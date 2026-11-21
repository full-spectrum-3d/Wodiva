from datetime import date

import numpy as np
import pandas as pd

from app.water.meteo import COLUMNS, fill_gaps


def test_fill_gaps_fills_nan_in_any_column_not_only_tmax():
    index = pd.Index([d.date() for d in pd.date_range("2024-06-01", "2024-06-10")], name="date")
    frame = pd.DataFrame({col: np.full(len(index), 10.0) for col in COLUMNS}, index=index)
    frame.loc[date(2024, 6, 4), "precip_mm"] = np.nan
    frame.loc[date(2024, 6, 6), "rs_mj"] = np.nan
    full, missing = fill_gaps(frame, index[0], index[-1])
    assert missing == 2
    assert not full[COLUMNS].isna().any().any()
    assert full.loc[date(2024, 6, 4), "precip_mm"] == 0.0
