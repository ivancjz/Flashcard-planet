from __future__ import annotations

from typing import Any

import httpx

from backend.app.core.config import get_settings


class TierError(Exception):
    """Raised when the backend returns 403 due to a tier/plan limit."""

    def __init__(self, message: str, upgrade_url: str = "/upgrade") -> None:
        super().__init__(message)
        self.upgrade_url = upgrade_url


class BackendClient:
    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.backend_base_url.rstrip("/")

    async def fetch_price(self, name: str) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{self.base_url}/api/v1/prices/search", params={"name": name})
            response.raise_for_status()
            return response.json()

    async def fetch_top_movers(self, limit: int = 10) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/prices/topmovers",
                params={"limit": limit},
            )
            response.raise_for_status()
            return response.json()

    async def fetch_top_value(self, limit: int = 10) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/prices/topvalue",
                params={"limit": limit},
            )
            response.raise_for_status()
            return response.json()

    async def fetch_prediction(self, name: str) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/prices/predict",
                params={"name": name},
            )
            response.raise_for_status()
            return response.json()

    async def fetch_alerts(self, discord_user_id: str) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{self.base_url}/api/v1/alerts/{discord_user_id}")
            response.raise_for_status()
            return response.json()

    async def fetch_history(self, name: str, limit: int = 5) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/prices/history",
                params={"name": name, "limit": limit},
            )
            response.raise_for_status()
            return response.json()

    async def create_watch(
        self,
        discord_user_id: str,
        asset_name: str,
        threshold_up_percent: float | None = None,
        threshold_down_percent: float | None = None,
        target_price: float | None = None,
        predict_signal_change: bool | None = None,
        predict_up_probability_above: float | None = None,
        predict_down_probability_above: float | None = None,
    ) -> dict[str, Any]:
        payload = {
            "discord_user_id": discord_user_id,
            "asset_name": asset_name,
            "threshold_up_percent": threshold_up_percent,
            "threshold_down_percent": threshold_down_percent,
            "target_price": target_price,
            "predict_signal_change": predict_signal_change,
            "predict_up_probability_above": predict_up_probability_above,
            "predict_down_probability_above": predict_down_probability_above,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(f"{self.base_url}/api/v1/watchlists", json=payload)
            if response.status_code == 403:
                detail = response.json().get("detail", {})
                if isinstance(detail, dict):
                    error_msg = detail.get("error", "Pro account required.")
                    upgrade_url = detail.get("upgrade_url", "/upgrade")
                else:
                    error_msg = str(detail)
                    upgrade_url = "/upgrade"
                raise TierError(error_msg, upgrade_url)
            response.raise_for_status()
            return response.json()

    async def delete_watch(self, discord_user_id: str, asset_name: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.delete(
                f"{self.base_url}/api/v1/watchlists",
                params={"discord_user_id": discord_user_id, "asset_name": asset_name},
            )
            response.raise_for_status()
            return response.json()

    async def fetch_watchlist(self, discord_user_id: str) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{self.base_url}/api/v1/watchlists/{discord_user_id}")
            response.raise_for_status()
            return response.json()

    async def fetch_card_detail_enriched(
        self, external_id: str, discord_user_id: str
    ) -> dict | None:
        async with httpx.AsyncClient(timeout=10.0) as http:
            response = await http.get(
                f"{self.base_url}/api/v1/cards/{external_id}/enriched",
                params={"discord_user_id": discord_user_id},
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()

    async def fetch_alert_history(
        self,
        discord_user_id: str,
        limit: int = 10,
        asset_name: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit}
        if asset_name:
            params["asset_name"] = asset_name
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/alerts/{discord_user_id}/history",
                params=params,
            )
            response.raise_for_status()
            return response.json()
