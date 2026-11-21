from __future__ import annotations

from typing import Any

from app.land.models import GeoFeature, LandResult, Level, Recommendation
from app.land.recommend.rules import apply


def locations(land: LandResult) -> dict[str, GeoFeature]:
    out: dict[str, GeoFeature] = {}
    if land.terrain is None:
        return out
    depressions = [
        f
        for f in land.terrain.features
        if f.kind == "zagłębienie" and f.properties.get("inside_parcel_share", 0) >= 0.5
    ]
    if depressions:
        out["depression"] = max(depressions, key=lambda f: f.properties["volume_m3"])
    channels = [f for f in land.terrain.features if f.kind == "linia spływu"]
    if channels:
        out["channel"] = max(channels, key=lambda f: f.properties["max_contributing_area_ha"])
    return out


def recommend(context: dict[str, Any], land: LandResult, confidence: Level) -> list[Recommendation]:
    return apply(context, "retencja", locations(land), confidence)
