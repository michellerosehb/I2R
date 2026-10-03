from __future__ import annotations

from typing import Any, Sequence

import numpy as np
import pandas as pd

from .sampling_common import (
    choose_window,
    position_groups,
    sample_positions,
    sampling_metadata,
)


def _period_labels(frame: pd.DataFrame, columns: Sequence[str]) -> pd.Series:
    labels = frame[columns[0]].astype(str)
    for column in columns[1:]:
        component = frame[column].astype(str)
        if column.upper() == "MONTH":
            component = component.str.zfill(2)
        labels = labels + "-" + component
    return labels


def sample_line_data_from_df(
    df: pd.DataFrame,
    spec: dict[str, Any],
    rng: np.random.Generator,
    style: dict[str, Any],
    min_points: int = 3,
) -> tuple[pd.DataFrame, dict[str, Any]] | None:
    """Build ordered line series from sampled source rows without replacement."""
    numeric_cols = [column for column in spec.get("numeric_cols", []) if column in df]
    agg_cols = [column for column in spec.get("agg_cols", []) if column in df]
    group_cols = [column for column in spec.get("group_cols", []) if column in df]
    if not numeric_cols or not agg_cols:
        return None

    y_col = str(rng.choice(numeric_cols))
    requested_lines = max(1, int(style.get("n_lines", 1)))
    strategy = str(rng.choice(["time", "group_series"])) if group_cols else "time"
    group_col = str(rng.choice(group_cols)) if strategy == "group_series" else None

    if agg_cols == ["YEAR"]:
        window_sizes = [6, 10, 15, 25]
    else:
        window_sizes = [6, 12, 18, 24, 36]
    indexes = position_groups(
        df,
        agg_cols,
        positive_columns=[y_col],
        non_null_columns=[group_col] if group_col else [],
    )
    minimum_source_rows = max(12, min_points * max(1, requested_lines) * 2)
    window = choose_window(
        indexes, rng, window_sizes, minimum_rows=minimum_source_rows
    )
    if window is None:
        return None
    candidates, filters = window
    selected = sample_positions(
        candidates,
        rng,
        minimum_rows=minimum_source_rows,
        maximum_rows=3000,
    )
    if selected is None:
        return None

    columns = list(agg_cols) + [y_col]
    if group_col:
        columns.append(group_col)
    sampled = df.iloc[selected][columns].copy()
    sampled[y_col] = pd.to_numeric(sampled[y_col], errors="coerce")
    sampled = sampled.dropna(subset=list(agg_cols) + [y_col])

    if group_col:
        totals = (
            sampled.groupby(group_col, observed=True)[y_col]
            .sum()
            .sort_values(ascending=False)
        )
        chosen_groups = totals.head(requested_lines).index.tolist()
        grouped = (
            sampled[sampled[group_col].isin(chosen_groups)]
            .groupby(list(agg_cols) + [group_col], observed=True)[y_col]
            .sum()
            .rename("y")
            .reset_index()
        )
        valid_groups = [
            value
            for value, part in grouped.groupby(group_col, observed=True)
            if part[list(agg_cols)].drop_duplicates().shape[0] >= min_points
        ]
        grouped = grouped[grouped[group_col].isin(valid_groups)]
        if grouped.empty:
            return None
        grouped["series"] = grouped[group_col].astype(str)
        plot_df = grouped
    else:
        plot_df = (
            sampled.groupby(list(agg_cols), observed=True)[y_col]
            .sum()
            .rename("y")
            .reset_index()
        )
        plot_df["series"] = "Series 1"

    plot_df = plot_df.sort_values(list(agg_cols) + ["series"]).reset_index(drop=True)
    periods = (
        plot_df[list(agg_cols)]
        .drop_duplicates()
        .sort_values(list(agg_cols))
        .reset_index(drop=True)
    )
    if len(periods) < min_points or plot_df["y"].nunique() < 2:
        return None
    periods["x"] = np.arange(len(periods), dtype=float)
    periods["x_label"] = _period_labels(periods, agg_cols)
    plot_df = plot_df.merge(periods, on=list(agg_cols), how="inner")

    context: dict[str, Any] = {
        "x_label": "Time period",
        "y_label": y_col.replace("_", " ").title(),
        "n_lines": int(plot_df["series"].nunique()),
        "x_tick_positions": periods["x"].tolist(),
        "x_tick_labels": periods["x_label"].tolist(),
        "x_axis_month_day_labels": 0,
        "strategy": strategy,
        "source_agg_cols": list(agg_cols),
        "value_col": y_col,
        "sampling": sampling_metadata(
            df,
            candidates,
            selected,
            filters,
            eligibility=f"{y_col} > 0 and time fields are not null",
        ),
    }
    if group_col:
        context["group_col"] = group_col
    return plot_df.reset_index(drop=True), context
