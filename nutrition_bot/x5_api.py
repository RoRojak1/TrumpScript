"""Асинхронный клиент для неофициальных HTTP-интерфейсов X5 Group.

Модуль не делает никаких сетевых запросов по умолчанию; вместо этого он
инкапсулирует логику построения запросов и разбор ответов, чтобы её можно было
легко покрыть юнит-тестами и переиспользовать в других сценариях.  В тестах мы
используем :class:`httpx.MockTransport`, а в рабочем окружении клиент можно
подключить к реальному API (например, pyaterochka_api или собственному шлюзу).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx

from .x5_cart import Cart, X5Catalog


class X5ApiError(RuntimeError):
    """Обёртка для ошибок взаимодействия с API."""


@dataclass
class X5ApiClient:
    """Минимальный HTTP-клиент для взаимодействия с сервисами X5."""

    base_url: str
    timeout: float = 10.0
    transport: Optional[httpx.BaseTransport] = None

    def __post_init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            transport=self.transport,
        )
        self._token: Optional[str] = None

    async def __aenter__(self) -> "X5ApiClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def authenticate(self, phone: str, password: str) -> None:
        """Получить токен доступа по номеру телефона и паролю/коду."""

        payload = {"phone": phone, "password": password}
        response = await self._client.post("/auth/login", json=payload)
        if response.status_code >= 400:
            raise X5ApiError(
                f"Authentication failed with status {response.status_code}: {response.text}"
            )
        data = response.json()
        token = data.get("token") or data.get("access_token")
        if not token:
            raise X5ApiError("Authentication response does not contain an access token")
        self._token = str(token)

    async def fetch_catalog(self, store_id: str) -> X5Catalog:
        """Загрузить ассортимент магазина и преобразовать его в :class:`X5Catalog`."""

        response = await self._client.get(
            f"/stores/{store_id}/catalog",
            headers=self._auth_headers(optional=True),
        )
        if response.status_code >= 400:
            raise X5ApiError(
                f"Failed to fetch catalog (status {response.status_code}): {response.text}"
            )
        data = response.json()
        products_payload: Any
        if isinstance(data, dict):
            products_payload = data.get("products") or data.get("items") or []
        else:
            products_payload = data
        if not isinstance(products_payload, list):
            raise X5ApiError("Catalog response has unexpected structure")
        return X5Catalog.from_payload(products_payload)

    async def push_cart(self, store_id: str, cart: Cart) -> Dict[str, Any]:
        """Отправить собранную корзину и вернуть JSON-ответ API."""

        body = {"store_id": store_id, "items": cart.to_payload()}
        response = await self._client.post(
            "/cart",
            headers=self._auth_headers(optional=False),
            json=body,
        )
        if response.status_code >= 400:
            raise X5ApiError(
                f"Cart submission failed with status {response.status_code}: {response.text}"
            )
        try:
            return response.json()
        except json.JSONDecodeError as exc:  # pragma: no cover - защитный код
            raise X5ApiError("Cart submission returned invalid JSON") from exc

    def _auth_headers(self, *, optional: bool) -> Dict[str, str]:
        if not self._token:
            if optional:
                return {}
            raise X5ApiError("Authentication token is missing; call authenticate() first")
        return {"Authorization": f"Bearer {self._token}"}


__all__ = ["X5ApiClient", "X5ApiError"]

