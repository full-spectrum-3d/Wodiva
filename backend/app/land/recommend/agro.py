from __future__ import annotations

from typing import Any

from app.land.models import Level, Recommendation
from app.land.recommend.rules import apply


def recommend(context: dict[str, Any], confidence: Level) -> list[Recommendation]:
    return apply(context, "agrotechnika", {}, confidence)
