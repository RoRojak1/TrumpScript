import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nutrition_bot import Ingredient, X5CartBuilder, load_default_catalog
from nutrition_bot.x5_cli import build_cart, cart_to_json_payload, format_cart_summary, load_menu


def test_catalog_loads_sample_data():
    catalog = load_default_catalog()
    ingredient = Ingredient(name="гречка", quantity=1, unit="kg")
    product = catalog.find_product(ingredient)
    assert product is not None
    assert product.sku == "1000002"


def test_builder_matches_alias_and_computes_packs():
    catalog = load_default_catalog()
    builder = X5CartBuilder(catalog)
    cart = builder.build_cart([Ingredient(name="томаты", quantity=750, unit="g")])
    assert len(cart.items) == 1
    item = cart.items[0]
    assert item.product.sku == "1000005"
    # 750 g with packs of 500 g should result in 2 packs
    assert item.packs == 2
    assert math.isclose(item.total_price, item.product.price * 2, rel_tol=1e-3)


def test_builder_handles_incompatible_units_with_fallback(caplog):
    catalog = load_default_catalog()
    builder = X5CartBuilder(catalog)
    with caplog.at_level("WARNING"):
        cart = builder.build_cart(
            [Ingredient(name="яйца", quantity=6, unit="g")]  # deliberately wrong unit
        )
    assert "Incompatible units" in caplog.text
    assert cart.items[0].packs == 1


def test_cli_helpers_load_menu_and_format(tmp_path):
    menu_path = Path(__file__).resolve().parents[1] / "nutrition_bot" / "data" / "sample_menu.json"
    ingredients = load_menu(menu_path)
    assert ingredients[0].name == "гречка"

    catalog = load_default_catalog()
    cart = build_cart(ingredients, catalog=catalog)
    summary = format_cart_summary(cart)
    assert "гречка" in summary
    payload = cart_to_json_payload(cart)
    assert "sku" in payload
