"""
Authentication API routes — QR code login.

Endpoints:
  GET  /api/auth/qrcode         — Generate a new QR code for login
  POST /api/auth/qrcode/poll    — Poll QR code scan status
  GET  /api/auth/status         — Check whether the current session is authenticated
  POST /api/auth/logout         — Revoke the session
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.rate_limiter import RateLimiter, RateLimitConfig
from app.db.database import get_db
from app.services.aliyun_client import AliyunDriveClient
from app.services.auth_service import AuthService

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------


def get_auth_service(db: AsyncSession = Depends(get_db)) -> AuthService:
    rate_limiter = RateLimiter(RateLimitConfig(
        interval_ms=settings.api_call_interval_ms,
        max_retries=settings.api_max_retries,
        max_backoff_seconds=settings.api_max_backoff_seconds,
    ))
    aliyun_client = AliyunDriveClient(settings, rate_limiter)
    return AuthService(db, settings, aliyun_client)


def get_session_id(
    session_id: str | None = Query(default=None),
    x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
) -> str | None:
    return session_id or x_session_id


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/qrcode", summary="Generate QR code for login")
async def get_qrcode(
    auth_service: AuthService = Depends(get_auth_service),
) -> JSONResponse:
    """
    Generate a new AliyunDrive QR code.

    Returns:
      - qr_link: URL to encode as QR code image on the frontend
      - qr_data: opaque data dict needed for polling (pass back as-is)
    """
    result = await auth_service.generate_qrcode()
    return JSONResponse(content={
        "qr_link": result["qr_link"],
        "qr_data": result["qr_data"],
        "cookies": result["cookies"],
    })


@router.post("/qrcode/poll", summary="Poll QR code scan status")
async def poll_qrcode(
    body: dict,
    auth_service: AuthService = Depends(get_auth_service),
) -> JSONResponse:
    """
    Poll the scan status of a QR code.

    Request body: ``{ "qr_data": <dict>, "cookies": <dict> }``
    Both fields are returned as-is from the /qrcode endpoint.
    """
    qr_data: dict = body.get("qr_data", {})
    cookies: dict = body.get("cookies", {})
    result = await auth_service.poll_qrcode(qr_data, cookies)
    return JSONResponse(content=result)


@router.get("/status", summary="Check authentication status")
async def auth_status(
    session_id: str | None = Depends(get_session_id),
    auth_service: AuthService = Depends(get_auth_service),
) -> JSONResponse:
    """
    Return whether the current session is authenticated.
    """
    if not session_id:
        return JSONResponse(content={"authenticated": False, "user_id": None, "nickname": None})

    authenticated = await auth_service.is_authenticated(session_id)

    user_id: str | None = None
    nickname: str | None = None

    if authenticated:
        from sqlalchemy import select
        from app.db.models import UserSession

        result = await auth_service._db.execute(
            select(UserSession).where(UserSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        if session:
            user_id = session.user_id
            nickname = session.nickname

    return JSONResponse(content={"authenticated": authenticated, "user_id": user_id, "nickname": nickname})


@router.post("/logout", summary="Logout — revoke session")
async def logout(
    session_id: str | None = Depends(get_session_id),
    auth_service: AuthService = Depends(get_auth_service),
) -> JSONResponse:
    """Revoke the current session."""
    if session_id:
        await auth_service.revoke_session(session_id)
    return JSONResponse(content={"message": "logged out"})
