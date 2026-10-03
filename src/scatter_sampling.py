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


def _point_target(rng: np.random.Generator, code: int) -> int:
    mapping = {0: (6, 11), 1: (10, 21), 2: (20, 31), 3: (30, 61), 6: (30, 61)}
    low, high = mapping.get(int(code), (10, 21))
    return int(rng.integers(low, high))


def _decorate_points(
    plot_df: pd.DataFrame,
    context: dict[str, Any],
    style: dict[str, Any],
    rng: np.random.Generator,
) -> tuple[pd.DataFrame, dict[str, Any]] | None:
    plot_df = plot_df.replace([np.inf, -np.inf], np.nan).dropna(subset=["x", "y"])
    if len(plot_df) < 3 or plot_df["x"].nunique() < 2 or plot_df["y"].nunique() < 2:
        return None
    plot_df = plot_df.reset_index(drop=True)

    requested_groups = max(1, min(int(style.get("n_groups", 1)), len(plot_df)))
    if requested_groups > 1:
        try:
            plot_df["group"] = pd.qcut(
                plot_df["x"],
                q=requested_groups,
                labels=[f"Group {index + 1}" for index in range(requested_groups)],
                duplicates="drop",
            ).astype(str)
        except Exception:
            plot_df["group"] = "Group 1"
    else:
        plot_df["group"] = "Group 1"

    actual_groups = plot_df["group"].drop_duplicates().tolist()
    n_colors = max(1, min(int(style.get("n_colors", 1)), len(actual_groups)))
    n_shapes = max(1, min(int(style.get("n_shapes", 1)), len(actual_groups)))
    color_map = {
        group: f"Color {index % n_colors + 1}"
        for index, group in enumerate(actual_groups)
    }
    shape_map = {
        group: f"Shape {index % n_shapes + 1}"
        for index, group in enumerate(actual_groups)
    }
    plot_df["color_group"] = plot_df["group"].map(color_map)
    plot_df["shape_group"] = plot_df["group"].map(shape_map)
    plot_df["show_label"] = False
    label_code = int(style.get("direct_labels", 0))
    if label_code == 1:
        plot_df["show_label"] = True
    elif label_code == 2:
        count = min(max(3, int(round(len(plot_df) * 0.30))), len(plot_df))
        chosen = rng.choice(plot_df.index.to_numpy(), size=count, replace=False)
        plot_df.loc[chosen, "show_label"] = True

    context.update(
        {
            "n_points": int(len(plot_df)),
            "n_groups": int(plot_df["group"].nunique()),
            "orientation": int(style.get("scatter_orientation", 1)),
            "x_range": [float(plot_df["x"].min()), float(plot_df["x"].max())],
            "y_range": [float(plot_df["y"].min()), float(plot_df["y"].max())],
        }
    )
    return plot_df, context


def _direct_scatter(
    df: pd.DataFrame,
    spec: dict[str, Any],
    rng: np.random.Generator,
    style: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]] | None:
    numeric = [column for column in spec.get("numeric_cols", []) if column in df]
    if len(numeric) < 2:
        return None
    x_col, y_col = rng.choice(numeric, size=2, replace=False).tolist()
    target = _point_target(rng, int(style.get("n_points_bin", 3)))

    date_col = spec.get("date_col")
    if date_col and date_col in df.columns and date_col != "CRASH DATE":
        period_cols = [date_col]
    elif {"YEAR", "MONTH"}.issubset(df.columns):
        period_cols = ["YEAR", "MONTH"]
    else:
        period_cols = [column for column in spec.get("agg_cols", []) if column in df]
    if not period_cols:
        return None

    indexes = position_groups(
        df,
        period_cols,
        positive_columns=[x_col, y_col],
    )
    window = choose_window(
        indexes,
        rng,
        [3, 6, 12, 24, 36],
        minimum_rows=max(4, min(target, 12)),
    )
    if window is None:
        return None
    candidates, filters = window
    selected = sample_positions(
        candidates,
        rng,
        minimum_rows=3,
        maximum_rows=max(4, target + max(3, target // 5)),
        preferred_rows=target,
    )
    if selected is None:
        return None

    source = df.iloc[selected].copy()
    # Some loaders attach DataFrame side tables in ``attrs``. Pandas attempts
    # to compare those attributes during row-wise string aggregation.
    source.attrs = {}
    plot_df = pd.DataFrame(
        {
            "x": pd.to_numeric(source[x_col], errors="coerce").to_numpy(),
            "y": pd.to_numeric(source[y_col], errors="coerce").to_numpy(),
        }
    )
    label_columns = [
        column
        for column in ("SUPPLIER", "ITEM TYPE", "BOROUGH", "YEAR", "MONTH")
        if column in source.columns
    ]
    if label_columns:
        labels = source[label_columns].astype(str).agg(" ".join, axis=1).to_numpy()
    else:
        labels = np.array([f"Point {position}" for position in selected])
    plot_df["point_id"] = [f"{label} #{position}" for label, position in zip(labels, selected)]
    plot_df["label"] = labels

    context: dict[str, Any] = {
        "x_label": str(x_col).replace("_", " ").title(),
        "y_label": str(y_col).replace("_", " ").title(),
        "x_col": x_col,
        "y_col": y_col,
        "strategy": "sampled_observations",
        "sampling": sampling_metadata(
            df,
            candidates,
            selected,
            filters,
            eligibility=f"{x_col} > 0 and {y_col} > 0",
        ),
    }
    return _decorate_points(plot_df, context, style, rng)


def _london_scatter(
    df: pd.DataFrame,
    rng: np.random.Generator,
    style: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]] | None:
    strategy = str(
        rng.choice(["sector_vs_sector", "borough_vs_borough"], p=[0.60, 0.40])
    )
    target = _point_target(rng, int(style.get("n_points_bin", 3)))
    years = position_groups(
        df,
        ["YEAR"],
        positive_columns=["EMPLOYEE_JOBS"],
        non_null_columns=["BOROUGH", "SECTOR"],
    )
    window = choose_window(years, rng, [3, 5, 10, 20], minimum_rows=12)
    if window is None:
        return None
    window_positions, filters = window
    window_frame = df.iloc[window_positions]

    if strategy == "sector_vs_sector":
        pair_col = "SECTOR"
        unit_cols = ["BOROUGH", "YEAR"]
        totals = window_frame.groupby(pair_col, observed=True)["EMPLOYEE_JOBS"].sum()
    else:
        pair_col = "BOROUGH"
        unit_cols = ["SECTOR", "YEAR"]
        totals = window_frame.groupby(pair_col, observed=True)["EMPLOYEE_JOBS"].sum()
    top = totals.nlargest(12).index.tolist()
    if len(top) < 2:
        return None
    pairs = [(top[left], top[right]) for left in range(len(top)) for right in range(left + 1, len(top))]
    rng.shuffle(pairs)
    chosen_pair = None
    for first, second in pairs:
        pair_mask = window_frame[pair_col].isin([first, second]).to_numpy()
        pair_positions = window_positions[pair_mask]
        pair_frame = df.iloc[pair_positions][unit_cols + [pair_col, "EMPLOYEE_JOBS"]].copy()
        pair_frame["_source_position"] = pair_positions
        aggregated = (
            pair_frame.groupby(unit_cols + [pair_col], observed=True)
            .agg(value=("EMPLOYEE_JOBS", "sum"), positions=("_source_position", list))
            .reset_index()
        )
        wide = aggregated.pivot(index=unit_cols, columns=pair_col, values="value")
        complete_units = wide.dropna(subset=[first, second])
        if len(complete_units) >= 3:
            chosen_pair = (first, second)
            break
    if chosen_pair is None:
        return None
    first, second = chosen_pair
    count = min(target, len(complete_units))
    if len(complete_units) > 3:
        count = min(count, len(complete_units) - 1)
    chosen_indices = rng.choice(len(complete_units), size=count, replace=False)
    chosen_units = complete_units.iloc[np.sort(chosen_indices)].reset_index()

    unit_index = pd.MultiIndex.from_frame(chosen_units[unit_cols])
    aggregated_index = pd.MultiIndex.from_frame(aggregated[unit_cols])
    selected_rows = aggregated[aggregated_index.isin(unit_index)]
    selected = np.sort(
        np.asarray(
            [position for positions in selected_rows["positions"] for position in positions],
            dtype=np.int64,
        )
    )
    candidates = np.sort(pair_positions.astype(np.int64, copy=False))

    plot_df = chosen_units.rename(columns={first: "x", second: "y"})
    labels = plot_df[unit_cols].astype(str).agg(" ".join, axis=1)
    plot_df["point_id"] = labels
    plot_df["label"] = labels
    context: dict[str, Any] = {
        "x_label": f"{str(first).title()} Jobs",
        "y_label": f"{str(second).title()} Jobs",
        "x_col": str(first),
        "y_col": str(second),
        "strategy": strategy,
        "detail": f"Comparison across {filters['window_periods']} years",
        "sampling": sampling_metadata(
            df,
            candidates,
            selected,
            filters,
            eligibility=f"complete {first} and {second} pairs",
        ),
    }
    keep = ["x", "y", "point_id", "label"]
    return _decorate_points(plot_df[keep], context, style, rng)


def sample_scatter_data_from_df(
    df: pd.DataFrame,
    spec: dict[str, Any],
    rng: np.random.Generator,
    style: dict[str, Any],
    min_points: int = 3,
) -> tuple[pd.DataFrame, dict[str, Any]] | None:
    del min_points  # The production sampler validates a minimum of three points.
    if {"BOROUGH", "SECTOR", "YEAR", "EMPLOYEE_JOBS"}.issubset(df.columns):
        return _london_scatter(df, rng, style)
    return _direct_scatter(df, spec, rng, style)
