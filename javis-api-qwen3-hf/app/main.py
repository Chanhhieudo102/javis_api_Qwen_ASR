"""FastAPI Application."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.common.exceptions import AppHTTPException
from app.common.exceptions.global_exceptions import global_exception_handler
from app.common.logging import setup_logging
from app.common.middleware import locale_middleware
from app.common.utils import build_docs
from app.voice2text.api.v2.routes import router as voice2text_router
from app.voice2text.services.hf_engine import HFEngine

# Đọc biến môi trường ENABLE_DB để quyết định có kết nối DB không
# Mặc định là "true" (production). Modal sẽ truyền "false" qua secrets.
ENABLE_DB = os.getenv("ENABLE_DB", "true").lower() == "true"


@asynccontextmanager
async def lifespan(app: FastAPI):
    HFEngine.get_instance()
    yield


class FastAPIAppSingleton:
    """Singleton class for FastAPI application."""

    _instance: FastAPI | None = None

    @classmethod
    def get_instance(cls) -> FastAPI:
        """Get the singleton instance of the FastAPI application."""
        if cls._instance is None:
            cls._instance = cls._create_app()
        return cls._instance

    @classmethod
    def _create_app(cls) -> FastAPI:
        """Create and configure the FastAPI application."""
        app = FastAPI(
            title="BE API",
            version="1.0.0",
            description="A FastAPI backend with clean architecture",
            docs_url=None,
            redoc_url=None,
            openapi_url=None,
            lifespan=lifespan,
        )

        # CORS middleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Initialize database (chỉ khi ENABLE_DB=true)
        if ENABLE_DB:
            from app.common.db.init_db import init_db
            init_db()

        # Locale middleware
        app.middleware("http")(locale_middleware)

        # Exception handlers
        app.add_exception_handler(AppHTTPException, global_exception_handler)
        app.add_exception_handler(RequestValidationError, global_exception_handler)

        # Setup logging
        setup_logging()

        # Include routers
        if ENABLE_DB:
            from app.api.v1.routes import routers as v1_routers
            from app.api.v1.routes import v1_tags
            app.include_router(v1_routers, prefix="/api/v1")
            build_docs(app, prefix="/api/v1", tags=v1_tags)

        # Voice2Text router (luôn bật, không phụ thuộc DB)
        app.include_router(voice2text_router, prefix="/api/v2")

        # Build documentation
        build_docs(app, prefix="/api/v2", tags=["voice2text"])

        return app


app = FastAPIAppSingleton.get_instance()
