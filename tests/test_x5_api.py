import json
from pathlib import Path

import asyncio

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nutrition_bot import Cart, CartItem, Ingredient, Product, X5ApiClient, X5ApiError, X5Catalog


def build_sample_cart() -> Cart:
    product = Product(
        sku="1",
        name="Тестовый товар",
        price=100.0,
        package_quantity=1,
        package_unit="pcs",
    )
    ingredient = Ingredient(name="тест", quantity=1, unit="pcs")
    return Cart(items=[CartItem(ingredient=ingredient, product=product, packs=2)])


def test_api_client_auth_catalog_and_cart():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path, request.headers, request.content))
        if request.url.path == "/auth/login":
            assert request.method == "POST"
            body = json.loads(request.content.decode())
            assert body["phone"] == "+70000000000"
            assert body["password"] == "secret"
            return httpx.Response(200, json={"token": "abc"})
        if request.url.path == "/stores/123/catalog":
            assert request.headers.get("authorization") == "Bearer abc"
            return httpx.Response(
                200,
                json={
                    "products": [
                        {
                            "sku": "1",
                            "name": "Тестовый товар",
                            "price": 100,
                            "package": {"quantity": 1, "unit": "pcs"},
                        }
                    ]
                },
            )
        if request.url.path == "/cart":
            assert request.headers.get("authorization") == "Bearer abc"
            body = json.loads(request.content.decode())
            assert body["store_id"] == "123"
            assert body["items"] == [{"sku": "1", "quantity": 2}]
            return httpx.Response(201, json={"cart_id": "xyz"})
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    transport = httpx.MockTransport(handler)

    async def scenario() -> None:
        async with X5ApiClient(base_url="https://example.com", transport=transport) as client:
            await client.authenticate("+70000000000", "secret")
            catalog = await client.fetch_catalog("123")
            assert isinstance(catalog, X5Catalog)
            cart = build_sample_cart()
            response = await client.push_cart("123", cart)
            assert response["cart_id"] == "xyz"

    asyncio.run(scenario())

    # Убедимся, что все три запроса были выполнены
    paths = [entry[1] for entry in requests]
    assert paths == ["/auth/login", "/stores/123/catalog", "/cart"]


def test_api_client_requires_authentication():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"products": []}))

    async def scenario() -> None:
        async with X5ApiClient(base_url="https://example.com", transport=transport) as client:
            with pytest.raises(X5ApiError):
                await client.push_cart("1", build_sample_cart())

    asyncio.run(scenario())
