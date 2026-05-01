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
