# Power BI report

A {{n_pbi_pages}}-page report built on a model of {{n_pbi_tables}} tables and {{n_measures}} DAX measures. It uses the same numbers as the web dashboard and the documents, because all three are generated from the same results in `data/processed`.

## Opening it

| File | Use it for |
|---|---|
| [`PSX_Sector_Risk_Return.pbix`](../powerbi/PSX_Sector_Risk_Return.pbix) | **Just looking.** The data is inside; double-click and it opens. Needs Power BI Desktop (free from Microsoft). |
| [`PSX_Sector_Risk_Return.pbip`](../powerbi/PSX_Sector_Risk_Return.pbip) | **Working on it, or reading it in Git.** A Power BI project: the model is plain text (TMDL) and each page and visual is a small JSON file. A project stores no data, so Power BI Desktop shows a **Refresh now** banner the first time; click it once and wait. |
| [`measures.dax`](../powerbi/measures.dax) | Every measure as text, grouped by folder, with a description. |

`python -m psxsec powerbi` (also run by `python -m psxsec report`) regenerates the project and `measures.dax`. The `.pbix` is a snapshot saved from the opened project (File, Save as) and is not rewritten by that command.

## Pages

{{table_pbi_pages}}

Slicers cross-filter the other visuals on a page. The sector slicer on **Sector detail** filters the year-by-year and rank charts through the relationships below, and the portfolio slicer on **Portfolios** filters the weights.

## Preview

Every page, exported from Power BI Desktop (File, Export, Export to PDF) and saved as an image. Click an image for the full size.

{{pbi_gallery_all}}

## Data model

{{table_pbi_tables}}

```
sectors ──< year_returns          preset_stats ──< presets
   └──────< rank_choices
(one to many)                     (one to many)
```

Only three tables are related. The rest are read by measures that filter them directly (for example `strategies[strategy_key] = "winners"`) or are plotted by themselves, like the weekly growth tables. Each table is stored in the model itself as compressed text, which is how Power BI keeps "Enter data" tables, so the project needs no other file. Text columns that should not sort alphabetically carry a `sortByColumn` (the twelve-month periods, the rules, the portfolios, the legend of the alpha chart).

## Measures

{{table_pbi_measures}}

A few patterns worth knowing:

- **Measures live in a table called `_Measures`.** Power BI rejects a table named `Measures`.
- **A number about the whole market is read from a one-row table.** `Market Return a Year` is `MAX ( market[market_cagr] )`, and the text measures (`Top Sector by Sharpe`) use `SELECTEDVALUE`, because `MAX` does not work on text.
- **A per-sector measure is an average over one row.** `Sharpe Ratio` is `AVERAGE ( sectors[sharpe] )`: a bar chart with one bar per sector shows each sector's value, and a card shows that sector's value when the sector slicer has one selected.
- **Counting is done in the measure, not stored.** `Alpha Significant After Correction` counts the sectors whose corrected p-value is below 0.05, so it answers to any slicer. It is wrapped in `COALESCE` because a count of nothing is blank in DAX and a card would show "(Blank)" instead of 0:

  ```dax
{{dax_alpha_after}}
  ```
- **A measure that shows the right amount.** Plotting all {{n_sectors_ranked}} sectors and the market on one chart is unreadable, so on **Ups and downs** the list picks the series and the measure draws them when between one and eight are picked. Until the reader picks, it draws only the whole market and cash:

  ```dax
{{dax_selected_level}}
  ```
  The table is written `'levels'` because Power BI reads the bare word `levels` as a keyword ("the syntax for 'levels' is incorrect"). Evaluating every measure in Desktop is what found it.
- **A second series without a relationship.** The sector against the whole market, period by period, uses `TREATAS` to line the market's table up with the periods in view:

  ```dax
  Market Year Return =
  CALCULATE (
      AVERAGE ( market_years[period_return] ),
      TREATAS ( VALUES ( year_returns[period_index] ), market_years[period_index] )
  )
  ```

## How it was built and checked

{{pbi_checked}}

## Limits

- Built and tested with a current Power BI Desktop (the project format needs a recent version). Older versions may not open the `.pbip`; the `.pbix` is saved by the version used here.
- The `.pbix` and the page images in [`powerbi_pages`](powerbi_pages) come from Power BI Desktop and are not rewritten by `python -m psxsec report`. If the data or the generator change, open the project, refresh, check the pages and save them again; a test fails when the `.pbix` no longer matches the report.
- The model holds the results of the analysis, not the prices: it cannot recompute a sector's Sharpe ratio from daily returns, and the bootstrap, the market model and the walk-forward test are done in Python (see the [methodology](methodology.md)).
- The portfolio builder with free weights is on the [web dashboard](https://maira-w.github.io/psx-sector-risk-return/); the Power BI report shows the four preset portfolios.
- The preset portfolios use weights worked out with hindsight from the whole five years. They show what diversification does and are not a test or a forecast. This is analysis, not investment advice.
