import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def sample_payload() -> dict:
    """A representative climate-intelligence payload for transformer tests."""
    return {
        "floodRisk": {"zone": "AE", "isHighRisk": True, "sfha": True},
        "airQuality": {"aqi": 80},
        "naturalHazardRisk": {
            "overallRiskScore": 60,
            "overallRiskRating": "Relatively High",
            "expectedAnnualLoss": 70,
        },
    }
