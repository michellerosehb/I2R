from __future__ import annotations

import hashlib
import json
import weakref
from typing import Any, Sequence

import numpy as np
import pandas as pd


# Group-to-row-position indexes are built lazily and reused across charts.  The
# cache holds only a weak reference to the source frame, so replacing a dataset
# cannot accidentally reuse indexes from an older DataFrame.
_POSITION_INDEXES: dict[
    tuple[int, tuple[str, ...], str, str],
    tuple[weakref.ReferenceType[pd.DataFrame], dict[tuple[Any, ...], np.ndarray]],
] = {}


def _normalise_key(value: Any) -> tuple[Any, ...]:
    if isinstance(value, tuple):
        return value
    return (value,)


def _json_value(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if pd.isna(value):
        return None
    return value


def _position_index(
    frame: pd.DataFrame,
    filter_columns: Sequence[str],
    value_col: str,
    category_col: str,
) -> dict[tuple[Any, ...], np.ndarray]:
    """Return reusable eligible row positions grouped by the requested filters."""
    columns = tuple(filter_columns)
    cache_key = (id(frame), columns, value_col, category_col)
    cached = _POSITION_INDEXES.get(cache_key)
    if cached is not None and cached[0]() is frame:
        return cached[1]

    values = pd.to_numeric(frame[value_col], errors="coerce")
    eligible = values.gt(0) & frame[category_col].notna()
    positions = np.flatnonzero(eligible.to_numpy())

    if not columns:
        result = {(): positions.astype(np.int64, copy=False)}
    else:
        key_frame = frame.iloc[positions][list(columns)]
        complete = key_frame.notna().all(axis=1).to_numpy()
        positions = positions[complete]
        key_frame = key_frame.iloc[np.flatnonzero(complete)]
        grouped = key_frame.groupby(
            list(columns), sort=True, observed=True, dropna=True
        ).indices
        result = {
            _normalise_key(key): positions[np.asarray(local, dtype=np.int64)]
            for key, local in grouped.items()
        }

    _POSITION_INDEXES[cache_key] = (weakref.ref(frame), result)
    return result


def _sample_positions(
    candidates: np.ndarray,
    rng: np.random.Generator,
    n_bars: int,
) -> np.ndarray | None:
    """Draw a variable-size source-row subset, always without replacement."""
    population = int(len(candidates))
    if population < 4:
        return None

    # Small slices retain most rows while still leaving room for many distinct
    # subsets. Large slices are capped so grouping remains fast per chart.
    if population <= 100:
        lower = max(3, min(population - 1, max(6, n_bars)))
        upper = population - 1
    else:
        lower = min(population - 1, max(30, n_bars * 3))
        upper = min(population - 1, max(lower, 2500))

    size = lower if lower == upper else int(rng.integers(lower, upper + 1))
    selected = rng.choice(candidates, size=size, replace=False)
    return np.sort(np.asarray(selected, dtype=np.int64))


def _source_sample_id(frame: pd.DataFrame, positions: np.ndarray) -> str:
    digest = hashlib.sha256()
    identity = {
        "dataset_name": frame.attrs.get("dataset_name", "unknown"),
        "source_fingerprint": frame.attrs.get("source_fingerprint", "unknown"),
    }
    digest.update(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    digest.update(np.asarray(positions, dtype="<i8").tobytes())
    return digest.hexdigest()


def _sampling_context(
    frame: pd.DataFrame,
    candidates: np.ndarray,
    selected: np.ndarray,
    filters: dict[str, Any],
) -> dict[str, Any]:
    population = int(len(candidates))
    sampled = int(len(selected))
    return {
        "method": "filtered_rows_without_replacement",
        "replacement": False,
        "filters": {key: _json_value(value) for key, value in filters.items()},
        "population_rows": population,
        "sampled_rows": sampled,
        "sample_fraction": sampled / population,
        "source_sample_id": _source_sample_id(frame, selected),
    }


def _aggregate_sample(
    frame: pd.DataFrame,
    selected: np.ndarray,
    category_col: str,
    value_col: str,
    n_bars: int,
    *,
    ordered_categories: Sequence[Any] | None = None,
    min_total: float = 1.0,
) -> tuple[pd.DataFrame, pd.Series] | None:
    sampled = frame.iloc[selected][[category_col, value_col]].copy()
    sampled[value_col] = pd.to_numeric(sampled[value_col], errors="coerce")
    sampled = sampled.dropna(subset=[category_col, value_col])
    series = sampled.groupby(category_col, observed=True)[value_col].sum(min_count=1)
    series = series[series > 0]
    if len(series) < 2 or float(series.sum()) <= min_total:
        return None

    if ordered_categories is not None:
        present = [value for value in ordered_categories if value in series.index]
        series = series.reindex(present)
    else:
        series = series.sort_values(ascending=False).head(n_bars)

    if len(series) < 2:
        return None
    plot_df = series.rename(value_col).reset_index()
    plot_df.columns = [category_col, value_col]
    return plot_df, series


def _choose_group(
    groups: dict[tuple[Any, ...], np.ndarray],
    rng: np.random.Generator,
    minimum_rows: int,
) -> tuple[tuple[Any, ...], np.ndarray] | None:
    viable = [
        (key, positions)
        for key, positions in sorted(groups.items(), key=lambda item: repr(item[0]))
        if len(positions) >= minimum_rows
    ]
    if not viable:
        return None
    return viable[int(rng.integers(0, len(viable)))]


def _choose_time_window(
    groups: dict[tuple[Any, ...], np.ndarray],
    rng: np.random.Generator,
    window_sizes: Sequence[int],
    minimum_rows: int,
) -> tuple[np.ndarray, dict[str, Any]] | None:
    ordered = sorted(groups.items(), key=lambda item: item[0])
    if not ordered:
        return None

    for _ in range(16):
        requested = int(window_sizes[int(rng.integers(0, len(window_sizes)))])
        width = min(requested, len(ordered))
        start = int(rng.integers(0, len(ordered) - width + 1))
        chosen = ordered[start : start + width]
        candidates = np.concatenate([positions for _, positions in chosen])
        if len(candidates) >= minimum_rows:
            return candidates, {
                "window_start": chosen[0][0][0],
                "window_end": chosen[-1][0][0],
                "window_periods": width,
            }
    return None


def _build_result(
    frame: pd.DataFrame,
    candidates: np.ndarray,
    rng: np.random.Generator,
    category_col: str,
    value_col: str,
    n_bars: int,
    context: dict[str, Any],
    filters: dict[str, Any],
    *,
    ordered_categories: Sequence[Any] | None = None,
    min_total: float = 1.0,
) -> tuple[pd.DataFrame, dict[str, Any]] | None:
    selected = _sample_positions(candidates, rng, n_bars)
    if selected is None:
        return None
    aggregated = _aggregate_sample(
        frame,
        selected,
        category_col,
        value_col,
        n_bars,
        ordered_categories=ordered_categories,
        min_total=min_total,
    )
    if aggregated is None:
        return None
    plot_df, series = aggregated
    documented_filters = dict(filters)
    documented_filters["row_eligibility"] = (
        f"{value_col} > 0 and {category_col} is not null"
    )
    context.update(
        {
            "category_col": category_col,
            "value_col": value_col,
            "n_bars": int(len(plot_df)),
            "total": float(series.sum()),
            "sampling": _sampling_context(
                frame, candidates, selected, documented_filters
            ),
        }
    )
    return plot_df, context


def _sample_london(
    frame: pd.DataFrame,
    rng: np.random.Generator,
    n_bars: int,
    min_total: float,
) -> tuple[pd.DataFrame, dict[str, Any]] | None:
    strategy = str(
        rng.choice(
            ["sector_totals", "borough_totals", "sector_year", "borough_year"],
            p=[0.35, 0.35, 0.15, 0.15],
        )
    )
    category_col = "SECTOR" if strategy.startswith("sector") else "BOROUGH"
    groups = _position_index(frame, ["YEAR"], "EMPLOYEE_JOBS", category_col)
    window_sizes = [1] if strategy.endswith("year") else [3, 5, 10, 20]
    window = _choose_time_window(groups, rng, window_sizes, minimum_rows=6)
    if window is None:
        return None
    candidates, filters = window
    return _build_result(
        frame,
        candidates,
        rng,
        category_col,
        "EMPLOYEE_JOBS",
        n_bars,
        {"strategy": strategy},
        filters,
        min_total=min_total,
    )


def _sample_collisions(
    frame: pd.DataFrame,
    numeric_cols: Sequence[str],
    rng: np.random.Generator,
    n_bars: int,
    min_total: float,
) -> tuple[pd.DataFrame, dict[str, Any]] | None:
    value_col = str(rng.choice(list(numeric_cols)))
    strategy = str(
        rng.choice(
            [
                "by_borough",
                "by_factor",
                "by_vehicle_type",
                "by_hour",
                "by_day",
                "by_month",
                "by_street",
                "factor_in_borough",
            ],
            p=[0.15, 0.15, 0.10, 0.15, 0.15, 0.10, 0.10, 0.10],
        )
    )
    category_map = {
        "by_borough": "BOROUGH",
        "by_factor": "CONTRIBUTING FACTOR VEHICLE 1",
        "by_vehicle_type": "VEHICLE TYPE CODE 1",
        "by_hour": "HOUR",
        "by_day": "DAY_OF_WEEK",
        "by_month": "MONTH",
        "factor_in_borough": "CONTRIBUTING FACTOR VEHICLE 1",
    }
    if strategy == "by_street":
        category_col = str(rng.choice(["ON STREET NAME", "OFF STREET NAME"]))
    else:
        category_col = category_map[strategy]
    if category_col not in frame.columns:
        return None

    mode = str(
        rng.choice(
            ["year", "year_month", "year_borough", "year_month_borough"],
            p=[0.35, 0.25, 0.25, 0.15],
        )
    )
    filter_columns = ["YEAR"]
    if "month" in mode and category_col != "MONTH":
        filter_columns.append("MONTH")
    if ("borough" in mode or strategy == "factor_in_borough") and category_col != "BOROUGH":
        filter_columns.append("BOROUGH")

    minimum_rows = max(6, min(30, n_bars))
    chosen = _choose_group(
        _position_index(frame, filter_columns, value_col, category_col),
        rng,
        minimum_rows,
    )
    if chosen is None and filter_columns != ["YEAR"]:
        filter_columns = ["YEAR"]
        chosen = _choose_group(
            _position_index(frame, filter_columns, value_col, category_col),
            rng,
            minimum_rows,
        )
    if chosen is None:
        return None

    key, candidates = chosen
    filters = dict(zip(filter_columns, key))
    ordered_categories: Sequence[Any] | None = None
    if strategy == "by_hour":
        ordered_categories = list(range(24))
    elif strategy == "by_day":
        ordered_categories = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
    elif strategy == "by_month":
        ordered_categories = list(range(1, 13))

    context: dict[str, Any] = {"strategy": strategy}
    if strategy == "by_street":
        context["street_col"] = category_col
    if "YEAR" in filters:
        context["year"] = _json_value(filters["YEAR"])
    if "BOROUGH" in filters:
        context["borough"] = _json_value(filters["BOROUGH"])
    return _build_result(
        frame,
        candidates,
        rng,
        category_col,
        value_col,
        n_bars,
        context,
        filters,
        ordered_categories=ordered_categories,
        min_total=min_total,
    )


def _sample_general(
    frame: pd.DataFrame,
    spec: dict[str, Any],
    numeric_cols: Sequence[str],
    group_cols: Sequence[str],
    rng: np.random.Generator,
    n_bars: int,
    min_total: float,
) -> tuple[pd.DataFrame, dict[str, Any]] | None:
    value_col = str(rng.choice(list(numeric_cols)))
    category_col = str(rng.choice(list(group_cols)))
    strategy = str(
        rng.choice(["group", "time_window", "filtered_group"], p=[0.40, 0.35, 0.25])
    )

    date_col = spec.get("date_col")
    if date_col and date_col in frame.columns:
        groups = _position_index(frame, [date_col], value_col, category_col)
        sizes = [3, 6, 12, 24] if strategy == "group" else [1, 3, 6, 12]
        window = _choose_time_window(groups, rng, sizes, minimum_rows=max(6, n_bars))
        if window is None:
            return None
        candidates, filters = window
    else:
        candidates = _position_index(frame, [], value_col, category_col).get(
            (), np.array([], dtype=np.int64)
        )
        filters = {}

    return _build_result(
        frame,
        candidates,
        rng,
        category_col,
        value_col,
        n_bars,
        {"strategy": strategy},
        filters,
        min_total=min_total,
    )


def sample_bar_data_from_df(
    df: pd.DataFrame,
    spec: dict[str, Any],
    rng: np.random.Generator,
    style: dict[str, Any],
    min_total: float = 1.0,
) -> tuple[pd.DataFrame, dict[str, Any]] | None:
    """Create a bar table from a deterministic, no-replacement source-row sample.

    Reproducibility is controlled entirely by ``rng`` and the source DataFrame.
    The returned context contains enough provenance to audit the selected slice.
    """
    numeric_cols = [column for column in spec["numeric_cols"] if column in df.columns]
    group_cols = [column for column in spec["group_cols"] if column in df.columns]
    if not numeric_cols or not group_cols:
        return None

    sample_bin = style.get("sample_bin", 8)
    n_bars = int(sample_bin) if isinstance(sample_bin, int) and sample_bin >= 2 else 8
    n_bars = max(2, min(n_bars, 30))

    if {"BOROUGH", "SECTOR", "YEAR", "EMPLOYEE_JOBS"}.issubset(df.columns):
        return _sample_london(df, rng, n_bars, min_total)
    if {"BOROUGH", "YEAR", "MONTH", "DAY_OF_WEEK", "HOUR"}.issubset(df.columns):
        return _sample_collisions(df, numeric_cols, rng, n_bars, min_total)
    return _sample_general(
        df, spec, numeric_cols, group_cols, rng, n_bars, min_total
    )
