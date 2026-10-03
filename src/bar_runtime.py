from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import pandas as pd


def canonical_dataframe_hash(frame: pd.DataFrame) -> str:
    """Return an order-independent hash of a plotted data table.

    Values are converted to a stable textual representation before hashing, so
    row order, DataFrame index, and CSV dtype inference do not make identical
    plotted data appear unique.
    """
    columns = sorted(str(column) for column in frame.columns)
    canonical = frame.copy()
    canonical.columns = [str(column) for column in canonical.columns]
    canonical = canonical.reindex(columns=columns)

    normalised = pd.DataFrame(index=canonical.index)
    for column in columns:
        values = canonical[column]
        if pd.api.types.is_datetime64_any_dtype(values):
            converted = pd.to_datetime(values, errors="coerce").dt.strftime(
                "%Y-%m-%dT%H:%M:%S.%f"
            )
        elif pd.api.types.is_numeric_dtype(values):
            converted = values.map(
                lambda value: "<NA>"
                if pd.isna(value)
                else format(float(value), ".15g")
            )
        else:
            converted = values.map(
                lambda value: "<NA>" if pd.isna(value) else str(value)
            )
        normalised[column] = converted.fillna("<NA>")

    if columns:
        normalised = normalised.sort_values(columns, kind="mergesort").reset_index(
            drop=True
        )
    payload = {
        "columns": columns,
        "rows": normalised.to_dict(orient="records"),
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class TableHashRegistry:
    """Persistent uniqueness registry for generated chart tables."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, timeout=60)
        self.connection.execute("PRAGMA busy_timeout = 60000")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS table_hashes (
                sample_hash TEXT PRIMARY KEY,
                chart_id TEXT NOT NULL UNIQUE,
                dataset_source TEXT,
                library TEXT,
                created_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        existing_columns = {
            row[1]
            for row in self.connection.execute("PRAGMA table_info(table_hashes)")
        }
        if "source_sample_id" not in existing_columns:
            self.connection.execute(
                "ALTER TABLE table_hashes ADD COLUMN source_sample_id TEXT"
            )
        self.connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
                table_hashes_source_sample_id_unique
            ON table_hashes(source_sample_id)
            WHERE source_sample_id IS NOT NULL
            """
        )
        self.connection.commit()

    def claim(
        self,
        sample_hash: str,
        chart_id: str,
        *,
        dataset_source: str | None = None,
        library: str | None = None,
        source_sample_id: str | None = None,
    ) -> bool:
        cursor = self.connection.execute(
            """
            INSERT OR IGNORE INTO table_hashes
                (sample_hash, chart_id, dataset_source, library, source_sample_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (sample_hash, chart_id, dataset_source, library, source_sample_id),
        )
        self.connection.commit()
        return cursor.rowcount == 1

    def release_chart(self, chart_id: str) -> None:
        self.connection.execute(
            "DELETE FROM table_hashes WHERE chart_id = ?", (chart_id,)
        )
        self.connection.commit()

    def count(self) -> int:
        row = self.connection.execute("SELECT COUNT(*) FROM table_hashes").fetchone()
        return int(row[0])

    def seed_from_tables(self, table_root: Path) -> int:
        """Seed an empty registry from older CSV outputs that lack hashes."""
        if self.count() != 0:
            return 0
        imported = 0
        for table_path in sorted(Path(table_root).glob("*/*.csv")):
            try:
                frame = pd.read_csv(table_path)
            except (OSError, ValueError, pd.errors.ParserError):
                continue
            if self.claim(
                canonical_dataframe_hash(frame),
                table_path.stem,
                library=table_path.parent.name,
            ):
                imported += 1
        return imported

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "TableHashRegistry":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()


def find_project_root(start: Path | None = None) -> Path:
    """Find the repository root without relying on a machine-specific path."""
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "requirements.txt").is_file() and (candidate / "data").is_dir():
            return candidate
    raise RuntimeError(
        "Could not find the I2R project root. Set I2R_PROJECT_ROOT explicitly."
    )


def source_fingerprint(path: Path) -> str:
    stat = path.stat()
    raw = f"{path.resolve()}:{stat.st_size}:{stat.st_mtime_ns}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


class DatasetCache:
    """Build cleaned Parquet datasets once, then load the cached files."""

    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def load(
        self,
        dataset_name: str,
        source_path: Path,
        loader: Callable[[pd.DataFrame], pd.DataFrame] | None = None,
        *,
        usecols: Sequence[str] | None = None,
        force_rebuild: bool = False,
    ) -> pd.DataFrame:
        source_path = Path(source_path)
        if not source_path.is_file():
            raise FileNotFoundError(f"Dataset not found: {source_path}")

        fingerprint = source_fingerprint(source_path)
        parquet_path = self.cache_dir / f"{dataset_name}.parquet"
        metadata_path = self.cache_dir / f"{dataset_name}.cache.json"

        cache_valid = False
        if not force_rebuild and parquet_path.is_file() and metadata_path.is_file():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                cache_valid = metadata.get("source_fingerprint") == fingerprint
            except (OSError, json.JSONDecodeError):
                cache_valid = False

        if cache_valid:
            frame = pd.read_parquet(parquet_path)
            for attr_name in metadata.get("dataframe_attrs", []):
                attr_path = self.cache_dir / f"{dataset_name}.attr.{attr_name}.parquet"
                if attr_path.is_file():
                    frame.attrs[attr_name] = pd.read_parquet(attr_path)
        else:
            read_kwargs: dict[str, Any] = {"low_memory": False}
            if usecols:
                read_kwargs["usecols"] = list(usecols)
            frame = pd.read_csv(source_path, **read_kwargs)
            if loader is not None:
                frame = loader(frame)
            dataframe_attrs = {
                name: value
                for name, value in frame.attrs.items()
                if isinstance(value, pd.DataFrame)
            }
            # Pandas serializes ``DataFrame.attrs`` into Parquet metadata. Nested
            # DataFrames are not JSON serializable, so persist them as explicit
            # sidecars and temporarily remove them from the main frame.
            for attr_name in dataframe_attrs:
                frame.attrs.pop(attr_name, None)
            frame.to_parquet(parquet_path, index=False, compression="zstd")
            frame.attrs.update(dataframe_attrs)
            for attr_name, attr_frame in dataframe_attrs.items():
                attr_frame.to_parquet(
                    self.cache_dir / f"{dataset_name}.attr.{attr_name}.parquet",
                    index=False,
                    compression="zstd",
                )
            metadata_path.write_text(
                json.dumps(
                    {
                        "dataset_name": dataset_name,
                        "source_path": str(source_path.resolve()),
                        "source_fingerprint": fingerprint,
                        "rows": len(frame),
                        "columns": list(frame.columns),
                        "dataframe_attrs": sorted(dataframe_attrs),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

        frame.attrs["dataset_name"] = dataset_name
        frame.attrs["source_fingerprint"] = fingerprint
        return frame


class AggregationCache:
    """Memoize expensive group-bys in memory and optionally on disk."""

    VALUE_COLUMN = "__aggregate_value__"

    def __init__(self, cache_dir: Path | None = None, *, persist: bool = True):
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        self.persist = bool(persist and self.cache_dir is not None)
        self._memory: dict[str, pd.Series] = {}
        self._unique_memory: dict[tuple[str, str], tuple[Any, ...]] = {}
        if self.persist:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _dataset_token(frame: pd.DataFrame) -> str:
        name = str(frame.attrs.get("dataset_name", "dataset"))
        fingerprint = str(frame.attrs.get("source_fingerprint", id(frame)))
        return f"{name}:{fingerprint}"

    @staticmethod
    def _normalise_filters(
        filters: Iterable[tuple[str, Any]] | None,
    ) -> tuple[tuple[str, Any], ...]:
        return tuple(filters or ())

    def _key(
        self,
        frame: pd.DataFrame,
        group_cols: Sequence[str],
        value_col: str,
        filters: tuple[tuple[str, Any], ...],
    ) -> str:
        payload = {
            "dataset": self._dataset_token(frame),
            "group_cols": list(group_cols),
            "value_col": value_col,
            "filters": [(column, str(value)) for column, value in filters],
        }
        encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _disk_path(self, frame: pd.DataFrame, key: str) -> Path:
        dataset_name = str(frame.attrs.get("dataset_name", "dataset"))
        return self.cache_dir / dataset_name / f"{key}.parquet"

    def group_sum(
        self,
        frame: pd.DataFrame,
        group_cols: str | Sequence[str],
        value_col: str,
        *,
        filters: Iterable[tuple[str, Any]] | None = None,
    ) -> pd.Series:
        columns = [group_cols] if isinstance(group_cols, str) else list(group_cols)
        normalised_filters = self._normalise_filters(filters)
        key = self._key(frame, columns, value_col, normalised_filters)

        cached = self._memory.get(key)
        if cached is not None:
            return cached

        disk_path = self._disk_path(frame, key) if self.persist else None
        if disk_path is not None and disk_path.is_file():
            cached_frame = pd.read_parquet(disk_path)
            cached = cached_frame.set_index(columns)[self.VALUE_COLUMN]
            self._memory[key] = cached
            return cached

        subset = frame
        for column, value in normalised_filters:
            subset = subset.loc[subset[column] == value]

        cached = (
            subset.groupby(columns, observed=True, sort=False, dropna=True)[value_col]
            .sum()
            .rename(self.VALUE_COLUMN)
        )
        self._memory[key] = cached

        if disk_path is not None:
            disk_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = disk_path.with_name(
                f"{disk_path.stem}.{os.getpid()}.tmp{disk_path.suffix}"
            )
            cached.reset_index().to_parquet(temporary, index=False, compression="zstd")
            temporary.replace(disk_path)
        return cached

    def unique(self, frame: pd.DataFrame, column: str) -> tuple[Any, ...]:
        key = (self._dataset_token(frame), column)
        cached = self._unique_memory.get(key)
        if cached is None:
            cached = tuple(frame[column].dropna().unique().tolist())
            self._unique_memory[key] = cached
        return cached


class JsonCache:
    """Small write-behind JSON cache, suitable for generated titles."""

    def __init__(self, path: Path, *, flush_every: int = 50):
        self.path = Path(path)
        self.flush_every = max(1, int(flush_every))
        self.data: dict[str, Any] = {}
        self._dirty = 0
        if self.path.is_file():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self.data = loaded
            except (OSError, json.JSONDecodeError):
                self.data = {}

    @staticmethod
    def key(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Any:
        return self.data.get(key)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value
        self._dirty += 1
        if self._dirty >= self.flush_every:
            self.flush()

    def flush(self) -> None:
        if self._dirty == 0:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.path)
        self._dirty = 0
