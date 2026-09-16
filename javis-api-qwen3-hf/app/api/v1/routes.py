"""API v1 routes configuration."""

from fastapi import APIRouter

from app.auth.api.v1.routes import router as auth_router
from app.users.api.v1.routes import router as users_router

routers = APIRouter()

router_list = [auth_router, users_router]
v1_tags: list[str] = []

for router in router_list:
    v1_tags.extend(router.tags or [])
    routers.include_router(router)
