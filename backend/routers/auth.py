from fastapi import APIRouter, HTTPException, status

from backend.database import get_pool
from backend.models.user import LoginRequest, RefreshRequest, TokenResponse, UserCreate, UserPublic
from backend.services.postgres_service import create_user, get_user_by_email
from backend.utils.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserPublic)
async def register(body: UserCreate):
    existing = await get_user_by_email(body.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = await create_user(body.email, hash_password(body.password))
    return UserPublic(id=user["id"], email=user["email"], role=user["role"])


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    user = await get_user_by_email(body.email)
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    sub = str(user["id"])
    return TokenResponse(
        access_token=create_access_token(sub, {"role": user["role"], "email": user["email"]}),
        refresh_token=create_refresh_token(sub),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest):
    try:
        payload = decode_token(body.refresh_token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    if payload.get("kind") != "refresh":
        raise HTTPException(status_code=401, detail="Not a refresh token")
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Invalid subject")
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, role FROM users WHERE id = $1",
            int(sub),
        )
    if not row:
        raise HTTPException(status_code=401, detail="User not found")
    return TokenResponse(
        access_token=create_access_token(
            str(row["id"]), {"role": row["role"], "email": row["email"]}
        ),
        refresh_token=create_refresh_token(str(row["id"])),
    )
