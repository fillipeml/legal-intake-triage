"""Microsoft Graph client (app-only, client credentials) with retries on throttling and
transient errors; the mailbox, the board and the directory lookups go through it."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import httpx

GRAPH = "https://graph.microsoft.com/v1.0"


class GraphError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"Graph {status}: {message}")
        self.status = status


class GraphClient:
    def __init__(
        self, tenant_id: str, client_id: str, client_secret: str, *, timeout: float = 60.0
    ) -> None:
        self.tenant_id, self.client_id, self.client_secret = tenant_id, client_id, client_secret
        self._token: str | None = None
        self._expires = 0.0
        self._http = httpx.Client(timeout=timeout)

    def _bearer(self) -> str:
        if self._token and self._expires > time.time() + 60:
            return self._token
        if not (self.tenant_id and self.client_id and self.client_secret):
            raise GraphError(0, "MS_TENANT_ID, MS_CLIENT_ID and MS_CLIENT_SECRET are required")
        import msal

        app = msal.ConfidentialClientApplication(
            self.client_id,
            authority=f"https://login.microsoftonline.com/{self.tenant_id}",
            client_credential=self.client_secret,
        )
        result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
        if "access_token" not in result:
            raise GraphError(401, str(result.get("error_description") or "authentication failed"))
        self._token = result["access_token"]
        self._expires = time.time() + int(result.get("expires_in", 3600))
        return self._token

    def _request(
        self,
        method: str,
        path_or_url: str,
        *,
        params: dict | None = None,
        json: Any = None,
        headers: dict | None = None,
    ) -> httpx.Response:
        url = path_or_url if path_or_url.startswith("http") else f"{GRAPH}{path_or_url}"
        for attempt in range(5):
            response = self._http.request(
                method,
                url,
                params=params,
                json=json,
                headers={"Authorization": f"Bearer {self._bearer()}", **(headers or {})},
            )
            if response.status_code == 429 or response.status_code >= 500:
                time.sleep(int(response.headers.get("Retry-After", "0") or 0) or 2 ** (attempt + 1))
                continue
            if response.status_code >= 400:
                raise GraphError(response.status_code, response.text[:500])
            return response
        raise GraphError(response.status_code, f"still failing after retries: {url}")

    def get(self, path: str, params: dict | None = None, headers: dict | None = None) -> dict:
        return self._request("GET", path, params=params, headers=headers).json()

    def get_paged(
        self, path: str, params: dict | None = None, headers: dict | None = None
    ) -> Iterator[dict]:
        data = self.get(path, params, headers)
        while True:
            yield from data.get("value", [])
            next_link = data.get("@odata.nextLink")
            if not next_link:
                return
            data = self._request("GET", next_link, headers=headers).json()

    def post(self, path: str, body: Any) -> dict:
        response = self._request("POST", path, json=body)
        return response.json() if response.content else {}

    def patch(self, path: str, body: Any, *, etag: str | None = None) -> None:
        headers = {"If-Match": etag} if etag else {}
        self._request("PATCH", path, json=body, headers=headers)
