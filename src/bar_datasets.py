from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .bar_runtime import DatasetCache, find_project_root


def dataset_registry(data_train: Path) -> dict[str, dict]:
    data_train = Path(data_train)
    return {
        "warehouse_retail": {
            "path": data_train / "Warehouse_and_Retail_Sales.csv",
            "numeric_cols": ["RETAIL SALES", "WAREHOUSE SALES", "RETAIL TRANSFERS"],
            "group_cols": ["ITEM TYPE", "SUPPLIER"],
            "date_col": "date",
            "agg_cols": ["YEAR", "MONTH"],
            "csv_usecols": [
                "YEAR",
                "MONTH",
                "SUPPLIER",
                "ITEM TYPE",
                "RETAIL SALES",
                "WAREHOUSE SALES",
                "RETAIL TRANSFERS",
            ],
            "loader": load_warehouse_retail,
        },
        "london_borough_sector_jobs": {
            "path": data_train / "london_borough_sector_jobs.csv",
            "numeric_cols": ["EMPLOYEE_JOBS"],
            "group_cols": ["BOROUGH", "SECTOR"],
            "date_col": None,
            "agg_cols": ["YEAR"],
            "csv_usecols": None,
            "loader": load_london_borough_sector_jobs,
        },
        "motor_vehicle_collisions": {
            "path": data_train / "Motor_Vehicle_Collisions_-_Crashes.csv",
            "numeric_cols": [
                "NUMBER OF PERSONS INJURED",
                "NUMBER OF PERSONS KILLED",
                "NUMBER OF PEDESTRIANS INJURED",
                "NUMBER OF CYCLIST INJURED",
                "NUMBER OF MOTORIST INJURED",
            ],
            "group_cols": [
                "BOROUGH",
                "CONTRIBUTING FACTOR VEHICLE 1",
                "VEHICLE TYPE CODE 1",
                "ON STREET NAME",
                "OFF STREET NAME",
                "DAY_OF_WEEK",
                "HOUR",
                "MONTH",
                "YEAR",
            ],
            "date_col": "CRASH DATE",
            "agg_cols": ["YEAR", "MONTH"],
            "csv_usecols": [
                "CRASH DATE",
                "CRASH TIME",
                "BOROUGH",
                "CONTRIBUTING FACTOR VEHICLE 1",
                "VEHICLE TYPE CODE 1",
                "ON STREET NAME",
                "OFF STREET NAME",
                "NUMBER OF PERSONS INJURED",
                "NUMBER OF PERSONS KILLED",
                "NUMBER OF PEDESTRIANS INJURED",
                "NUMBER OF CYCLIST INJURED",
                "NUMBER OF MOTORIST INJURED",
            ],
            "loader": load_motor_vehicle_collisions,
        },
    }


def load_warehouse_retail(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame["date"] = pd.to_datetime(
        {
            "year": frame["YEAR"].astype("Int64"),
            "month": frame["MONTH"].astype("Int64"),
            "day": 1,
        },
        errors="coerce",
    )
    return frame


def load_london_borough_sector_jobs(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.dropna(axis=1, how="all").dropna(axis=0, how="all").reset_index(drop=True)

    def is_year_like(value: object) -> bool:
        text = str(value).strip()
        if text.endswith(".0"):
            text = text[:-2]
        return len(text) == 4 and text.isdigit() and text[:2] in {"19", "20"}

    current_year_cols = [column for column in frame.columns if is_year_like(column)]
    if len(current_year_cols) < 5:
        best_index = None
        best_count = 0
        for index in range(min(len(frame), 30)):
            count = sum(is_year_like(value) for value in frame.iloc[index].tolist())
            if count > best_count:
                best_index = index
                best_count = count
        if best_index is not None and best_count >= 5:
            frame.columns = [str(value) for value in frame.iloc[best_index].tolist()]
            frame = frame.iloc[best_index + 1 :].reset_index(drop=True)

    year_cols = [column for column in frame.columns if is_year_like(column)]
    id_cols = [column for column in frame.columns if not is_year_like(column)]
    if not year_cols or not id_cols:
        raise ValueError("Could not identify year columns in London dataset")

    result = frame.melt(
        id_vars=id_cols,
        value_vars=year_cols,
        var_name="YEAR",
        value_name="EMPLOYEE_JOBS",
    )
    result["YEAR"] = pd.to_numeric(
        result["YEAR"].astype(str).str.replace(r"\.0$", "", regex=True),
        errors="coerce",
    )
    result["EMPLOYEE_JOBS"] = pd.to_numeric(result["EMPLOYEE_JOBS"], errors="coerce")
    result = result.dropna(subset=["YEAR", "EMPLOYEE_JOBS"])
    result = result.loc[result["EMPLOYEE_JOBS"] > 0]

    rename: dict[object, str] = {}
    for column in id_cols:
        normalised = str(column).strip().upper()
        if any(token in normalised for token in ("BOROUGH", "AREA", "DISTRICT")):
            rename[column] = "BOROUGH"
        elif any(token in normalised for token in ("SECTOR", "INDUSTRY", "TYPE")):
            rename[column] = "SECTOR"
    result = result.rename(columns=rename)

    remaining = [column for column in id_cols if column not in rename]
    if "BOROUGH" not in result.columns and remaining:
        result = result.rename(columns={remaining.pop(0): "BOROUGH"})
    if "SECTOR" not in result.columns and remaining:
        result = result.rename(columns={remaining.pop(0): "SECTOR"})
    return result.reset_index(drop=True)


def load_motor_vehicle_collisions(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame["CRASH DATE"] = pd.to_datetime(frame["CRASH DATE"], errors="coerce")
    frame["YEAR"] = frame["CRASH DATE"].dt.year
    frame["MONTH"] = frame["CRASH DATE"].dt.month
    frame["DAY_OF_WEEK"] = frame["CRASH DATE"].dt.day_name()
    frame["HOUR"] = pd.to_datetime(
        frame["CRASH TIME"], format="%H:%M", errors="coerce"
    ).dt.hour

    categorical = [
        "BOROUGH",
        "CONTRIBUTING FACTOR VEHICLE 1",
        "VEHICLE TYPE CODE 1",
        "ON STREET NAME",
        "OFF STREET NAME",
    ]
    for column in categorical:
        frame[column] = (
            frame[column]
            .astype("string")
            .str.strip()
            .str.title()
            .replace({"Unspecified": pd.NA, "": pd.NA})
        )

    numeric = [
        "NUMBER OF PERSONS INJURED",
        "NUMBER OF PERSONS KILLED",
        "NUMBER OF PEDESTRIANS INJURED",
        "NUMBER OF CYCLIST INJURED",
        "NUMBER OF MOTORIST INJURED",
    ]
    for column in numeric:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0)
    return frame.dropna(subset=["YEAR", "MONTH"]).reset_index(drop=True)


def load_all_datasets(
    registry: dict[str, dict],
    cache: DatasetCache,
    *,
    force_rebuild: bool = False,
) -> dict[str, pd.DataFrame]:
    datasets: dict[str, pd.DataFrame] = {}
    for name, spec in registry.items():
        path = Path(spec["path"])
        if not path.is_file():
            print(f"Dataset not found: {path}")
            continue
        frame = cache.load(
            name,
            path,
            spec.get("loader"),
            usecols=spec.get("csv_usecols"),
            force_rebuild=force_rebuild,
        )
        datasets[name] = frame
        print(f"Loaded {name!r}: {len(frame):,} rows, {len(frame.columns)} columns")
    return datasets


def main() -> None:
    parser = argparse.ArgumentParser(description="Build reusable bar-generator Parquet caches")
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--data-train", type=Path)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    project = (args.project_root or find_project_root()).resolve()
    data_train = (args.data_train or project / "data" / "train").resolve()
    cache_dir = (args.cache_dir or project / "data" / "processed" / "bar" / "datasets").resolve()
    cache = DatasetCache(cache_dir)
    datasets = load_all_datasets(
        dataset_registry(data_train), cache, force_rebuild=args.force
    )
    if not datasets:
        raise SystemExit("No datasets were loaded")
    print(f"Prepared {len(datasets)} bar datasets in {cache_dir}")


if __name__ == "__main__":
    main()
