from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from app.core.schemas import (
    Cause,
    Confidence,
    DataSource,
    HydroInfo,
    IrrigationAdvice,
    Limitation,
    Parcel,
    Recommendation,
    Report,
    SatelliteState,
    SoilInfo,
    TerrainInfo,
    WaterState,
)


@dataclass
class LandObservation:
    satellite: SatelliteState | None = None
    terrain: TerrainInfo | None = None
    hydro: HydroInfo | None = None
    sources: list[DataSource] = field(default_factory=list)
    limitations: list[Limitation] = field(default_factory=list)


@dataclass
class LandInterpretation:
    causes: list[Cause] = field(default_factory=list)
    recommendations: list[Recommendation] = field(default_factory=list)
    confidence: list[Confidence] = field(default_factory=list)
    limitations: list[Limitation] = field(default_factory=list)


@dataclass
class ReportInput:
    parcel: Parcel
    analysis_date: date
    crop: str
    water: WaterState | None
    soil: SoilInfo | None
    irrigation: IrrigationAdvice | None
    land: LandObservation
    interpretation: LandInterpretation
    sources: list[DataSource]
    limitations: list[Limitation]
    timings_s: dict[str, float]


class LandService(Protocol):
    async def observe(self, parcel: Parcel, analysis_date: date, crop: str) -> LandObservation: ...

    def interpret(
        self,
        parcel: Parcel,
        water: WaterState,
        soil: SoilInfo,
        irrigation: IrrigationAdvice,
        land: LandObservation,
    ) -> LandInterpretation: ...


class ReportBuilder(Protocol):
    def build(self, data: ReportInput) -> Report: ...
