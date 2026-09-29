from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import current_claims, current_user, evict_session
from app.core.ratelimit import login_limiter
from app.repositories.mongo_repository import SessionRepository
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserOut
from app.services import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(req: RegisterRequest):
    return await auth_service.register(req)


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, request: Request):
    key = f"{request.client.host if request.client else '?'}:{req.email.lower()}"
    wait = login_limiter.retry_after(key)
    if wait:
        raise HTTPException(429, f"Too many failed attempts. Try again in {wait} seconds.",
                            headers={"Retry-After": str(wait)})
    try:
        result = await auth_service.login(req)
    except HTTPException as e:
        if e.status_code == 401:
            login_limiter.record_failure(key)
        raise
    login_limiter.reset(key)
    return result


@router.post("/logout", status_code=204)
async def logout(claims: dict = Depends(current_claims)):
    evict_session(claims["sid"])
    await SessionRepository().delete(claims["sid"])


@router.get("/me", response_model=UserOut)
async def me(user: dict = Depends(current_user)):
    return auth_service.to_user_out(user)
