from app.core.schemas import DataSource, Limitation, SoilInfo, SoilLayer
from app.water.engine.soil_hydraulics import (
    IUNG_DEFAULT_LAYERS,
    iung_category_from_texture,
    saxton_rawls,
    usda_texture,
)
from app.water.sources import iung, soilgrids

DEPTHS = [(0, 5), (5, 15), (15, 30), (30, 60), (60, 100)]
OM_PER_SOC = 1.724


def layers_from_soilgrids(raw: dict[str, dict[str, float]]) -> list[SoilLayer]:
    layers = []
    for top, bottom in DEPTHS:
        values = raw.get(f"{top}-{bottom}cm", {})
        if "sand" not in values or "clay" not in values:
            continue
        sand, clay = values["sand"], values["clay"]
        soc = values.get("soc", 1.0)
        silt = max(0.0, 100 - sand - clay)
        fc, wp = saxton_rawls(sand, clay, soc * OM_PER_SOC)
        layers.append(
            SoilLayer(
                top_cm=top,
                bottom_cm=bottom,
                sand_pct=round(sand, 1),
                silt_pct=round(silt, 1),
                clay_pct=round(clay, 1),
                soc_pct=round(soc, 2),
                theta_fc=round(fc, 3),
                theta_wp=round(wp, 3),
                awc=round(fc - wp, 3),
            )
        )
    return layers


def layers_from_category(category: str) -> list[SoilLayer]:
    sand, clay, om = IUNG_DEFAULT_LAYERS[category]
    layers = []
    for top, bottom in DEPTHS:
        om_layer = om if top < 30 else om * 0.3
        fc, wp = saxton_rawls(sand, clay, om_layer)
        layers.append(
            SoilLayer(
                top_cm=top,
                bottom_cm=bottom,
                sand_pct=sand,
                silt_pct=100 - sand - clay,
                clay_pct=clay,
                soc_pct=round(om_layer / OM_PER_SOC, 2),
                theta_fc=round(fc, 3),
                theta_wp=round(wp, 3),
                awc=round(fc - wp, 3),
            )
        )
    return layers


def weighted(layers: list[SoilLayer], attr: str, max_cm: int = 100) -> float:
    total = sum(min(layer.bottom_cm, max_cm) - layer.top_cm for layer in layers if layer.top_cm < max_cm)
    if total <= 0:
        return 0.0
    acc = sum(
        getattr(layer, attr) * (min(layer.bottom_cm, max_cm) - layer.top_cm)
        for layer in layers
        if layer.top_cm < max_cm
    )
    return acc / total


def summarize(layers: list[SoilLayer], category: str | None, category_source: str, source: str) -> SoilInfo:
    top = [layer for layer in layers if layer.top_cm < 30]
    awc_mm = sum(layer.awc * (layer.bottom_cm - layer.top_cm) * 10 for layer in layers)
    sand30, silt30, clay30 = (
        weighted(top, "sand_pct", 30),
        weighted(top, "silt_pct", 30),
        weighted(top, "clay_pct", 30),
    )
    return SoilInfo(
        layers=layers,
        texture_topsoil=usda_texture(sand30, silt30, clay30),
        iung_category=category,
        iung_category_source=category_source,
        awc_mm_100cm=round(awc_mm, 1),
        organic_matter_pct_topsoil=round(weighted(top, "soc_pct", 30) * OM_PER_SOC, 2),
        source=source,
    )


async def load(
    lat: float, lon: float, user_category: str | None = None
) -> tuple[SoilInfo, list[DataSource], list[Limitation]]:
    raw, ds = await soilgrids.query(lat, lon)
    sources = [ds, iung.data_source()]
    limitations: list[Limitation] = []
    layers = layers_from_soilgrids(raw) if raw else []
    if len(layers) >= 3:
        sand = weighted(layers, "sand_pct")
        clay = weighted(layers, "clay_pct")
        derived = iung_category_from_texture(sand, clay)
        category = user_category or derived
        cat_source = (
            "podana przez użytkownika" if user_category else "wyznaczona z uziarnienia SoilGrids wg kryteriów IUNG"
        )
        info = summarize(layers, category, cat_source, "SoilGrids")
        if user_category and user_category != derived:
            info.agreement = f"niezgodna: SoilGrids wskazuje kategorię {derived}, użytkownik {user_category}"
            info.confidence = "niska"
        else:
            info.agreement = "kategoria z SoilGrids; brak usługi IUNG do porównania punktowego"
            info.confidence = "średnia"
        limitations.append(
            Limitation(
                code="soil_resolution",
                message="Gleba z SoilGrids (siatka 250 m, model globalny) – może odbiegać od mapy glebowo-rolniczej "
                "dla konkretnej działki.",
                section="gleba",
            )
        )
        return info, sources, limitations
    category = user_category or "III"
    info = summarize(
        layers_from_category(category),
        category,
        "podana przez użytkownika" if user_category else "wartość domyślna (brak danych glebowych)",
        "kategoria IUNG" if user_category else "wartość domyślna",
    )
    info.confidence = "niska"
    limitations.append(
        Limitation(
            code="soil_missing",
            message="Brak danych SoilGrids – przyjęto typowe uziarnienie dla kategorii gleby "
            f"{category}. Wynik bilansu wody ma niską pewność.",
            severity="ostrzeżenie",
            section="gleba",
        )
    )
    return info, sources, limitations
