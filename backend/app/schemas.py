"""Pydantic response models for the public API contract."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str


class ConsumerSummaryMeta(BaseModel):
    flood_zone: str
    aqi: Optional[float] = None
    hazard_score: Optional[float] = None


class ConsumerSummary(BaseModel):
    composite_score: int
    flood_pct: int
    air_operational_pct: int
    other_pct: int
    meta: ConsumerSummaryMeta


class CarriersReducing(BaseModel):
    count: int
    of: int


class BusinessSummary(BaseModel):
    risk_tier: str
    properties_at_risk_pct: float
    flood_zone_pct: float
    infra_stress_score: float
    rate_increase_5y_pct: int
    carriers_reducing: CarriersReducing


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
