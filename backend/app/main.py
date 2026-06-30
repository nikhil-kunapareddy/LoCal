"""FastAPI application for the Climate Risk Intelligence backend.

This is the single source of truth for climate-risk data: it owns the external
integrations (FEMA, NRI, WAQI, NREL, EIA, Open-Meteo, ...) and the dashboard
summary derivations. The Next.js frontend reaches it through a same-origin proxy,
so this service stays private and never exposes API keys to the browser.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .config import get_settings
from .http_client import close_client
from .logging_config import configure_logging

logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings = get_settings()
    missing = settings.missing_optional_keys()
    if missing:
        logger.warning("startup.degraded_mode", extra={"missing_keys": missing})
    else:
        logger.info("startup.all_keys_present")
    yield
    await close_client()


app = FastAPI(
    title="Climate Risk Intelligence API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().allowed_origin_list,
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(router)
