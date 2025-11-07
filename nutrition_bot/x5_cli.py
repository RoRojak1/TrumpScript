"""Command line helper to experiment with the X5 cart builder."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .x5_api import X5ApiClient, X5ApiError
from .x5_cart import Cart, Ingredient, X5CartBuilder, X5Catalog, load_default_catalog


def load_menu(path: Path) -> List[Ingredient]:
    """Load a menu definition from ``path``.

    The expected structure is a JSON array with objects containing
    ``name``, ``quantity`` and ``unit`` fields.  Quantities are
    automatically converted to ``float`` values.
    """

    with open(path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)

    ingredients: List[Ingredient] = []
    for entry in payload:
        try:
            name = entry["name"]
            quantity = float(entry["quantity"])
            unit = entry["unit"]
        except (KeyError, TypeError, ValueError) as exc:  # pragma: no cover - defensive
            raise ValueError(f"Invalid menu entry: {entry!r}") from exc
        ingredients.append(Ingredient(name=name, quantity=quantity, unit=unit))
    return ingredients


def build_cart(
    ingredients: Sequence[Ingredient],
    *,
    catalog: Optional[X5Catalog] = None,
    store_id: Optional[str] = None,
) -> Cart:
    """Build a cart for ``ingredients`` using ``catalog``.

    If ``catalog`` is omitted the bundled sample catalogue is used.  The
    ``store_id`` parameter is present for parity with the unofficial API
    but is currently unused by the builder; it is accepted so that the
    function signature mirrors the real-world integration points.
    """

    catalog = catalog or load_default_catalog()
    builder = X5CartBuilder(catalog, default_store_id=store_id)
    return builder.build_cart(ingredients)


def format_cart_summary(cart: Cart) -> str:
    """Return a human readable summary of the cart."""

    lines: List[str] = []
    for item in cart.items:
        line = (
            f"- {item.ingredient.name} → {item.product.name}"
            f" (packs: {item.packs}, price: {item.total_price:.2f} ₽)"
        )
        lines.append(line)
    lines.append(f"Total: {cart.total_price:.2f} ₽")
    return "\n".join(lines)


def cart_to_json_payload(cart: Cart) -> str:
    """Serialise the cart payload to JSON for inspection."""

    return json.dumps(cart.to_payload(), ensure_ascii=False, indent=2)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an X5 cart from a menu JSON file")
    parser.add_argument(
        "--menu",
        type=Path,
        required=True,
        help="Path to a JSON file describing the menu ingredients",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        help="Optional path to an X5 catalog JSON snapshot; defaults to the bundled sample",
    )
    parser.add_argument(
        "--store-id",
        type=str,
        help="Optional store identifier to include in downstream requests",
    )
    parser.add_argument(
        "--api-base",
        type=str,
        help="Base URL of the X5 HTTP API when submitting carts or loading remote catalogs",
    )
    parser.add_argument(
        "--phone",
        type=str,
        help="Phone number used for API authentication",
    )
    parser.add_argument(
        "--password",
        type=str,
        help="Password or one-time code for API authentication",
    )
    parser.add_argument(
        "--use-api-catalog",
        action="store_true",
        help="Load the catalog from the HTTP API instead of a local snapshot",
    )
    parser.add_argument(
        "--submit",
        action="store_true",
        help="Submit the assembled cart to the HTTP API",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="If set, print the cart payload JSON after the summary",
    )
    args = parser.parse_args(argv)
    if args.submit:
        missing = [
            name
            for name, value in (
                ("--api-base", args.api_base),
                ("--store-id", args.store_id),
                ("--phone", args.phone),
                ("--password", args.password),
            )
            if not value
        ]
        if missing:
            parser.error("--submit requires the following arguments: " + ", ".join(missing))
    if args.use_api_catalog and (not args.api_base or not args.store_id):
        parser.error("--use-api-catalog requires --api-base and --store-id")
    return args


async def fetch_catalog_via_api(
    store_id: str,
    *,
    api_base: str,
    phone: Optional[str] = None,
    password: Optional[str] = None,
    client_kwargs: Optional[Dict[str, Any]] = None,
) -> X5Catalog:
    """Загрузить каталог через :class:`X5ApiClient`.  Используется в CLI и тестах."""

    client_kwargs = dict(client_kwargs or {})
    async with X5ApiClient(base_url=api_base, **client_kwargs) as client:
        if phone and password:
            await client.authenticate(phone, password)
        elif phone or password:
            raise X5ApiError("Both phone and password must be provided for authentication")
        return await client.fetch_catalog(store_id)


async def submit_cart_via_api(
    cart: Cart,
    *,
    api_base: str,
    store_id: str,
    phone: str,
    password: str,
    client_kwargs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Отправить корзину через :class:`X5ApiClient` и вернуть ответ API."""

    client_kwargs = dict(client_kwargs or {})
    async with X5ApiClient(base_url=api_base, **client_kwargs) as client:
        await client.authenticate(phone, password)
        return await client.push_cart(store_id, cart)


def resolve_catalog(args: argparse.Namespace) -> X5Catalog:
    if args.catalog:
        return X5Catalog.from_file(args.catalog)
    if args.use_api_catalog:
        if not args.api_base or not args.store_id:
            raise X5ApiError("API base URL and store id are required to load catalog from API")
        return asyncio.run(
            fetch_catalog_via_api(
                args.store_id,
                api_base=args.api_base,
                phone=args.phone,
                password=args.password,
            )
        )
    return load_default_catalog()


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    ingredients = load_menu(args.menu)
    try:
        catalog = resolve_catalog(args)
    except X5ApiError as exc:
        raise SystemExit(str(exc))
    cart = build_cart(ingredients, catalog=catalog, store_id=args.store_id)
    print(format_cart_summary(cart))
    if args.json:
        print()
        print(cart_to_json_payload(cart))
    if args.submit:
        try:
            response = asyncio.run(
                submit_cart_via_api(
                    cart,
                    api_base=args.api_base,
                    store_id=args.store_id,
                    phone=args.phone,
                    password=args.password,
                )
            )
        except X5ApiError as exc:
            raise SystemExit(str(exc))
        print()
        print("API response:")
        print(json.dumps(response, ensure_ascii=False, indent=2))


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
