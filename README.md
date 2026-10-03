# I2R Automated Chart Dataset Generator

This project generates chart datasets consisting of a chart image, the data table
used to create it, and structured metadata. It currently supports bar, line, pie,
and scatter charts rendered with Altair, Matplotlib, Seaborn, and Plotly.

The intended production dataset contains approximately 400,000 charts:

- 100,000 bar charts
- 100,000 line charts
- 100,000 pie charts
- 100,000 scatter charts
- Equal numbers from each plotting library within every chart type
- Equal use of each source dataset, with a different underlying sample for every chart
- Style parameters sampled with the existing observed weights
- Reproducible generation from fixed inputs and seeds

## Project status

This repository is currently a working notebook-based development checkpoint. The
four generators can create SVG/CSV/JSON artifact sets using real source data,
deterministic seeds, weighted styles, reusable data caches, and persistent uniqueness
checks.

It is **not yet the final one-command production pipeline**. In particular, automatic
dataset downloads, exact dataset quotas, per-chart failure recovery and validation
logs, a scheduler-safe worker design, and a command-line entry point still need to be
implemented. See [Remaining work](#remaining-work).

## Final generator notebooks

The active notebooks are:

```text
notebooks/final_notebook_v1/notebooks/
├── bar_generator_FINAL.ipynb
├── line_generator_FINAL.ipynb
├── pie_generator_FINAL.ipynb
└── scatter_generator_FINAL.ipynb
```

Files in `old_notebooks/` and scripts such as `fix_line_prompt.py` are not part of the
current production path.

## What is implemented

### Chart generation

- Four chart types: bar, line, pie, and scatter.
- Four plotting libraries: Altair, Matplotlib, Seaborn, and Plotly.
- Chart images are saved as SVG for every library.
- Each chart has a matching CSV table and JSON metadata file.
- The observed style distributions already present in each notebook are used for
  weighted parameter sampling.
- Template-based titles are the fast default. Cached Ollama-generated titles are
  available as an optional mode.

### Data sampling and uniqueness

The production sampling functions are in:

```text
src/bar_sampling.py
src/line_sampling.py
src/pie_sampling.py
src/scatter_sampling.py
src/sampling_common.py
```

For a fixed source-data snapshot and seed, sampling and chart IDs are deterministic.
The samplers select source rows without replacement within a chart and record sampling
details in the metadata, including filters, population size, sampled-row count,
sampling fraction, and `source_sample_id`.

Each chart type maintains a SQLite uniqueness manifest. Both the selected source rows
and the canonical plotted table are checked before an artifact set is accepted. A
duplicate is retried up to the notebook's configured attempt limit.

This prevents duplicate samples within one output/manifest history. It does not yet
guarantee that 100,000 valid unique samples exist for every combination; that must be
established with scale testing.

### Runtime improvements

- Large CSV files are cleaned once and cached as compressed Parquet files.
- Only required CSV columns are read where the shared registry specifies them.
- Expensive aggregations are cached in memory and on disk.
- Complete existing SVG/CSV/JSON triples can be reused when resume mode is enabled.
- Deterministic chart IDs make disjoint seed ranges possible.
- Machine-specific absolute paths have been replaced with project-relative paths and
  environment-variable overrides.

The shared cache, manifest, and dataset utilities live in `src/bar_runtime.py` and
`src/bar_datasets.py`. Despite their historical names, parts of the runtime module are
used by all four chart generators.

## Source datasets

The current registry supports these sources:

| Registry name | Source | Current repository state |
| --- | --- | --- |
| `warehouse_retail` | [Warehouse and Retail Sales](https://catalog.data.gov/dataset/warehouse-and-retail-sales) | CSV currently tracked in `data/train/` |
| `london_borough_sector_jobs` | [Borough by Sector Employee Jobs](https://data.london.gov.uk/dataset/borough-by-sector-employee-jobs-emqdl) | CSV currently tracked in `data/train/` |
| `motor_vehicle_collisions` | NYC Motor Vehicle Collisions | Expected as `data/train/Motor_Vehicle_Collisions_-_Crashes.csv`; excluded from Git because of its size |

The collision code expects crash-level columns such as `CRASH DATE`, `CRASH TIME`,
injury counts, and contributing factors. The NYC link supplied during development
points to the **Vehicles** table (`bm4k-52h4`), so the intended crash export/source URL
must be confirmed before the automatic downloader is implemented.

At present, missing datasets are skipped. Therefore a fresh clone contains the two
tracked datasets and can run with those sources, but does not contain the collision
CSV. Dataset downloading is not automated yet.

## Current setup and use

Python dependencies are listed in `requirements.txt`. A current manual setup is:

```bash
python -m venv i2r
source i2r/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pytest
python -m pytest tests -q
jupyter notebook
```

On PowerShell, activate the environment with `i2r\Scripts\Activate.ps1` instead of
the `source` command. `pytest` is currently installed separately because a dedicated
development-dependency file has not yet been added.

Open and run the desired `*_FINAL.ipynb` notebook. There is not yet a supported
non-interactive command that generates all chart types from the terminal.

The bar dataset cache can optionally be prepared before opening the notebook:

```bash
python -m src.bar_datasets --project-root .
```

This command prepares the bar cache only. The other notebooks currently build their
own chart-type cache when they are executed.

### Current defaults

Each notebook currently generates 25 charts per library, or 100 charts total. The
target of 100,000 charts per chart type would require 25,000 charts per library.
Large production runs should wait until the remaining reliability and scale tasks are
complete.

Configuration is read from environment variables:

| Variable | Meaning |
| --- | --- |
| `I2R_PROJECT_ROOT` | Repository root; normally detected automatically |
| `I2R_DATA_TRAIN` | Directory containing the source CSV files |
| `I2R_<TYPE>_CACHE` | Cache root for `BAR`, `LINE`, `PIE`, or `SCATTER` |
| `I2R_<TYPE>_OUTPUT` | Output root for a chart type |
| `I2R_<TYPE>_CHARTS_PER_LIBRARY` | Number generated for each of the four libraries |
| `I2R_<TYPE>_START_SEED` | First deterministic seed for the run |
| `I2R_<TYPE>_TITLE_MODE` | `template` (default) or `ollama` |
| `I2R_OLLAMA_MODEL` | Ollama model used when title mode is `ollama` |
| `I2R_RESUME_OUTPUT` | `1` reuses complete existing artifact triples |
| `I2R_CLEAR_OUTPUT` | `1` deletes the selected chart type's output root before generation |

For example, in Bash:

```bash
export I2R_PROJECT_ROOT=/path/to/I2R
export I2R_LINE_CHARTS_PER_LIBRARY=25
export I2R_LINE_START_SEED=1000
export I2R_LINE_TITLE_MODE=template
export I2R_RESUME_OUTPUT=1
export I2R_CLEAR_OUTPUT=0
```

In PowerShell, the equivalent assignment syntax is:

```powershell
$env:I2R_PROJECT_ROOT = "C:\path\to\I2R"
$env:I2R_LINE_CHARTS_PER_LIBRARY = "25"
$env:I2R_LINE_START_SEED = "1000"
$env:I2R_LINE_TITLE_MODE = "template"
$env:I2R_RESUME_OUTPUT = "1"
$env:I2R_CLEAR_OUTPUT = "0"
```

> **Important:** the bar notebook currently defaults `I2R_CLEAR_OUTPUT` to `1`, a
> temporary development setting. Line, pie, and scatter default it to `0`. Always set
> `I2R_CLEAR_OUTPUT=0` for a resumable run. Normalizing this default is part of the
> remaining production work.

## Output structure

Unless a chart-specific output variable overrides it, outputs are written under:

```text
notebooks/final_notebook_v1/outputs/generated/
```

Each chart type has this structure:

```text
<chart-type>plots/
├── images/
│   ├── altair/*.svg
│   ├── matplotlib/*.svg
│   ├── plotly/*.svg
│   └── seaborn/*.svg
├── metadata/
│   └── <library>/*.json
├── tables/
│   └── <library>/*.csv
└── manifests/
    └── <chart-type>_uniqueness.sqlite
```

Generated outputs, processed caches, and the large collision CSV are ignored by Git.
Keep the uniqueness manifest together with its output directory when resuming or
moving a run.

## Reproducibility and recovery

- The same source-data snapshot, seed, chart type, library, and configuration produce
  the same sampling and style choices.
- Chart IDs contain the chart type, library, and seed.
- A run with `I2R_RESUME_OUTPUT=1` skips an ID only when its SVG, CSV, and JSON files
  all exist.
- A failed run can be restarted with the same settings and `I2R_CLEAR_OUTPUT=0` to
  retain completed charts.

Current limitation: an exception from one chart stops the active batch. Restarting
resumes completed triples, but the batch does not yet log the failed seed and continue
automatically.

## Tests

Run the current automated tests with:

```bash
python -m pytest tests -q
```

The current suite contains nine tests covering notebook code-cell compilation, cache
behavior, deterministic sampling, within-chart row uniqueness, cross-chart uniqueness
claims, atomic title-cache writes, and project-root discovery.

The suite does not yet constitute a full rendering or production-scale test. Automated
SVG/CSV/JSON integrity checks and end-to-end tests for every chart type/library pair
remain to be added.

## Remaining work

The following tasks are ordered so they can be implemented and reviewed one at a time:

1. **Add an automatic dataset downloader.** Download all three authoritative sources,
   confirm the correct NYC crash dataset, validate expected schemas, record source
   versions/checksums, and document licenses and attribution.
2. **Add one terminal entry point.** Provide a command that performs setup checks,
   prepares datasets, and generates one or all chart types without manually executing
   notebooks. Keep notebooks as development and inspection interfaces.
3. **Make the Python environment reproducible.** State the supported Python version
   and add a pinned lock file, Conda environment, or container definition. Separate
   optional Ollama support if appropriate.
4. **Centralize and safeguard configuration.** Move production settings out of
   notebook cells, default output clearing to off for every chart type, validate paths
   and counts, and save the resolved run configuration with the output.
5. **Implement exact generation quotas.** Schedule exactly 100,000 charts per type,
   25,000 per plotting library, and equal source-dataset counts instead of choosing a
   dataset independently at random. Preserve the existing observed style weights.
6. **Add fault-tolerant execution and structured logs.** Catch failures per chart,
   record the chart type/library/dataset/seed/error, continue the batch, enforce a
   retry policy, and write a final success/failure summary.
7. **Design and validate parallel workers.** Define deterministic non-overlapping
   seed/shard assignments, avoid unsafe shared-manifest behavior on network file
   systems, and provide a merge step for worker outputs and uniqueness records.
8. **Add dataset validation.** Verify every SVG is readable, every artifact triple is
   complete, metadata matches the CSV and filename, hashes are unique, and final
   library/dataset/style distributions satisfy their targets.
9. **Run staged scale tests.** Test small, medium, and node-sized batches; measure
   throughput, memory, disk use, cache effectiveness, collision/retry rates, and
   whether each sampler can supply the required number of unique charts.
10. **Finish repository automation and documentation.** Add continuous integration,
    a license, data citations, a production runbook, recovery instructions, and a
    documented release/tag once the pipeline is validated.

## Known limitations

- Dataset selection is currently random, so source use is approximately—not exactly—
  balanced.
- Resume-on-restart exists, but continue-after-error within a batch does not.
- Multi-worker and scheduler execution have not yet been validated.
- The bar notebook's temporary default clears its output unless explicitly disabled.
- The collision dataset source and automatic download still need to be finalized.
- The present tests focus on runtime and sampling logic rather than full-scale output
  validation.
