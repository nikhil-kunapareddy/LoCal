"""Unit tests for the pure transformers and the summary routes (climate mocked)."""

import app.api.routes as routes
from app.services.summary import to_business_summary, to_consumer_summary


# --------------------------------------------------------------------------- #
# Pure transformer logic — no network                                          #
# --------------------------------------------------------------------------- #
def test_consumer_summary_high_risk(sample_payload):
    out = to_consumer_summary(sample_payload)
    # flood_score=85*0.4 + air(80)*0.3 + hazard(60)*0.3 = 34 + 24 + 18 = 76
    assert out["composite_score"] == 76
    assert out["flood_pct"] == 35  # isHighRisk
    assert out["air_operational_pct"] == 35  # air_score >= 70
    assert out["other_pct"] == 30
    assert out["meta"]["flood_zone"] == "AE"
    assert out["meta"]["aqi"] == 80


def test_consumer_summary_defaults_on_empty():
    out = to_consumer_summary({})
    # flood 50*0.4 + air 50*0.3 + hazard 50*0.3 = 50
    assert out["composite_score"] == 50
    assert out["flood_pct"] == 25
    assert out["air_operational_pct"] == 30
    assert out["meta"]["flood_zone"] == "Unknown"


def test_business_summary_high_risk(sample_payload):
    out = to_business_summary(sample_payload)
    assert out["risk_tier"] == "Relatively High"
    assert out["properties_at_risk_pct"] == 42.5
    assert out["flood_zone_pct"] == 18.2
    assert out["infra_stress_score"] == 7.0  # 70/10 clamped to [1,10]
    assert out["carriers_reducing"] == {"count": 12, "of": 18}


def test_business_summary_defaults_on_empty():
    out = to_business_summary({})
    assert out["risk_tier"] == "Moderate"
    assert out["properties_at_risk_pct"] == 21.0
    assert out["infra_stress_score"] == 5.5


# --------------------------------------------------------------------------- #
# Routes — climate service mocked so no external calls happen                  #
# --------------------------------------------------------------------------- #
async def _fake_climate(lat, lng):
    return {
        "floodRisk": {"zone": "X", "isHighRisk": False, "sfha": False},
        "airQuality": {"aqi": 42},
        "naturalHazardRisk": {"overallRiskScore": 30, "overallRiskRating": "Low"},
    }


def test_summary_consumer_route(client, monkeypatch):
    monkeypatch.setattr(routes, "get_climate_intelligence", _fake_climate)
    res = client.get("/api/summary/consumer?lat=42.36&lng=-71.05")
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {
        "composite_score",
        "flood_pct",
        "air_operational_pct",
        "other_pct",
        "meta",
    }


def test_summary_business_route(client, monkeypatch):
    monkeypatch.setattr(routes, "get_climate_intelligence", _fake_climate)
    res = client.get("/api/summary/business?lat=42.36&lng=-71.05")
    assert res.status_code == 200
    assert res.json()["risk_tier"] == "Low"


def test_bad_coordinates_returns_400(client):
    # Outside contiguous US -> CoordinateError -> 400.
    res = client.get("/api/summary/consumer?lat=0&lng=0")
    assert res.status_code == 400
    assert "error" in res.json()
