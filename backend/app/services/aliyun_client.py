"""
AliyunDrive API client.

Uses api.aliyundrive.com (same as aligo) for all file operations.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import Settings
from app.core.file_type import classify_file_type
from app.core.rate_limiter import RateLimiter
from app.models.schemas import BatchResult, DuplicateFile, DuplicateGroup, DuplicateListPage, TokenPair

logger = logging.getLogger(__name__)

# Use the same host as aligo — the open.alipan.com OpenAPI requires a registered
# client_id which we don't have; api.aliyundrive.com works with the QR-code token.
_API_HOST = "https://api.aliyundrive.com"

_UNI_HEADERS: dict[str, str] = {
    "Referer": "https://aliyundrive.com",
    "User-Agent": (
        "AliApp(AYSD/5.8.0) com.alicloud.databox/37029260 "
        "Channel/36176927979800@rimet_android_5.8.0 language/zh-CN /Android Mobile/Xiaomi Redmi"
    ),
    "x-canary": "client=Android,app=adrive,version=v5.8.0",
}

# Error codes returned by AliyunDrive that indicate the file no longer exists
# or is already in the recycle bin — treat these as "success" since the file
# is effectively gone from the user's drive.
_IGNORABLE_CODES = {
    "NotFound.File",
    "ForbiddenFileInTheRecycleBin",
    "FileNotFound",
    "NotFound",
}

# Error message substrings that also indicate the file is already gone.
_IGNORABLE_MSG_FRAGMENTS = (
    "not found",
    "recycle bin is not supported",
    "file in system recycle bin",
)


class AliyunDriveClient:
    """
    Async HTTP client for the AliyunDrive internal API (api.aliyundrive.com).
    """

    def __init__(self, config: Settings, rate_limiter: RateLimiter) -> None:
        self._config = config
        self._rate_limiter = rate_limiter

    # ------------------------------------------------------------------
    # Drive info
    # ------------------------------------------------------------------

    async def get_default_drive_id(self, access_token: str) -> str:
        """Return the user's default drive_id."""
        url = f"{_API_HOST}/v2/drive/get_default_drive"
        data = await self._request("POST", url, access_token, json={})
        # API returns "drive_id" (not "default_drive_id")
        return data["drive_id"]

    # ------------------------------------------------------------------
    # File listing
    # ------------------------------------------------------------------

    async def list_files(
        self,
        access_token: str,
        drive_id: str,
        parent_file_id: str = "root",
        marker: str | None = None,
        limit: int = 200,
    ) -> dict:
        """
        List files/folders in a directory (one page).

        Returns the raw API response dict with keys: items, next_marker
        """
        url = f"{_API_HOST}/adrive/v3/file/list"
        payload: dict[str, Any] = {
            "drive_id": drive_id,
            "parent_file_id": parent_file_id,
            "limit": limit,
            "all": False,
            "order_by": "updated_at",
            "order_direction": "DESC",
        }
        if marker:
            payload["marker"] = marker
        return await self._request("POST", url, access_token, json=payload)

    # ------------------------------------------------------------------
    # Batch operations
    # ------------------------------------------------------------------

    async def batch_trash(
        self,
        access_token: str,
        file_ids: list[str],
        drive_id: str = "",
    ) -> BatchResult:
        """Move up to 100 files to the recycle bin."""
        url = f"{_API_HOST}/v3/batch"
        payload = {
            "requests": [
                {
                    "body": {"drive_id": drive_id, "file_id": fid},
                    "headers": {"Content-Type": "application/json"},
                    "id": fid,
                    "method": "POST",
                    "url": "/recyclebin/trash",
                }
                for fid in file_ids
            ],
            "resource": "file",
        }
        data = await self._request("POST", url, access_token, json=payload)
        return self._parse_batch_response(data, file_ids)

    async def batch_delete_permanently(
        self,
        access_token: str,
        file_ids: list[str],
        drive_id: str = "",
    ) -> BatchResult:
        """Permanently delete up to 100 files."""
        url = f"{_API_HOST}/v3/batch"
        payload = {
            "requests": [
                {
                    "body": {"drive_id": drive_id, "file_id": fid},
                    "headers": {"Content-Type": "application/json"},
                    "id": fid,
                    "method": "POST",
                    "url": "/file/delete",
                }
                for fid in file_ids
            ],
            "resource": "file",
        }
        data = await self._request("POST", url, access_token, json=payload)
        return self._parse_batch_response(data, file_ids)

    # ------------------------------------------------------------------
    # Token refresh
    # ------------------------------------------------------------------

    async def refresh_token(self, refresh_token: str) -> TokenPair:
        """Exchange a refresh token for a new access/refresh token pair."""
        url = "https://api.aliyundrive.com/v2/account/token"
        payload = {
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        async with httpx.AsyncClient(timeout=30.0, headers=_UNI_HEADERS) as client:
            response = await client.post(
                url, json=payload,
                headers={**_UNI_HEADERS, "Content-Type": "application/json"},
            )
            response.raise_for_status()
            data = response.json()

        return TokenPair(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", refresh_token),
            expires_in=data.get("expires_in", 7200),
            token_type=data.get("token_type", "Bearer"),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        url: str,
        access_token: str | None,
        **kwargs: Any,
    ) -> dict:
        async def _do_request() -> dict:
            headers: dict[str, str] = {
                **_UNI_HEADERS,
                "Content-Type": "application/json",
            }
            if access_token:
                headers["Authorization"] = f"Bearer {access_token}"

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.request(method, url, headers=headers, **kwargs)
                response.raise_for_status()
                return response.json()

        result: dict = await self._rate_limiter.call_with_rate_limit(_do_request)
        return result

    @staticmethod
    def _parse_batch_response(data: dict, requested_ids: list[str]) -> BatchResult:
        success_ids: list[str] = []
        failed_items: list[dict] = []

        responses: list[dict] = data.get("responses", [])
        responded_ids: set[str] = set()

        for item in responses:
            file_id: str = item.get("id", "")
            responded_ids.add(file_id)
            status: int = item.get("status", 0)
            body: dict = item.get("body", {})
            error_code: str = body.get("code", "")
            error_msg: str = body.get("message", "")

            # Log non-2xx responses for debugging
            if not (200 <= status < 300):
                logger.debug(
                    "Batch response non-2xx: file_id=%s status=%s code=%r message=%r",
                    file_id, status, error_code, error_msg,
                )

            # Treat as success if HTTP 2xx, or if the error indicates the file
            # is already gone / already in the recycle bin.
            msg_lower = error_msg.lower()
            ignorable = (
                error_code in _IGNORABLE_CODES
                or any(frag in msg_lower for frag in _IGNORABLE_MSG_FRAGMENTS)
            )

            if 200 <= status < 300 or ignorable:
                success_ids.append(file_id)
            else:
                failed_items.append({
                    "file_id": file_id,
                    "error_msg": error_msg or f"HTTP {status}",
                })

        for fid in requested_ids:
            if fid not in responded_ids:
                logger.warning("File ID %s was not present in batch response.", fid)
                failed_items.append({
                    "file_id": fid,
                    "error_msg": "No response from batch API",
                })

        return BatchResult(success_ids=success_ids, failed_items=failed_items)
