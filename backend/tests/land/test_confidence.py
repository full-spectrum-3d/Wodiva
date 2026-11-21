from app.land import confidence


def test_short_meteo_history_lowers_water_confidence(water, soil):
    full = confidence.water_section(water, soil)
    assert len(water.climate.years_analyzed) >= confidence.MIN_RELIABLE_YEARS
    short_climate = water.climate.model_copy(update={"years_analyzed": water.climate.years_analyzed[-1:]})
    short = confidence.water_section(water.model_copy(update={"climate": short_climate}), soil)
    assert short.score <= full.score - 0.39
    assert any("krótka historia" in r for r in short.reasons)
