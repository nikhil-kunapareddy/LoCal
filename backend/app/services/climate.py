"""Climate-risk data aggregation: geocode -> fan out to sources -> assemble report.

Orchestrates the external data ``ClimateSource`` components behind one ``get()``
call. ``ClimateService`` is a plain object with no web-framework dependency, so it
can be unit-tested or driven from a script as easily as from the FastAPI service.

Each source maps one upstream API to a small, stable dict; the service fans them
out concurrently and tolerates partial failure — a single dead source degrades to
``{"error": ...}`` in its slot instead of failing the whole report.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import logging
from dataclasses import dataclass
from typing import Any, List, Optional, Protocol, Sequence

from ..config import Settings, get_settings
from ..http_client import fetch_json

logger = logging.getLogger("climate")

JSON = dict[str, Any]

# Bounding box for the contiguous United States (matches the original TS guard).
_US_LAT_MIN, _US_LAT_MAX = 24.0, 50.0
_US_LNG_MIN, _US_LNG_MAX = -125.0, -66.0

_HIGH_RISK_FLOOD_ZONES = ("A", "AE", "AH", "AO", "AR", "A99", "V", "VE")
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


class CoordinateError(ValueError):
    """Raised for malformed or out-of-range coordinates."""


@dataclass
class Location:
    """A resolved county for a coordinate, or ``None`` fields when unresolved.

    ``state`` is the two-letter code used to look up state-level energy prices.
    """

    state: Optional[str] = None
    state_fips: Optional[str] = None
    county_fips: Optional[str] = None
    county_name: Optional[str] = None


# --------------------------------------------------------------------------- #
# Source interface                                                            #
# --------------------------------------------------------------------------- #
class ClimateSource(Protocol):
    """A single coordinate-keyed external data source.

    ``key`` is the report field this source populates; ``label`` names it in error
    envelopes when ``fetch`` raises.
    """

    key: str
    label: str

    async def fetch(self, lat: float, lng: float) -> JSON:
        ...


# --------------------------------------------------------------------------- #
# Concrete sources                                                            #
# --------------------------------------------------------------------------- #
class ReverseGeocoder:
    """U.S. Census geocoder — resolves a coordinate to its county."""

    async def locate(self, lat: float, lng: float) -> Optional[Location]:
        url = (
            "https://geocoding.geo.census.gov/geocoder/geographies/coordinates"
            f"?x={lng}&y={lat}&benchmark=Public_AR_Current&vintage=Current_Vintages"
            "&layers=Counties&format=json"
        )
        data = await fetch_json(url)
        counties = (((data or {}).get("result") or {}).get("geographies") or {}).get("Counties") or []
        county = counties[0] if counties else None
        if not county:
            return None
        return Location(
            state=county.get("STUSAB"),
            state_fips=county.get("STATE"),
            county_fips=county.get("COUNTY"),
            county_name=county.get("BASENAME"),
        )


class FloodRiskSource:
    """FEMA National Flood Hazard Layer — flood zone for a coordinate."""

    key = "floodRisk"
    label = "FEMA NFHL"

    async def fetch(self, lat: float, lng: float) -> JSON:
        url = (
            "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query"
            f"?geometry={lng},{lat}"
            "&geometryType=esriGeometryPoint"
            "&inSR=4326"
            "&spatialRel=esriSpatialRelIntersects"
            "&outFields=FLD_ZONE,ZONE_SUBTY,SFHA_TF,STATIC_BFE"
            "&returnGeometry=false"
            "&f=json"
        )
        data = await fetch_json(url)
        features = (data or {}).get("features") or []
        feature = (features[0] or {}).get("attributes") if features else None
        if not feature:
            return {"zone": "Unknown", "isHighRisk": False, "sfha": False}

        zone = feature.get("FLD_ZONE") or ""
        is_high_risk = any(str(zone).startswith(z) for z in _HIGH_RISK_FLOOD_ZONES)
        return {
            "zone": feature.get("FLD_ZONE") or "Unknown",
            "zoneSubtype": feature.get("ZONE_SUBTY"),
            "sfha": feature.get("SFHA_TF") == "T",
            "isHighRisk": is_high_risk,
            "baseFloodElevation": feature.get("STATIC_BFE"),
        }


class NationalRiskIndexSource:
    """FEMA National Risk Index — composite natural-hazard risk for a coordinate."""

    key = "naturalHazardRisk"
    label = "FEMA NRI"

    async def fetch(self, lat: float, lng: float) -> JSON:
        out_fields = (
            "RISK_SCORE,RISK_RATNG,EAL_SCORE,EAL_RATNG,WFIR_RISKS,HRCN_RISKS,TRND_RISKS,"
            "ERQK_RISKS,HWAV_RISKS,DRGT_RISKS,LNDS_RISKS,RFLD_RISKS,SWND_RISKS,CFLD_RISKS,"
            "AVLN_RISKS,VLCN_RISKS,TSUN_RISKS,LTNG_RISKS,WNTW_RISKS,HAIL_RISKS,ISTM_RISKS"
        )
        url = (
            "https://services.arcgis.com/XG15cJAlne2vxtgt/arcgis/rest/services/NRI_CT/FeatureServer/0/query"
            f"?geometry={lng},{lat}"
            "&geometryType=esriGeometryPoint"
            "&inSR=4326"
            "&spatialRel=esriSpatialRelIntersects"
            f"&outFields={out_fields}"
            "&returnGeometry=false&f=json"
        )
        data = await fetch_json(url)
        features = (data or {}).get("features") or []
        a = (features[0] or {}).get("attributes") if features else None
        if not a:
            return {"error": "No NRI data for this location"}
        return {
            "overallRiskScore": a.get("RISK_SCORE"),
            "overallRiskRating": a.get("RISK_RATNG"),
            "expectedAnnualLoss": a.get("EAL_SCORE"),
            "expectedAnnualLossRating": a.get("EAL_RATNG"),
            "hazards": {
                "wildfire": a.get("WFIR_RISKS"),
                "hurricane": a.get("HRCN_RISKS"),
                "tornado": a.get("TRND_RISKS"),
                "earthquake": a.get("ERQK_RISKS"),
                "heatWave": a.get("HWAV_RISKS"),
                "drought": a.get("DRGT_RISKS"),
                "landslide": a.get("LNDS_RISKS"),
                "riverineFlooding": a.get("RFLD_RISKS"),
                "strongWind": a.get("SWND_RISKS"),
                "coastalFlooding": a.get("CFLD_RISKS"),
                "avalanche": a.get("AVLN_RISKS"),
                "volcano": a.get("VLCN_RISKS"),
                "tsunami": a.get("TSUN_RISKS"),
                "lightning": a.get("LTNG_RISKS"),
                "winterWeather": a.get("WNTW_RISKS"),
                "hail": a.get("HAIL_RISKS"),
                "icestorm": a.get("ISTM_RISKS"),
            },
        }


class AirQualitySource:
    """World Air Quality Index — AQI and pollutant breakdown for a coordinate."""

    key = "airQuality"
    label = "WAQI"

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()

    async def fetch(self, lat: float, lng: float) -> JSON:
        token = self.settings.waqi_token
        if not token:
            return {"error": "WAQI_TOKEN not configured"}
        url = f"https://api.waqi.info/feed/geo:{lat};{lng}/?token={token}"
        data = await fetch_json(url)
        if data.get("status") != "ok":
            return {"error": data.get("data") or "WAQI error"}

        d = data.get("data") or {}
        iaqi = d.get("iaqi") or {}

        def pick(key: str) -> Any:
            v = iaqi.get(key)
            if v is None:
                return None
            return v.get("v") if isinstance(v, dict) else v

        city = d.get("city") or {}
        time_block = d.get("time") or {}
        return {
            "aqi": d.get("aqi"),
            "dominantPollutant": d.get("dominantpol"),
            "stationName": city.get("name"),
            "updatedAt": time_block.get("s"),
            "pollutants": {
                "pm25": pick("pm25"),
                "pm10": pick("pm10"),
                "no2": pick("no2"),
                "o3": pick("o3"),
                "so2": pick("so2"),
                "co": pick("co"),
            },
        }


class SolarPotentialSource:
    """NREL PVWatts — modeled annual/monthly solar production for a coordinate."""

    key = "solarPotential"
    label = "NREL PVWatts"

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()

    async def fetch(self, lat: float, lng: float) -> JSON:
        params = {
            "api_key": self.settings.nrel_api_key,
            "lat": str(lat),
            "lon": str(lng),
            "system_capacity": "4",
            "azimuth": "180",
            "tilt": "20",
            "array_type": "1",
            "module_type": "0",
            "losses": "14",
            "dataset": "nsrdb",
        }
        query = "&".join(f"{k}={v}" for k, v in params.items())
        # NOTE: corrected host — the original TS source had a typo ("developer.nlr.gov").
        data = await fetch_json(f"https://developer.nrel.gov/api/pvwatts/v8.json?{query}")
        if data.get("errors"):
            return {"error": ", ".join(data["errors"])}

        out = data.get("outputs") or {}
        ac_monthly = out.get("ac_monthly") or [0] * 12
        return {
            "annualKwh": round(out.get("ac_annual", 0)),
            "monthlyKwh": [
                {"month": m, "kwh": round(ac_monthly[i])} for i, m in enumerate(_MONTHS)
            ],
            "estimatedAnnualSavings": round(out.get("ac_annual", 0) * 0.16),
        }


class WeatherForecastSource:
    """Open-Meteo — 7-day daily forecast for a coordinate."""

    key = "weatherForecast"
    label = "Open-Meteo"

    async def fetch(self, lat: float, lng: float) -> JSON:
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lng}"
            "&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,"
            "windspeed_10m_max,uv_index_max,weathercode"
            "&temperature_unit=fahrenheit&windspeed_unit=mph&precipitation_unit=inch"
            "&timezone=auto&forecast_days=7"
        )
        data = await fetch_json(url)
        d = data.get("daily") or {}
        times = d.get("time") or []
        return {
            "timezone": data.get("timezone"),
            "forecast": [
                {
                    "date": date,
                    "tempMaxF": d["temperature_2m_max"][i],
                    "tempMinF": d["temperature_2m_min"][i],
                    "precipitationIn": d["precipitation_sum"][i],
                    "maxWindMph": d["windspeed_10m_max"][i],
                    "uvIndex": d["uv_index_max"][i],
                    "weatherCode": d["weathercode"][i],
                }
                for i, date in enumerate(times)
            ],
        }


class EnergyPriceSource:
    """EIA — latest residential electricity price for a state.

    Keyed by state (not coordinate), so it is wired in by the service after
    geocoding rather than listed among the coordinate ``sources``.
    """

    key = "energyPrice"
    label = "EIA"

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()

    async def fetch_for_state(self, state_code: str) -> JSON:
        api_key = self.settings.eia_api_key
        if not api_key:
            return {"error": "EIA_API_KEY not configured"}
        url = (
            "https://api.eia.gov/v2/electricity/retail-sales/data"
            f"?api_key={api_key}&data[]=price&facets[sectorid][]=RES"
            f"&facets[stateid][]={state_code}&frequency=monthly"
            "&sort[0][column]=period&sort[0][direction]=desc&length=12"
        )
        data = await fetch_json(url)
        results = ((data or {}).get("response") or {}).get("data") or []
        if not results:
            return {"error": "No EIA data for this state"}
        return {
            "state": state_code,
            "latestPeriod": results[0].get("period"),
            "pricePerKwh": float(results[0].get("price")),
        }


# --------------------------------------------------------------------------- #
# Orchestrator                                                                #
# --------------------------------------------------------------------------- #
def _default_sources(settings: Settings) -> List[ClimateSource]:
    """The coordinate-keyed sources fanned out on every request."""
    return [
        FloodRiskSource(),
        NationalRiskIndexSource(),
        AirQualitySource(settings),
        SolarPotentialSource(settings),
        WeatherForecastSource(),
    ]


class ClimateService:
    """Wires the geocoder and data sources into one climate-report flow."""

    def __init__(
        self,
        sources: Optional[Sequence[ClimateSource]] = None,
        geocoder: Optional[ReverseGeocoder] = None,
        energy_source: Optional[EnergyPriceSource] = None,
        settings: Optional[Settings] = None,
    ):
        self.settings = settings or get_settings()
        self.sources = list(sources) if sources is not None else _default_sources(self.settings)
        self.geocoder = geocoder or ReverseGeocoder()
        self.energy_source = energy_source or EnergyPriceSource(self.settings)

    async def get(self, lat: float, lng: float) -> JSON:
        """Validate, geocode, fan out to sources, and assemble the report."""
        if not _is_finite(lat) or not _is_finite(lng):
            raise CoordinateError("Invalid coordinates. Provide lat/lng numbers.")
        if not (_US_LAT_MIN <= lat <= _US_LAT_MAX and _US_LNG_MIN <= lng <= _US_LNG_MAX):
            raise CoordinateError("Coordinates appear outside contiguous United States.")

        location = await self._locate(lat, lng)

        energy_task = (
            self.energy_source.fetch_for_state(location.state)
            if location and location.state
            else _resolved({"error": "No state resolved"})
        )
        outcomes = await asyncio.gather(
            *(source.fetch(lat, lng) for source in self.sources),
            energy_task,
            return_exceptions=True,
        )
        *source_outcomes, energy_outcome = outcomes

        report: JSON = {"meta": self._meta(lat, lng, location)}
        for source, outcome in zip(self.sources, source_outcomes):
            report[source.key] = _unwrap(outcome, source.label)
        report[self.energy_source.key] = _unwrap(energy_outcome, self.energy_source.label)
        report.update(self._stub_sections())
        return report

    async def _locate(self, lat: float, lng: float) -> Optional[Location]:
        """Geocoding is best-effort; downstream tolerates ``None``."""
        try:
            return await self.geocoder.locate(lat, lng)
        except Exception:
            return None

    def _meta(self, lat: float, lng: float, location: Optional[Location]) -> JSON:
        return {
            "lat": lat,
            "lng": lng,
            "requestedAt": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "location": (
                {
                    "state": location.state,
                    "county": location.county_name,
                    "stateFips": location.state_fips,
                    "countyFips": location.county_fips,
                }
                if location
                else None
            ),
        }

    def _stub_sections(self) -> JSON:
        """Sections not yet wired in integrated mode; gated on configured keys."""
        s = self.settings
        return {
            "climateHistory": (
                {"note": "Not yet wired in integrated mode"}
                if s.noaa_token
                else {"error": "NOAA_TOKEN not configured"}
            ),
            "propertyPrices": (
                {"note": "Not yet wired in integrated mode"}
                if s.attom_api_key
                else {"error": "ATTOM_API_KEY not configured"}
            ),
            "housePriceIndex": (
                {"note": "Not yet wired in integrated mode"}
                if s.fred_api_key
                else {"error": "FRED_API_KEY not configured"}
            ),
            "costIntelligence": {},
        }


# --------------------------------------------------------------------------- #
# Helpers + module-level convenience entry point                              #
# --------------------------------------------------------------------------- #
def _unwrap(outcome: Any, label: str) -> JSON:
    """Turn a gathered result/exception into a value or an error envelope."""
    if isinstance(outcome, Exception):
        return {"error": f"{label} failed: {outcome}"}
    return outcome


def _is_finite(value: float) -> bool:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return False
    return f == f and f not in (float("inf"), float("-inf"))


async def _resolved(value: JSON) -> JSON:
    return value


async def get_climate_intelligence(lat: float, lng: float) -> JSON:
    """Convenience wrapper: run a default-wired :class:`ClimateService`."""
    return await ClimateService().get(lat, lng)
