"""
Authentication service for AliyunDrive OAuth 2.0 flow.

Handles:
- QR code login (scan with AliyunDrive app)
- Refreshing access tokens automatically
- Session management (create, validate, revoke)
- Encrypted token storage in the sessions table
"""
from __future__ import annotations

import base64
import json
import logging
import time
import uuid
from typing import Any

import httpx
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.crypto import decrypt_token, encrypt_token
from app.db.models import UserSession
from app.services.aliyun_client import AliyunDriveClient

logger = logging.getLogger(__name__)

# Refresh the access token this many seconds before it actually expires
_REFRESH_BUFFER_SECONDS = 5 * 60  # 5 minutes

# aligo-compatible constants (same as aligo/core/Config.py)
_AUTH_HOST = "https://auth.aliyundrive.com"
_PASSPORT_HOST = "https://passport.aliyundrive.com"
_API_HOST = "https://api.aliyundrive.com"
_V2_OAUTH_AUTHORIZE = "/v2/oauth/authorize"
_QRCODE_GENERATE = "/newlogin/qrcode/generate.do"
_QRCODE_QUERY = "/newlogin/qrcode/query.do"
_TOKEN_REFRESH = "/v2/account/token"
_CLIENT_ID = "25dzX3vbYqktVxyX"
_UNI_PARAMS: dict[str, str] = {"appName": "aliyun_drive"}
_UNI_HEADERS: dict[str, str] = {
    "Referer": "https://aliyundrive.com",
    "User-Agent": (
        "AliApp(AYSD/5.8.0) com.alicloud.databox/37029260 "
        "Channel/36176927979800@rimet_android_5.8.0 language/zh-CN /Android Mobile/Xiaomi Redmi"
    ),
    "x-canary": "client=Android,app=adrive,version=v5.8.0",
}


class AuthService:
    """
    Manages QR-code-based authentication with AliyunDrive.

    All public methods are coroutines and must be awaited.
    """

    def __init__(
        self,
        db: AsyncSession,
        config: Settings,
        aliyun_client: AliyunDriveClient,
    ) -> None:
        self._db = db
        self._config = config
        self._client = aliyun_client

    # ------------------------------------------------------------------
    # QR Code Login
    # ------------------------------------------------------------------

    async def generate_qrcode(self) -> dict:
        """
        Request a new QR code from AliyunDrive passport service.

        Mirrors aligo's _login_by_qrcode():
          1. GET auth.aliyundrive.com/v2/oauth/authorize  → sets SESSIONID cookie
          2. GET passport.aliyundrive.com/newlogin/qrcode/generate.do → QR data
          3. Serialize cookies into the response so the client can pass them back
             during polling (stateless — no server-side session store needed).

        Returns a dict with:
          - qr_link: the URL to encode as QR code
          - qr_data: raw data dict from the generate endpoint
          - cookies: serialized cookie dict (must be passed back to poll)
        """
        async with httpx.AsyncClient(
            timeout=30.0,
            headers=_UNI_HEADERS,
            follow_redirects=True,
        ) as client:
            # Step 1: visit authorize page to obtain SESSIONID cookie
            await client.get(
                _AUTH_HOST + _V2_OAUTH_AUTHORIZE,
                params={
                    "login_type": "custom",
                    "response_type": "code",
                    "redirect_uri": "https://www.aliyundrive.com/sign/callback",
                    "client_id": _CLIENT_ID,
                    "state": '{"origin":"file://"}',
                },
            )
            session_id_cookie = client.cookies.get("SESSIONID")
            logger.info("generate_qrcode: SESSIONID=%s", session_id_cookie)

            # Step 2: generate QR code (same session, cookies carried automatically)
            resp = await client.get(
                _PASSPORT_HOST + _QRCODE_GENERATE,
                params=_UNI_PARAMS,
            )
            resp.raise_for_status()

            # Serialize all cookies so they can be sent back by the client on poll
            cookies_dict: dict[str, str] = dict(client.cookies)

        body = resp.json()
        data: dict = body["content"]["data"]

        logger.info(
            "generate_qrcode: ck=%s cookies=%s",
            data.get("ck"),
            list(cookies_dict.keys()),
        )

        return {
            "qr_link": data["codeContent"],
            "qr_data": data,
            "cookies": cookies_dict,
        }

    async def poll_qrcode(self, qr_data: dict, cookies: dict) -> dict:
        """
        Poll the QR code scan status once.

        Parameters
        ----------
        qr_data:
            The raw ``data`` dict returned by ``generate_qrcode``.
        cookies:
            The cookie dict returned by ``generate_qrcode`` — must include
            SESSIONID so the passport server can identify the QR session.

        Returns
        -------
        dict with keys:
          - status: "NEW" | "SCANED" | "CONFIRMED" | "EXPIRED" | "CANCELED"
          - session_id: set only when status == "CONFIRMED"
          - user_id: set only when status == "CONFIRMED"
          - nickname: set only when status == "CONFIRMED"
        """
        logger.debug(
            "poll_qrcode: ck=%s cookies=%s",
            qr_data.get("ck"),
            list(cookies.keys()),
        )

        async with httpx.AsyncClient(
            timeout=30.0,
            headers=_UNI_HEADERS,
            cookies=cookies,
        ) as client:
            resp = await client.post(
                _PASSPORT_HOST + _QRCODE_QUERY,
                data=qr_data,
                params=_UNI_PARAMS,
            )
            resp.raise_for_status()

        login_data = resp.json()["content"]["data"]
        status: str = login_data.get("qrCodeStatus", "EXPIRED")
        logger.debug("poll_qrcode: status=%s", status)

        if status in ("EXPIRED", "CANCELED"):
            return {"status": status}

        if status != "CONFIRMED":
            return {"status": status}

        # --- CONFIRMED ---
        biz_ext_b64: str = login_data.get("bizExt", "")
        biz_ext = base64.b64decode(biz_ext_b64).decode("gb18030")
        pds_result: dict = json.loads(biz_ext).get("pds_login_result", {})
        refresh_token: str = pds_result.get("refreshToken", "")

        if not refresh_token:
            raise HTTPException(
                status_code=400,
                detail="Failed to extract refresh token from QR login",
            )

        session_id, user_id, nickname = await self._create_session_from_refresh_token(
            refresh_token
        )

        return {
            "status": "CONFIRMED",
            "session_id": session_id,
            "user_id": user_id,
            "nickname": nickname,
        }

    async def _create_session_from_refresh_token(
        self, refresh_token: str
    ) -> tuple[str, str, str | None]:
        """Exchange a refresh token for an access token and persist the session."""
        async with httpx.AsyncClient(timeout=30.0, headers=_UNI_HEADERS) as client:
            resp = await client.post(
                _API_HOST + _TOKEN_REFRESH,
                json={"refresh_token": refresh_token, "grant_type": "refresh_token"},
            )
            resp.raise_for_status()

        token_data: dict = resp.json()
        access_token: str = token_data["access_token"]
        new_refresh_token: str = token_data.get("refresh_token", refresh_token)
        expires_in: int = token_data.get("expires_in", 7200)
        user_id: str = str(
            token_data.get("user_id") or token_data.get("sub") or uuid.uuid4().hex
        )
        nickname: str | None = token_data.get("nick_name") or token_data.get("nickname")

        session_id = str(uuid.uuid4())
        now = int(time.time())

        session = UserSession(
            id=session_id,
            user_id=user_id,
            nickname=nickname,
            access_token_enc=encrypt_token(access_token),
            refresh_token_enc=encrypt_token(new_refresh_token),
            token_expires_at=now + expires_in,
            created_at=now,
            updated_at=now,
        )
        self._db.add(session)
        await self._db.commit()

        logger.info(
            "Created session %s for user %s (%s)", session_id, user_id, nickname
        )
        return session_id, user_id, nickname

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    async def refresh_access_token(self, session_id: str) -> str:
        """
        Use the stored refresh token to obtain a new access token.
        """
        session = await self._get_session(session_id)

        try:
            refresh_token = decrypt_token(session.refresh_token_enc)
            token_pair = await self._client.refresh_token(refresh_token)
        except Exception as exc:
            logger.error("Token refresh failed for session %s: %s", session_id, exc)
            await self._db.delete(session)
            await self._db.commit()
            raise HTTPException(
                status_code=401,
                detail="Refresh token is invalid. Please re-authenticate.",
            ) from exc

        now = int(time.time())
        session.access_token_enc = encrypt_token(token_pair.access_token)
        session.refresh_token_enc = encrypt_token(token_pair.refresh_token)
        session.token_expires_at = now + token_pair.expires_in
        session.updated_at = now
        await self._db.commit()

        logger.info("Refreshed access token for session %s", session_id)
        return token_pair.access_token

    async def get_valid_access_token(self, session_id: str) -> str:
        """
        Return a valid access token, refreshing proactively if near expiry.
        """
        session = await self._get_session(session_id)

        now = int(time.time())
        if session.token_expires_at - now <= _REFRESH_BUFFER_SECONDS:
            return await self.refresh_access_token(session_id)

        return decrypt_token(session.access_token_enc)

    async def revoke_session(self, session_id: str) -> None:
        """Delete the session record, effectively logging the user out."""
        await self._db.execute(
            delete(UserSession).where(UserSession.id == session_id)
        )
        await self._db.commit()
        logger.info("Revoked session %s", session_id)

    async def is_authenticated(self, session_id: str) -> bool:
        """Check whether a session exists and has a stored refresh token."""
        if not session_id:
            return False
        result = await self._db.execute(
            select(UserSession).where(UserSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        return session is not None and bool(session.refresh_token_enc)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_session(self, session_id: str) -> UserSession:
        result = await self._db.execute(
            select(UserSession).where(UserSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        if session is None:
            raise HTTPException(
                status_code=401,
                detail="Session not found. Please re-authenticate.",
            )
        return session
