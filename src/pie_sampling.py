from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .sampling_common import (
    choose_window,
    position_groups,
    sample_positions,
    sampling_metadata,
)


def _cap_visible_slices(series: pd.Series, count: int) -> pd.Series | None:
    values = series[series > 0].sort_values(ascending=False)
    if len(values) < 2:
        return None
    count = max(2, min(int(count), len(values)))
    if len(values) <= count:
        return values
    keep = max(1, count - 1)
    visible = values.head(keep).copy()
    remainder = float(values.iloc[keep:].sum())
    if remainder > 0:
        visible.loc["Other"] = remainder
    return visible


def sample_pie_data_from_df(
    df: pd.DataFrame,
    spec: dict[str, Any],
    rng: np.random.Generator,
    style: dict[str, Any],
    min_total: float = 1.0,
) -> tuple[pd.DataFrame, dict[str, Any]] | None:
    """Aggregate a deterministic no-replacement source-row sample into slices."""
    numeric_cols = [column for column in spec.get("numeric_cols", []) if column in df]
    group_cols = [column for column in spec.get("group_cols", []) if column in df]
    if not numeric_cols or not group_cols:
        return None
    value_col = str(rng.choice(numeric_cols))
    slice_count = max(2, int(style.get("slice_count", 5)))

    if {"BOROUGH", "SECTOR", "YEAR", "EMPLOYEE_JOBS"}.issubset(df.columns):
        strategy = str(
            rng.choice(
                ["sector_totals", "borough_totals", "sector_year", "borough_year"],
                p=[0.30, 0.30, 0.20, 0.20],
            )
        )
        category_col = "SECTOR" if strategy.startswith("sector") else "BOROUGH"
        period_cols = ["YEAR"]
        window_sizes = [1] if strategy.endswith("year") else [3, 5, 10, 20]
    elif {"BOROUGH", "YEAR", "MONTH"}.issubset(df.columns):
        strategy = str(
            rng.choice(
                ["by_borough", "by_vehicle_type", "by_borough_year", "by_vehicle_type_year"],
                p=[0.30, 0.30, 0.20, 0.20],
            )
        )
        category_col = (
            "VEHICLE TYPE CODE 1" if "vehicle_type" in strategy else "BOROUGH"
        )
        if category_col not in df.columns:
            return None
        period_cols = ["YEAR", "MONTH"]
        window_sizes = [12] if strategy.endswith("year") else [3, 6, 12, 24]
    else:
        category_col = str(rng.choice(group_cols))
        strategy = str(
            rng.choice(["group", "time_window", "filtered_group"], p=[0.40, 0.35, 0.25])
        )
        date_col = spec.get("date_col")
        if date_col and date_col in df.columns:
            period_cols = [date_col]
        else:
            period_cols = [column for column in spec.get("agg_cols", []) if column in df]
        if not period_cols:
            return None
        window_sizes = [1, 3, 6, 12] if strategy != "group" else [3, 6, 12, 24]

    groups = position_groups(
        df,
        period_cols,
        positive_columns=[value_col],
        non_null_columns=[category_col],
    )
    minimum_rows = max(8, slice_count * 2)
    window = choose_window(groups, rng, window_sizes, minimum_rows=minimum_rows)
    if window is None:
        return None
    candidates, filters = window
    selected = sample_positions(
        candidates,
        rng,
        minimum_rows=minimum_rows,
        maximum_rows=2500,
    )
    if selected is None:
        return None

    sampled = df.iloc[selected][[category_col, value_col]].copy()
    sampled[value_col] = pd.to_numeric(sampled[value_col], errors="coerce")
    sampled = sampled.dropna(subset=[category_col, value_col])
    series = sampled.groupby(category_col, observed=True)[value_col].sum(min_count=1)
    visible = _cap_visible_slices(series, slice_count)
    if visible is None:
        return None
    total = float(visible.sum())
    if total <= min_total or float(visible.max() / total) >= 0.995:
        return None

    plot_df = visible.rename(value_col).reset_index()
    plot_df.columns = [category_col, value_col]
    context: dict[str, Any] = {
        "value_col": value_col,
        "category_col": category_col,
        "strategy": strategy,
        "n_slices": int(len(plot_df)),
        "total": total,
        "has_other_category": bool("Other" in plot_df[category_col].astype(str).values),
        "requested_slice_count": slice_count,
        "sampling": sampling_metadata(
            df,
            candidates,
            selected,
            filters,
            eligibility=f"{value_col} > 0 and {category_col} is not null",
        ),
    }
    return plot_df, context
