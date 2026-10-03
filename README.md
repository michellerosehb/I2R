# Automated Chart Generator Project

This repository contains code for automated chart generation across multiple chart types. The goal of the project is to generate chart images together with their corresponding metadata and data tables. These outputs can then be used to inspect, compare, and further analyze different chart parameter settings.

## What has been done

Notebooks for all automated chart generators are done. The project currently contains generator notebooks for the following chart types:

- Bar charts
- Line charts
- Pie charts
- Scatter plots

The main updated notebooks are:

```text
updated_bar_generator.ipynb
updated_line_generator.ipynb
updated_pie_generation.ipynb
updated_scatter_generator.ipynb
```

Each notebook generates a different chart type, but the notebooks have a similar structure. They contain code for generating charts with different plotting libraries, saving the generated chart images, saving the data tables used for the charts, and saving metadata for each generated chart.

The `updated_[chart type]_generator.ipynb` documents contain the code that creates a testing function. This testing function creates an image, metadata file, and table file for each parameter setting. The parameter settings are based on the values found while manually labeling the 100 charts per chart type.

This makes it possible to check whether every individual parameter setting works correctly and whether the visual output matches the intended chart design.

## Supported chart types

The current notebooks support the following chart types:

```text
barplots
lineplots
pieplots
scatterplots
```

Each chart type has its own notebook and its own output folder.

## Supported plotting libraries

The chart generators currently support multiple plotting libraries:

```text
matplotlib
seaborn
plotly
altair
```

Each notebook contains a testing cell to test whether chart generation works for each library. The notebooks also contain a testing cell that generates an image for each library and for each parameter setting. These generated images are saved with filenames that include the parameter setting, so they can be checked manually.

## Output structure

The normal generated chart outputs are saved outside the `notebooks` folder.

The normal outputs are saved in:

```text
outputs/generated/
```

For example:

```text
outputs/generated/barplots/
outputs/generated/lineplots/
outputs/generated/pieplots/
outputs/generated/scatterplots/
```

The testing outputs are saved separately in:

```text
testing/
```

For example:

```text
testing/bar_testing/
testing/line_testing/
testing/pie_testing/
testing/scatter_testing/
```

Both the normal output folders and the testing folders contain subfolders for:

```text
images/
metadata/
tables/
```

These folders are again divided by plotting library. The structure is therefore:

```text
images/matplotlib/
images/seaborn/
images/plotly/
images/altair/

metadata/matplotlib/
metadata/seaborn/
metadata/plotly/
metadata/altair/

tables/matplotlib/
tables/seaborn/
tables/plotly/
tables/altair/
```

This structure makes it easier to compare the output per chart type, per plotting library, and per parameter setting.

## Metadata and tables

For every generated chart, the notebooks save three types of output:

1. The chart image
2. The metadata file
3. The data table used to create the chart

The metadata contains information about the chart type, plotting library, selected parameter settings, and other relevant generation details. The table file contains the actual data used to create the chart.

Saving these files together makes it easier to inspect whether the generated chart matches the metadata and whether the parameter settings were applied correctly.

## Weighted parameter selection

The notebooks are designed to support weighted parameter selection. This means that parameter values can be sampled according to predefined weights.

For example, if a certain chart parameter value should appear more often in the generated dataset, it can receive a higher weight. If another parameter value should appear less often, it can receive a lower weight.

The goal is to control the fraction of generated charts that contain each parameter value. This is important because the generated dataset should reflect the intended distribution of chart features.

## Important notes

Only one dataset is used now. This means that the current generated charts are limited in terms of data variety. More datasets should be added later to make the generated charts more diverse and realistic.

The current chart titles, subtitles, and axis titles are also not yet very realistic. At the moment, they are mostly generated in a simple or rule-based way. I will look into using LLMs for this, so that the generated titles and labels become more natural and realistic.

## To do

The following tasks still need to be completed:

- Finalize the weighted selection of parameter settings.
  - This includes finalizing the last charts that need to be sampled.
  - The final parameter weights should be based on the manually labeled charts.

- Improve chart titles, subtitles, and axis titles.
  - These are currently not really realistic.
  - I will look into LLMs for generating more natural chart text.

- Find more datasets.
  - Currently, only one dataset is used.
  - More datasets are needed to increase the variety of the generated charts.

- Write the final report and documentation.
  - The report should explain the structure of the notebooks.
  - It should describe the chart parameters, weighted sampling, testing functions, and output structure.
  - It should also discuss limitations and future improvements.

## Current project goal

The current goal of the project is to create a complete and structured chart generation pipeline. The pipeline should be able to generate chart images automatically, save the corresponding metadata and tables, and test every parameter setting separately.

This makes it possible to inspect the generated charts in a systematic way and to improve the chart generation process step by step.

## High-throughput generation

All four final notebooks support cached, resumable generation for computational nodes:

```text
notebooks/final_notebook_v1/notebooks/bar_generator_FINAL.ipynb
notebooks/final_notebook_v1/notebooks/line_generator_FINAL.ipynb
notebooks/final_notebook_v1/notebooks/pie_generator_FINAL.ipynb
notebooks/final_notebook_v1/notebooks/scatter_generator_FINAL.ipynb
```

Every generated example is a complete SVG/CSV/JSON triple. IDs are deterministic from
the chart type, plotting library, and seed, so an interrupted run can safely resume.

Prepare the cleaned Parquet datasets once before starting a large batch:

```bash
python -m src.bar_datasets --project-root .
```

The first run of each notebook reads and cleans the source CSV files. Later runs load
Parquet files from `data/processed/<chart-type>/datasets/`. Expensive group-by results
are cached lazily under `data/processed/<chart-type>/aggregations/`. The standalone
command above currently prebuilds the bar cache; the other notebooks build their
cache once when first executed.

### Chart data sampling and uniqueness

The production samplers live in `src/bar_sampling.py`, `src/line_sampling.py`,
`src/pie_sampling.py`, and `src/scatter_sampling.py`. Each sampler first selects a
meaningful dataset or time slice and then samples source rows without replacement.
Selection is deterministic for a fixed source snapshot and RNG seed. Reusable
row-position indexes avoid rescanning a large source dataset for every chart.

Metadata records the filters, eligible population size, sampled-row count, sampling
fraction, and `source_sample_id`. The final plotted table is also assigned a canonical
`sample_hash`. Both identifiers are claimed in the chart type's manifest, for example
`manifests/line_uniqueness.sqlite`. If either the source rows or resulting table were
already used, generation retries before writing output. Keep each manifest with its
output directory when resuming a run.

The notebook is configured through environment variables:

```bash
export I2R_PROJECT_ROOT=/path/to/I2R
export I2R_BAR_OUTPUT=/path/to/generated/barplots
export I2R_BAR_CHARTS_PER_LIBRARY=2500
export I2R_BAR_START_SEED=1000
export I2R_BAR_TITLE_MODE=template
export I2R_CLEAR_OUTPUT=0
export I2R_RESUME_OUTPUT=1
```

For line, pie, or scatter, replace `BAR` in the chart-specific variables with `LINE`,
`PIE`, or `SCATTER`. For example, use `I2R_LINE_CHARTS_PER_LIBRARY` and
`I2R_LINE_START_SEED`. The optional output variables are `I2R_BAR_OUTPUT`,
`I2R_LINE_OUTPUT`, `I2R_PIE_OUTPUT`, and `I2R_SCATTER_OUTPUT`.

`template` title mode is the fast production default. Set the chart-specific title
mode to `ollama` to generate titles with Ollama; responses are cached under that
chart type's processed-data directory.

For a multi-process or scheduler-array run, build the dataset cache first and assign
each worker a disjoint start-seed range. Workers may share the same output and
aggregation-cache directories because chart IDs are deterministic and aggregation
cache writes are atomic. Use template title mode for parallel jobs; each JSON Ollama
title cache is intended for a single writer.

Plotly SVG export is pinned to Plotly 6 with Kaleido 0.2.1 so it works on a headless
node without installing Chrome.
