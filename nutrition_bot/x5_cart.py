"""Utilities for assembling a shopping cart using the X5 retail catalog.

The module does not depend on any private or undocumented libraries.  It is
built around a small, serialisable schema so that the same logic can be reused
with the unofficial X5/"Пятёрочка" HTTP API or with a locally cached snapshot of
its catalogue.  For the purposes of unit testing we ship the
``x5_sample_catalog.json`` file which mimics a subset of the real API response.

The main entry point is :class:`X5CartBuilder`.  It converts a list of desired
ingredients into concrete ``sku`` payloads that can later be uploaded to a cart
through a browser automation step or an API client.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Ingredient:
    """A menu ingredient with quantity and measurement unit."""

    name: str
    quantity: float
    unit: str

    def normalised_unit(self) -> str:
        return self.unit.strip().lower()


@dataclass(frozen=True)
class Product:
    """A purchasable SKU from the X5 assortment."""

    sku: str
    name: str
    price: float
    package_quantity: float
    package_unit: str
    aliases: Sequence[str] = field(default_factory=list)

    def normalised_unit(self) -> str:
        return self.package_unit.strip().lower()

    def all_keywords(self) -> Sequence[str]:
        """Return the list of names that can trigger a match."""

        aliases = list(self.aliases)
        aliases.append(self.name)
        return aliases


@dataclass
class CartItem:
    """Link between the ingredient and the chosen product."""

    ingredient: Ingredient
    product: Product
    packs: int

    @property
    def total_price(self) -> float:
        return round(self.packs * self.product.price, 2)

    @property
    def payload(self) -> Dict[str, object]:
        """Represent the item as a serialisable structure for API calls."""

        return {"sku": self.product.sku, "quantity": self.packs}


@dataclass
class Cart:
    """Collection of :class:`CartItem` objects."""

    items: List[CartItem]

    @property
    def total_price(self) -> float:
        return round(sum(item.total_price for item in self.items), 2)

    def to_payload(self) -> List[Dict[str, object]]:
        """Return the payload expected by most cart endpoints."""

        return [item.payload for item in self.items]


class X5Catalog:
    """A tiny in-memory representation of the X5 assortment.

    The class can be initialised either from the bundled sample file or from a
    JSON response obtained via the unofficial X5 Group APIs.  Only the handful
    of fields that are necessary to build a cart are preserved.
    """

    #: Conversion table to translate units into a canonical base.
    UNIT_FACTORS: Dict[str, float] = {
        # Mass
        "g": 1.0,
        "гр": 1.0,
        "г": 1.0,
        "gram": 1.0,
        "grams": 1.0,
        "gramm": 1.0,
        "грамм": 1.0,
        "граммы": 1.0,
        "kg": 1000.0,
        "кг": 1000.0,
        "kilogram": 1000.0,
        "kilograms": 1000.0,
        "килограмм": 1000.0,
        "килограммы": 1000.0,
        "mg": 0.001,
        "мг": 0.001,
        # Volume
        "ml": 0.001,
        "milliliter": 0.001,
        "milliliters": 0.001,
        "мл": 0.001,
        "l": 1.0,
        "литр": 1.0,
        "литры": 1.0,
        "л": 1.0,
        # Count
        "pcs": 1.0,
        "piece": 1.0,
        "pieces": 1.0,
        "шт": 1.0,
        "шт.": 1.0,
        "уп": 1.0,
        "упаковка": 1.0,
    }

    #: Categories of measurement compatible with each unit.
    UNIT_CATEGORIES: Dict[str, str] = {
        "g": "mass",
        "гр": "mass",
        "г": "mass",
        "gram": "mass",
        "grams": "mass",
        "gramm": "mass",
        "грамм": "mass",
        "граммы": "mass",
        "kg": "mass",
        "кг": "mass",
        "kilogram": "mass",
        "kilograms": "mass",
        "килограмм": "mass",
        "килограммы": "mass",
        "mg": "mass",
        "мг": "mass",
        "ml": "volume",
        "milliliter": "volume",
        "milliliters": "volume",
        "мл": "volume",
        "l": "volume",
        "литр": "volume",
        "литры": "volume",
        "л": "volume",
        "pcs": "count",
        "piece": "count",
        "pieces": "count",
        "шт": "count",
        "шт.": "count",
        "уп": "count",
        "упаковка": "count",
    }

    def __init__(self, products: Sequence[Product]):
        self._products = list(products)

    @classmethod
    def from_file(cls, path: Path) -> "X5Catalog":
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        if isinstance(payload, dict):
            # Some API responses wrap the product list inside a dedicated field.
            for key in ("products", "items", "assortment"):
                if key in payload and isinstance(payload[key], list):
                    payload = payload[key]
                    break
        if not isinstance(payload, list):
            raise ValueError("Unexpected catalog payload structure")
        return cls.from_payload(payload)

    @classmethod
    def from_payload(cls, payload: Sequence[Dict[str, object]]) -> "X5Catalog":
        products: List[Product] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            package = item.get("package") or {}
            if not isinstance(package, dict):
                package = {}
            package_quantity = package.get("quantity") or item.get("package_quantity") or item.get("weight") or 1
            package_unit = package.get("unit") or item.get("package_unit") or item.get("measure_unit") or item.get("unit") or "pcs"
            aliases = item.get("aliases") or item.get("synonyms") or item.get("tags") or []
            if isinstance(aliases, str):
                aliases = [aliases]
            price = item.get("price") or item.get("current_price") or item.get("regular_price") or 0
            sku = item.get("sku") or item.get("id") or item.get("code")
            name = item.get("name") or item.get("title")
            if sku is None or name is None:
                continue
            try:
                product = Product(
                    sku=str(sku),
                    name=str(name),
                    price=float(price),
                    package_quantity=float(package_quantity),
                    package_unit=str(package_unit),
                    aliases=list(aliases) if isinstance(aliases, (list, tuple, set)) else [],
                )
            except (TypeError, ValueError):
                continue
            products.append(product)
        return cls(products)

    def find_product(self, ingredient: Ingredient) -> Optional[Product]:
        """Return the product that best matches the ingredient name."""

        candidates = []
        ingredient_name = ingredient.name.lower()
        for product in self._products:
            score = self._match_score(product, ingredient_name)
            if score:
                candidates.append((score, product.price, product))
        if not candidates:
            return None
        _, _, best_product = max(candidates, key=lambda tup: (tup[0], -tup[1]))
        return best_product

    @staticmethod
    def _match_score(product: Product, ingredient_name: str) -> int:
        """Calculate a heuristic score between 0 and 3."""

        best_score = 0
        for keyword in product.all_keywords():
            lowered = keyword.lower()
            if lowered == ingredient_name:
                return 3
            if lowered in ingredient_name or ingredient_name in lowered:
                best_score = max(best_score, 2)
            else:
                lowered_words = set(lowered.split())
                ingr_words = set(ingredient_name.split())
                if lowered_words & ingr_words:
                    best_score = max(best_score, 1)
        return best_score

    @classmethod
    def unit_category(cls, unit: str) -> Optional[str]:
        return cls.UNIT_CATEGORIES.get(unit)

    @classmethod
    def unit_factor(cls, unit: str) -> Optional[float]:
        return cls.UNIT_FACTORS.get(unit)


class X5CartBuilder:
    """Convert menu ingredients into the payload for an X5 cart."""

    def __init__(self, catalog: X5Catalog, default_store_id: Optional[str] = None):
        self.catalog = catalog
        self.default_store_id = default_store_id

    def build_cart(self, ingredients: Iterable[Ingredient]) -> Cart:
        items: List[CartItem] = []
        for ingredient in ingredients:
            product = self.catalog.find_product(ingredient)
            if not product:
                logger.warning("No product found for ingredient '%s'", ingredient.name)
                continue
            packs = self._calculate_packs(ingredient, product)
            items.append(CartItem(ingredient=ingredient, product=product, packs=packs))
        return Cart(items)

    def _calculate_packs(self, ingredient: Ingredient, product: Product) -> int:
        ingredient_unit = ingredient.normalised_unit()
        product_unit = product.normalised_unit()

        ingredient_category = X5Catalog.unit_category(ingredient_unit)
        product_category = X5Catalog.unit_category(product_unit)

        if ingredient_category != product_category:
            # If the units are incompatible we fall back to a single pack to avoid
            # suggesting impossible conversions.  A warning is logged so the menu
            # creator can add the missing mapping.
            logger.warning(
                "Incompatible units: ingredient '%s' uses '%s', product '%s' uses '%s'",
                ingredient.name,
                ingredient_unit,
                product.name,
                product_unit,
            )
            return 1

        ingredient_factor = X5Catalog.unit_factor(ingredient_unit)
        product_factor = X5Catalog.unit_factor(product_unit)
        if ingredient_factor is None or product_factor is None:
            logger.warning(
                "Unknown measurement units for '%s' (%s) or '%s' (%s)",
                ingredient.name,
                ingredient_unit,
                product.name,
                product_unit,
            )
            return 1

        ingredient_qty_base = ingredient.quantity * ingredient_factor
        product_qty_base = product.package_quantity * product_factor
        if product_qty_base == 0:
            logger.warning("Product '%s' has zero package size", product.name)
            return 1

        packs = math.ceil(ingredient_qty_base / product_qty_base)
        return max(packs, 1)


def load_default_catalog() -> X5Catalog:
    """Load the bundled sample catalogue for development purposes."""

    sample_path = Path(__file__).parent / "data" / "x5_sample_catalog.json"
    if not sample_path.exists():
        raise FileNotFoundError(
            "Sample X5 catalog is missing. Ensure 'x5_sample_catalog.json' is packaged"
        )
    return X5Catalog.from_file(sample_path)


__all__ = [
    "Ingredient",
    "Product",
    "CartItem",
    "Cart",
    "X5Catalog",
    "X5CartBuilder",
    "load_default_catalog",
]
