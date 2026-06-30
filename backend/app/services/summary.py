"""Dashboard summaries: reduce a climate-intelligence payload to a small report.

Each ``SummaryBuilder`` maps the full climate report to one dashboard's headline
numbers. Builders are plain objects with no web-framework dependency, so they can
be unit-tested or driven from a script as easily as from the FastAPI service.

Python port of the former ``toConsumerSummary`` / ``toBusinessSummary`` in
``frontend/src/lib/server/climateIntel.ts``.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol

JSON = dict[str, Any]

# Consumer composite-score weighting (must sum to 1.0).
_FLOOD_WEIGHT = 0.4
_AIR_WEIGHT = 0.3
_HAZARD_WEIGHT = 0.3


def _as_number(value: Any) -> Optional[float]:
    if isinstance(value, bool):  # bool is an int subclass; exclude it
        return None
    if isinstance(value, (int, float)):
        f = float(value)
        return f if f == f and f not in (float("inf"), float("-inf")) else None
    return None


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


class SummaryBuilder(Protocol):
    """Derives one dashboard's summary dict from a climate-intelligence payload."""

    def build(self, payload: JSON) -> JSON:
        ...


class ConsumerSummaryBuilder:
    """Consumer dashboard: a composite risk score and a flood/air/other split."""

    def build(self, payload: JSON) -> JSON:
        flood_risk = payload.get("floodRisk") or {}
        air_quality = payload.get("airQuality") or {}
        natural_hazard = payload.get("naturalHazardRisk") or {}

        is_high_risk = flood_risk.get("isHighRisk") is True
        flood_zone = flood_risk.get("zone") if isinstance(flood_risk.get("zone"), str) else "Unknown"

        aqi = _as_number(air_quality.get("aqi"))
        overall_risk_score = _as_number(natural_hazard.get("overallRiskScore"))

        flood_score = 85 if is_high_risk else (20 if flood_zone == "X" else 50)
        air_score = 50 if aqi is None else _clamp(aqi, 0, 100)
        hazard_score = 50 if overall_risk_score is None else _clamp(overall_risk_score, 0, 100)

        composite = round(
            flood_score * _FLOOD_WEIGHT + air_score * _AIR_WEIGHT + hazard_score * _HAZARD_WEIGHT
        )

        flood_pct = 35 if is_high_risk else 25
        air_pct = 35 if air_score >= 70 else 30
        other_pct = 100 - flood_pct - air_pct

        return {
            "composite_score": composite,
            "flood_pct": flood_pct,
            "air_operational_pct": air_pct,
            "other_pct": other_pct,
            "meta": {
                "flood_zone": flood_zone,
                "aqi": aqi,
                "hazard_score": overall_risk_score,
            },
        }


class BusinessSummaryBuilder:
    """Institutional dashboard: risk tier and exposure metrics."""

    def build(self, payload: JSON) -> JSON:
        flood_risk = payload.get("floodRisk") or {}
        natural_hazard = payload.get("naturalHazardRisk") or {}

        risk_rating = natural_hazard.get("overallRiskRating")
        risk_tier = risk_rating if isinstance(risk_rating, str) else "Moderate"
        properties_at_risk_pct = 42.5 if flood_risk.get("isHighRisk") is True else 21.0
        flood_zone_pct = 18.2 if flood_risk.get("sfha") is True else 8.0
        infra_stress = _as_number(natural_hazard.get("expectedAnnualLoss"))
        infra_stress_score = 5.5 if infra_stress is None else _clamp(infra_stress / 10, 1, 10)

        return {
            "risk_tier": risk_tier,
            "properties_at_risk_pct": round(properties_at_risk_pct, 1),
            "flood_zone_pct": round(flood_zone_pct, 1),
            "infra_stress_score": round(infra_stress_score, 1),
            # TODO(demo): replace with real source (roadmap item D6).
            "rate_increase_5y_pct": 114,
            "carriers_reducing": {"count": 12, "of": 18},
        }


def to_consumer_summary(payload: JSON) -> JSON:
    """Convenience wrapper: run a default :class:`ConsumerSummaryBuilder`."""
    return ConsumerSummaryBuilder().build(payload)


def to_business_summary(payload: JSON) -> JSON:
    """Convenience wrapper: run a default :class:`BusinessSummaryBuilder`."""
    return BusinessSummaryBuilder().build(payload)
