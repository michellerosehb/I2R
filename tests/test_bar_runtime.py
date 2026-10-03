from __future__ import annotations

import ast
import json
from pathlib import Path

import pandas as pd
import numpy as np

from src.bar_runtime import (
    AggregationCache,
    DatasetCache,
    JsonCache,
    TableHashRegistry,
    canonical_dataframe_hash,
    find_project_root,
)
from src.bar_sampling import sample_bar_data_from_df
from src.line_sampling import sample_line_data_from_df
from src.pie_sampling import sample_pie_data_from_df


PROJECT = Path(__file__).resolve().parents[1]


def test_final_notebook_code_cells_compile() -> None:
    notebook_dir = PROJECT / "notebooks" / "final_notebook_v1" / "notebooks"
    notebook_paths = sorted(notebook_dir.glob("*_FINAL.ipynb"))
    assert {path.stem for path in notebook_paths} == {
        "bar_generator_FINAL",
        "line_generator_FINAL",
        "pie_generator_FINAL",
        "scatter_generator_FINAL",
    }
    for notebook_path in notebook_paths:
        notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
        for index, cell in enumerate(notebook["cells"]):
            if cell.get("cell_type") != "code":
                continue
            source = "".join(cell.get("source", []))
            try:
                ast.parse(source)
            except SyntaxError as exc:
                raise AssertionError(
                    f"{notebook_path.name} code cell {index} does not compile"
                ) from exc


def test_dataset_and_aggregation_caches(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    pd.DataFrame(
        {
            "group": ["a", "a", "b"],
            "year": [2024, 2025, 2025],
            "value": [1, 2, 4],
            "unused": [10, 20, 30],
        }
    ).to_csv(source, index=False)

    dataset_cache = DatasetCache(tmp_path / "datasets")
    frame = dataset_cache.load(
        "sample",
        source,
        usecols=["group", "year", "value"],
    )
    assert list(frame.columns) == ["group", "year", "value"]

    aggregation_cache = AggregationCache(tmp_path / "aggregations", persist=True)
    totals = aggregation_cache.group_sum(frame, "group", "value")
    assert totals.to_dict() == {"a": 3, "b": 4}

    filtered = aggregation_cache.group_sum(
        frame,
        "group",
        "value",
        filters=(("year", 2025),),
    )
    assert filtered.to_dict() == {"a": 2, "b": 4}

    reloaded_cache = AggregationCache(tmp_path / "aggregations", persist=True)
    reloaded = reloaded_cache.group_sum(frame, "group", "value")
    assert reloaded.to_dict() == totals.to_dict()


def test_dataset_cache_preserves_dataframe_attributes(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    pd.DataFrame({"group": ["a", "b"], "value": [1, 2]}).to_csv(
        source, index=False
    )

    def attach_side_table(frame: pd.DataFrame) -> pd.DataFrame:
        frame.attrs["side_table"] = pd.DataFrame(
            {"group": ["a", "b"], "count": [3, 4]}
        )
        return frame

    cache_dir = tmp_path / "datasets"
    first = DatasetCache(cache_dir).load("sample", source, attach_side_table)
    second = DatasetCache(cache_dir).load("sample", source, attach_side_table)

    pd.testing.assert_frame_equal(first.attrs["side_table"], second.attrs["side_table"])


def test_bar_sampler_is_reproducible_and_samples_without_replacement() -> None:
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2020-01-01", periods=120, freq="MS"),
            "category": np.tile(["a", "b", "c", "d"], 30),
            "filter": np.tile(["x", "y"], 60),
            "value": np.arange(1.0, 121.0),
        }
    )
    frame.attrs["dataset_name"] = "synthetic"
    frame.attrs["source_fingerprint"] = "v1"
    spec = {
        "numeric_cols": ["value"],
        "group_cols": ["category", "filter"],
        "date_col": "date",
    }

    first = sample_bar_data_from_df(
        frame, spec, np.random.default_rng(17), {"sample_bin": 4}
    )
    repeated = sample_bar_data_from_df(
        frame, spec, np.random.default_rng(17), {"sample_bin": 4}
    )
    different = sample_bar_data_from_df(
        frame, spec, np.random.default_rng(18), {"sample_bin": 4}
    )

    assert first is not None and repeated is not None and different is not None
    first_table, first_context = first
    repeated_table, repeated_context = repeated
    _, different_context = different
    pd.testing.assert_frame_equal(first_table, repeated_table)
    assert first_context == repeated_context
    sampling = first_context["sampling"]
    assert sampling["replacement"] is False
    assert 0 < sampling["sampled_rows"] < sampling["population_rows"]
    assert sampling["source_sample_id"] != different_context["sampling"]["source_sample_id"]


def test_uniqueness_registry_rejects_tables_and_source_samples(tmp_path: Path) -> None:
    table = pd.DataFrame({"category": ["a", "b"], "value": [1.0, 2.0]})
    reordered = table.iloc[::-1].reset_index(drop=True)
    table_hash = canonical_dataframe_hash(table)
    assert table_hash == canonical_dataframe_hash(reordered)

    with TableHashRegistry(tmp_path / "uniqueness.sqlite") as registry:
        assert registry.claim(
            table_hash,
            "chart-1",
            dataset_source="sample",
            library="matplotlib",
            source_sample_id="source-sample-1",
        )
        assert not registry.claim(
            table_hash,
            "chart-2",
            dataset_source="sample",
            library="plotly",
            source_sample_id="source-sample-2",
        )
        assert not registry.claim(
            canonical_dataframe_hash(
                pd.DataFrame({"category": ["a", "b"], "value": [3.0, 4.0]})
            ),
            "chart-3",
            dataset_source="sample",
            library="altair",
            source_sample_id="source-sample-1",
        )


def test_line_and_pie_samplers_are_reproducible() -> None:
    dates = pd.date_range("2022-01-01", periods=24, freq="MS")
    frame = pd.DataFrame(
        [
            {
                "YEAR": date.year,
                "MONTH": date.month,
                "date": date,
                "ITEM TYPE": f"Type {row % 6}",
                "SUPPLIER": f"Supplier {row % 10}",
                "RETAIL SALES": float(row + period + 1),
                "WAREHOUSE SALES": float(row * 2 + period + 2),
            }
            for period, date in enumerate(dates)
            for row in range(20)
        ]
    )
    frame.attrs.update(dataset_name="warehouse", source_fingerprint="v1")
    spec = {
        "numeric_cols": ["RETAIL SALES", "WAREHOUSE SALES"],
        "group_cols": ["ITEM TYPE", "SUPPLIER"],
        "agg_cols": ["YEAR", "MONTH"],
        "date_col": "date",
    }

    cases = [
        (sample_line_data_from_df, {"n_lines": 2}),
        (sample_pie_data_from_df, {"slice_count": 6}),
    ]
    for sampler, style in cases:
        first = sampler(frame, spec, np.random.default_rng(41), style)
        repeated = sampler(frame, spec, np.random.default_rng(41), style)
        assert first is not None and repeated is not None
        pd.testing.assert_frame_equal(first[0], repeated[0])
        assert first[1] == repeated[1]
        sampling = first[1]["sampling"]
        assert sampling["replacement"] is False
        assert sampling["sampled_rows"] < sampling["population_rows"]


def test_scatter_sampler_uses_unique_source_rows() -> None:
    notebook_path = (
        PROJECT
        / "notebooks"
        / "final_notebook_v1"
        / "notebooks"
        / "scatter_generator_FINAL.ipynb"
    )
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    namespace = {
        "np": np,
        "pd": pd,
        "SCATTER_AGGREGATIONS": AggregationCache(persist=False),
    }
    exec("".join(notebook["cells"][17]["source"]), namespace)
    sample = namespace["sample_scatter_data_from_df"]
    style = {"n_groups": 2, "n_colors": 2, "n_shapes": 1, "direct_labels": 0}

    warehouse = pd.DataFrame(
        {
            "YEAR": np.repeat([2023, 2024], 20),
            "MONTH": np.tile(np.repeat([1, 2, 3, 4], 5), 2),
            "SUPPLIER": np.tile([f"Supplier {i}" for i in range(10)], 4),
            "ITEM TYPE": np.tile(["A", "B", "C", "D", "E"], 8),
            "RETAIL SALES": np.arange(1, 41),
            "WAREHOUSE SALES": np.arange(41, 81),
            "RETAIL TRANSFERS": np.arange(81, 121),
        }
    )
    warehouse.attrs.update(dataset_name="warehouse", source_fingerprint="v1")
    warehouse_spec = {
        "numeric_cols": ["RETAIL SALES", "WAREHOUSE SALES", "RETAIL TRANSFERS"],
        "group_cols": ["ITEM TYPE", "SUPPLIER"],
        "agg_cols": ["YEAR", "MONTH"],
    }

    collision_rows = []
    for borough_index, borough in enumerate(["A", "B", "C", "D", "E"]):
        for year in [2023, 2024]:
            for month in range(1, 5):
                collision_rows.append(
                    {
                        "BOROUGH": borough,
                        "YEAR": year,
                        "MONTH": month,
                        "CRASH_COUNT": 10 + borough_index + month,
                        "NUMBER OF PERSONS INJURED": 4 + borough_index + month,
                        "NUMBER OF PERSONS KILLED": 1 + borough_index,
                        "INJURY_RATE": 0.2 + month / 100,
                    }
                )
    collision = pd.DataFrame(collision_rows)
    collision.attrs.update(dataset_name="collision", source_fingerprint="v1")
    collision_spec = {
        "numeric_cols": [
            "CRASH_COUNT",
            "NUMBER OF PERSONS INJURED",
            "NUMBER OF PERSONS KILLED",
            "INJURY_RATE",
        ],
        "group_cols": ["BOROUGH"],
        "agg_cols": ["YEAR", "MONTH"],
    }

    london = pd.DataFrame(
        [
            {
                "BOROUGH": f"Borough {borough}",
                "SECTOR": f"Sector {sector}",
                "YEAR": year,
                "EMPLOYEE_JOBS": 100 + borough * 10 + sector,
            }
            for year in [2023, 2024]
            for borough in range(6)
            for sector in range(6)
        ]
    )
    london.attrs.update(dataset_name="london", source_fingerprint="v1")
    london_spec = {
        "numeric_cols": ["EMPLOYEE_JOBS"],
        "group_cols": ["BOROUGH", "SECTOR"],
        "agg_cols": ["YEAR"],
    }

    for frame, spec in [
        (warehouse, warehouse_spec),
        (collision, collision_spec),
        (london, london_spec),
    ]:
        result = sample(frame, spec, np.random.default_rng(7), style)
        assert result is not None
        plot_frame, context = result
        assert len(plot_frame) >= 3
        assert np.isfinite(plot_frame[["x", "y"]].to_numpy()).all()
        assert context["n_points"] == len(plot_frame)
        assert context["sampling"]["replacement"] is False
        assert context["sampling"]["source_sample_id"]


def test_json_cache_flushes_atomically(tmp_path: Path) -> None:
    path = tmp_path / "titles.json"
    cache = JsonCache(path, flush_every=2)
    cache.set("one", ["Title", None])
    assert not path.exists()
    cache.set("two", ["Other", "Subtitle"])
    assert json.loads(path.read_text(encoding="utf-8"))["two"][1] == "Subtitle"


def test_find_project_root(tmp_path: Path) -> None:
    root = tmp_path / "project"
    nested = root / "notebooks" / "nested"
    nested.mkdir(parents=True)
    (root / "data").mkdir()
    (root / "requirements.txt").write_text("pandas\n", encoding="utf-8")
    assert find_project_root(nested) == root
