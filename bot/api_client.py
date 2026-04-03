from __future__ import annotations

from typing import Any

import httpx

from backend.app.core.config import get_settings


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
