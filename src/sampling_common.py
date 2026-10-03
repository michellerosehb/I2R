from __future__ import annotations

import hashlib
import json
import weakref
from typing import Any, Sequence

import numpy as np
import pandas as pd


_POSITION_CACHE: dict[
    tuple[int, tuple[str, ...], tuple[str, ...], tuple[str, ...]],
    tuple[weakref.ReferenceType[pd.DataFrame], dict[tuple[Any, ...], np.ndarray]],
] = {}


def json_value(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if pd.isna(value):
        return None
    return value


def position_groups(
    frame: pd.DataFrame,
    group_columns: Sequence[str],
    *,
    positive_columns: Sequence[str] = (),
    non_null_columns: Sequence[str] = (),
) -> dict[tuple[Any, ...], np.ndarray]:
    """Index eligible DataFrame row positions by one or more filter columns."""
    groups = tuple(group_columns)
    positive = tuple(positive_columns)
    non_null = tuple(non_null_columns)
    cache_key = (id(frame), groups, positive, non_null)
    cached = _POSITION_CACHE.get(cache_key)
    if cached is not None and cached[0]() is frame:
        return cached[1]

    eligible = np.ones(len(frame), dtype=bool)
    for column in positive:
        values = pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=float)
        eligible &= np.isfinite(values) & (values > 0)
    for column in non_null:
        eligible &= frame[column].notna().to_numpy()
    positions = np.flatnonzero(eligible)

    if not groups:
        result = {(): positions.astype(np.int64, copy=False)}
    else:
        keys = frame.iloc[positions][list(groups)]
        keys.attrs = {}
        complete = keys.notna().all(axis=1).to_numpy()
        positions = positions[complete]
        keys = keys.iloc[np.flatnonzero(complete)]
        grouped = keys.groupby(
            list(groups), sort=True, observed=True, dropna=True
        ).indices
        result = {}
        for key, local_positions in grouped.items():
            normalised_key = key if isinstance(key, tuple) else (key,)
            result[normalised_key] = positions[
                np.asarray(local_positions, dtype=np.int64)
            ]

    _POSITION_CACHE[cache_key] = (weakref.ref(frame), result)
    return result


def choose_window(
    groups: dict[tuple[Any, ...], np.ndarray],
    rng: np.random.Generator,
    window_sizes: Sequence[int],
    *,
    minimum_rows: int,
) -> tuple[np.ndarray, dict[str, Any]] | None:
    ordered = sorted(groups.items(), key=lambda item: item[0])
    if not ordered:
        return None
    for _ in range(20):
        requested = int(window_sizes[int(rng.integers(0, len(window_sizes)))])
        width = min(requested, len(ordered))
        start = int(rng.integers(0, len(ordered) - width + 1))
        chosen = ordered[start : start + width]
        candidates = np.concatenate([positions for _, positions in chosen])
        if len(candidates) >= minimum_rows:
            return candidates, {
                "window_start": chosen[0][0],
                "window_end": chosen[-1][0],
                "window_periods": width,
            }
    return None


def sample_positions(
    candidates: np.ndarray,
    rng: np.random.Generator,
    *,
    minimum_rows: int,
    maximum_rows: int = 2500,
    preferred_rows: int | None = None,
) -> np.ndarray | None:
    population = int(len(candidates))
    if population < minimum_rows:
        return None
    maximum = min(population, maximum_rows)
    if population > minimum_rows:
        maximum = min(maximum, population - 1)
    minimum = min(minimum_rows, maximum)
    if preferred_rows is None:
        size = minimum if minimum == maximum else int(rng.integers(minimum, maximum + 1))
    else:
        jitter = max(1, int(round(preferred_rows * 0.20)))
        low = max(minimum, preferred_rows - jitter)
        high = min(maximum, preferred_rows + jitter)
        size = high if low > high else int(rng.integers(low, high + 1))
    selected = rng.choice(candidates, size=size, replace=False)
    return np.sort(np.asarray(selected, dtype=np.int64))


def source_sample_id(frame: pd.DataFrame, positions: np.ndarray) -> str:
    digest = hashlib.sha256()
    identity = {
        "dataset_name": frame.attrs.get("dataset_name", "unknown"),
        "source_fingerprint": frame.attrs.get("source_fingerprint", "unknown"),
    }
    digest.update(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    digest.update(np.asarray(np.sort(positions), dtype="<i8").tobytes())
    return digest.hexdigest()


def sampling_metadata(
    frame: pd.DataFrame,
    candidates: np.ndarray,
    selected: np.ndarray,
    filters: dict[str, Any],
    *,
    eligibility: str,
) -> dict[str, Any]:
    population = int(len(candidates))
    sampled = int(len(selected))
    documented_filters = {
        key: json_value(value) for key, value in filters.items()
    }
    documented_filters["row_eligibility"] = eligibility
    return {
        "method": "filtered_rows_without_replacement",
        "replacement": False,
        "filters": documented_filters,
        "population_rows": population,
        "sampled_rows": sampled,
        "sample_fraction": sampled / population,
        "source_sample_id": source_sample_id(frame, selected),
    }
