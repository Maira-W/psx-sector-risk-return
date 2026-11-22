"""The Power BI report, written in the project format Power BI Desktop itself saves (PBIR).

Each page is a folder with a page.json and one visual.json per visual. A visual is described by a small spec: a
title, a Power BI visual type, the fields for each role and a position on a 1280 x 720 page. A field is
(table, name); measures live in _Measures and everything else is a column.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from .. import config
from .model import PROJECT, tag

PAGE_W, PAGE_H = 1280, 720
GAP = 16

SCHEMAS = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition"
VISUAL_SCHEMA = f"{SCHEMAS}/visualContainer/2.14.0/schema.json"
PAGE_SCHEMA = f"{SCHEMAS}/page/2.1.0/schema.json"
PAGES_SCHEMA = f"{SCHEMAS}/pagesMetadata/1.1.0/schema.json"
REPORT_SCHEMA = f"{SCHEMAS}/report/3.3.0/schema.json"
VERSION_SCHEMA = f"{SCHEMAS}/versionMetadata/1.0.0/schema.json"
THEME_FILE = "PSXSectors.json"

PAGE_BACKGROUND = "#F3F5F8"
PANEL = "#FFFFFF"
BORDER = "#D9DEE5"
MUTED = "#4A5568"

# Column headers shown in table visuals (the model keeps the machine-friendly column names).
HEADERS = {
    "sector": "Sector", "n_companies": "Companies", "cagr": "Return a year", "volatility": "Volatility", "max_drawdown": "Worst fall",
    "sharpe": "Sharpe", "sharpe_lo": "Sharpe, low", "sharpe_hi": "Sharpe, high", "p_top1": "Chance of first", "p_top3": "Chance of top 3",
    "p_beats_market": "Chance beats market", "dividend_points": "From dividends", "beta": "Beta", "alpha": "Alpha a year", "alpha_t": "t",
    "alpha_p": "p alone", "alpha_p_adjusted": "p corrected", "alpha_q": "q", "dsr": "Deflated Sharpe", "sortino": "Sortino",
    "cvar_95": "Bad-day loss", "up_capture": "Up capture", "down_capture": "Down capture", "longest_fall_months": "Longest fall (months)",
    "choice": "Analysis", "kind": "Kind", "sectors_compared": "Sectors compared", "rank_correlation": "Rank correlation",
    "top3_in_common": "Top 3 in common", "main_top_sector": "Main top sector", "strategy": "Rule", "sharpe_vs_equal": "Sharpe vs equal",
    "vs_equal_p": "p", "vs_equal_p_adjusted": "p corrected", "turnover": "Traded monthly", "setting": "Look-back and sectors held",
    "months": "Months", "sharpe_rule": "Sharpe of the rule", "sharpe_equal_weight": "Sharpe, equal weight", "difference": "Difference",
    "p": "p", "preset": "Portfolio", "sectors_held": "Sectors held", "group_letter": "Group", "n_sectors": "Sectors", "sectors": "Sectors in the group",
    "topic": "Topic", "note": "Note", "short_name": "Sector",
}

Field = tuple[str, str]


def col(table: str, name: str) -> Field:
    return (table, name)


def msr(name: str) -> Field:
    return ("_Measures", name)


# ---------------------------------------------------------------------------
# visual specs
# ---------------------------------------------------------------------------
def spec(title: str, vtype: str, roles: dict[str, list[Field]], x: int, y: int, w: int, h: int,
         labels: bool = False, sort: str | None = None, log: bool = False, widths: dict[Field, int] | None = None,
         axis_titles: bool = True) -> dict:
    return {"title": title, "type": vtype, "roles": roles, "x": x, "y": y, "w": w, "h": h, "labels": labels,
            "sort": sort, "log": log, "widths": widths or {}, "axis_titles": axis_titles}


def card(title: str, measure: str, x: int, y: int, w: int, h: int = 104) -> dict:
    return spec(title, "card", {"Values": [msr(measure)]}, x, y, w, h)


def cards_row(items: list[tuple[str, str]], y: int = GAP, x: int = GAP, width: int = PAGE_W - 2 * GAP) -> list[dict]:
    n = len(items)
    w = (width - (n - 1) * GAP) // n
    return [card(title, measure, x + i * (w + GAP), y, w) for i, (title, measure) in enumerate(items)]


def slicer(title: str, field: Field, x: int, y: int, w: int, h: int) -> dict:
    return spec(title, "slicer", {"Values": [field]}, x, y, w, h)


def line(title: str, category: Field, measures: list[str], x: int, y: int, w: int, h: int, series: Field | None = None,
         log: bool = False) -> dict:
    roles = {"Category": [category], "Y": [msr(m) for m in measures]}
    if series:
        roles["Series"] = [series]
    return spec(title, "lineChart", roles, x, y, w, h, log=log)


def bars(title: str, category: Field, measures: list[str], x: int, y: int, w: int, h: int,
         series: Field | None = None, labels: bool = True, sort: str | None = None) -> dict:
    """Horizontal bars. sort="Descending" orders the bars by the first measure, largest at the top."""
    roles = {"Category": [category], "Y": [msr(m) for m in measures]}
    if series:
        roles["Series"] = [series]
    return spec(title, "clusteredBarChart", roles, x, y, w, h, labels=labels, sort=sort)


def columns(title: str, category: Field, measures: list[str], x: int, y: int, w: int, h: int,
            series: Field | None = None, labels: bool = False) -> dict:
    roles = {"Category": [category], "Y": [msr(m) for m in measures]}
    if series:
        roles["Series"] = [series]
    return spec(title, "clusteredColumnChart", roles, x, y, w, h, labels=labels)


def scatter(title: str, category: Field, x_measure: str, y_measure: str, series: Field | None,
            x: int, y: int, w: int, h: int, size: str | None = None, labels: bool = False, axis_titles: bool = True) -> dict:
    roles = {"Category": [category], "X": [msr(x_measure)], "Y": [msr(y_measure)]}
    if series:
        roles["Series"] = [series]
    if size:
        roles["Size"] = [msr(size)]
    return spec(title, "scatterChart", roles, x, y, w, h, labels=labels, axis_titles=axis_titles)


def table(title: str, columns_: list[Field], x: int, y: int, w: int, h: int, widths: dict[Field, int] | None = None) -> dict:
    return spec(title, "tableEx", {"Values": columns_}, x, y, w, h, widths=widths)


# ---------------------------------------------------------------------------
# pages
# ---------------------------------------------------------------------------
RAIL = 200                      # width of the slicer column on the left of a page
BODY_Y = 136                    # where charts start, below a row of cards
BODY_H = PAGE_H - BODY_Y - GAP  # 568
FULL = PAGE_W - 2 * GAP         # 1248


def page_overview() -> list[dict]:
    return cards_row([
        ("Whole market, a year", "Market Return a Year"),
        ("Cash at the policy rate", "Cash Return a Year"),
        ("Whole market Sharpe ratio", "Market Sharpe"),
        ("Best by Sharpe ratio", "Top Sector by Sharpe"),
        ("Companies analysed", "Companies Analysed"),
    ]) + [
        bars("Return per unit of risk: Sharpe ratio, by sector", col("sectors", "short_name"), ["Sharpe Ratio"],
             GAP, BODY_Y, 560, BODY_H, sort="Descending"),
        scatter("Risk and return: each dot is a sector", col("sectors", "short_name"), "Volatility",
                "Return a Year", None, GAP + 560 + GAP, BODY_Y, FULL - 560 - GAP, BODY_H, labels=True),
    ]


def page_scorecard() -> list[dict]:
    names = ["sector", "n_companies", "cagr", "volatility", "max_drawdown", "sharpe", "sharpe_lo", "sharpe_hi", "p_top1", "p_top3",
             "p_beats_market", "dividend_points"]
    widths = [215, 80, 95, 85, 85, 70, 85, 85, 95, 95, 105, 100]
    return [table("Every ranked sector (click a heading to sort)", [col("sectors", n) for n in names], GAP, GAP, FULL, PAGE_H - 2 * GAP,
                  widths={col("sectors", n): w for n, w in zip(names, widths, strict=True)})]


def page_ups() -> list[dict]:
    top_h = 250
    y2 = GAP + top_h + GAP
    h2 = PAGE_H - GAP - y2
    mid = GAP + RAIL + GAP
    w1 = 520
    return [
        line("Best three sectors, the whole market and cash: growth of 100 rupees (log scale)", col("levels_top", "date"),
             ["Highlight Level"], GAP, GAP, FULL, top_h, series=col("levels_top", "series"), log=True),
        slicer("Pick up to eight series", col("levels", "series"), GAP, y2, RAIL, h2),
        line("Growth of 100 rupees, the series you pick (log scale)", col("levels", "date"), ["Selected Level"], mid, y2, w1, h2,
             series=col("levels", "series"), log=True),
        line("Falls from the last peak (%)", col("levels", "date"), ["Selected Drawdown"], mid + w1 + GAP, y2,
             PAGE_W - (mid + w1 + GAP) - GAP, h2, series=col("levels", "series")),
    ]


def page_detail() -> list[dict]:
    rail, mid = 250, GAP + 250 + GAP
    width = PAGE_W - mid - GAP
    chart1 = 460
    return [slicer("Sector", col("sectors", "sector"), GAP, GAP, rail, PAGE_H - 2 * GAP)] + cards_row([
        ("Return a year", "Return a Year"), ("Volatility", "Volatility"), ("Worst fall", "Worst Fall"),
        ("Sharpe ratio", "Sharpe Ratio"), ("Rank by Sharpe", "Rank by Sharpe"),
    ], x=mid, width=width) + [
        columns("Return by twelve-month period: sector and market", col("year_returns", "period"),
                ["Sector Year Return", "Market Year Return"], mid, BODY_Y, chart1, BODY_H, labels=True),
        bars("Sharpe rank under each way of doing it (1 is best)", col("rank_choices", "choice_short"),
             ["Rank in Each Analysis"], mid + chart1 + GAP, BODY_Y, PAGE_W - (mid + chart1 + GAP) - GAP, BODY_H),
    ]


def page_sure() -> list[dict]:
    w = 380
    right = GAP + 2 * (w + GAP)
    names = ["choice", "rank_correlation", "top3_in_common", "main_top_sector"]
    widths = [150, 85, 80, 105]
    return cards_row([
        ("Chance the leader is first", "Top Sector Chance of First"),
        ("Sectors with a 10%+ chance", "Sectors With a 10% Chance of First"),
        ("Methods: rank agreement", "Method Rank Correlation (median)"),
        ("Dates: lowest agreement", "Date Rank Correlation (lowest)"),
        ("First half vs second half", "First vs Second Half Correlation"),
    ]) + [
        bars("Chance of finishing first (%)", col("sectors", "short_name"), ["Chance of First"], GAP, BODY_Y, w, BODY_H, sort="Descending"),
        bars("Chance of finishing in the top three (%)", col("sectors", "short_name"), ["Chance of Top 3"], GAP + w + GAP, BODY_Y, w, BODY_H,
             sort="Descending"),
        table("The 12 other ways of doing the analysis", [col("robustness_summary", n) for n in names], right, BODY_Y, PAGE_W - right - GAP, BODY_H,
              widths={col("robustness_summary", n): v for n, v in zip(names, widths, strict=True)}),
    ]


def page_alpha() -> list[dict]:
    w = 440
    right = GAP + w + GAP
    names = ["short_name", "beta", "alpha", "alpha_p", "alpha_p_adjusted", "dsr", "sortino", "cvar_95", "up_capture", "down_capture"]
    widths = [150, 50, 62, 58, 80, 72, 58, 62, 62, 66]
    return cards_row([
        ("Look real on their own", "Alpha Significant Alone"),
        ("Real after the correction", "Alpha Significant After Correction"),
        ("Largest alpha a year", "Best Alpha"),
        ("Its corrected p-value", "Best Alpha p Corrected"),
        ("Its deflated Sharpe ratio", "Best Deflated Sharpe"),
    ]) + [
        scatter("Alpha against beta: each dot is a sector", col("sectors", "short_name"), "Beta", "Alpha a Year", col("sectors", "alpha_class"),
                GAP, BODY_Y, w, BODY_H, labels=True),
        table("Risk and alpha by sector (click a heading to sort)", [col("sectors", n) for n in names], right, BODY_Y, PAGE_W - right - GAP,
              BODY_H, widths={col("sectors", n): v for n, v in zip(names, widths, strict=True)}),
    ]


def page_moves() -> list[dict]:
    bar_w = 340                                     # the two bar charts run the full height, so every sector has a bar
    x2 = GAP + bar_w + GAP
    right = x2 + bar_w + GAP                        # the sector map, the shares and the groups share the right-hand side
    right_w = PAGE_W - right - GAP
    top_h = 260
    y2 = BODY_Y + top_h + GAP
    bottom_h = BODY_H - top_h - GAP
    share_w = 190
    return cards_row([
        ("Share due to the market", "Market Share of Variation"),
        ("Independent bets", "Effective Bets"),
        ("Average correlation", "Average Correlation"),
        ("Correlation, market out", "Average Correlation Without Market"),
        ("Rate-sensitive sectors", "Sectors Reacting to Rates"),
        ("Rupee-sensitive sectors", "Sectors Reacting to the Rupee"),
    ]) + [
        bars("Extra monthly return per rate point (%)", col("sectors", "short_name"), ["Rate Effect"],
             GAP, BODY_Y, bar_w, BODY_H, sort="Descending"),
        bars("Extra monthly return per 1% rupee fall (%)", col("sectors", "short_name"), ["Rupee Effect"],
             x2, BODY_Y, bar_w, BODY_H, sort="Descending"),
        scatter("Sector map: across is the market, up splits the rest", col("sectors", "short_name"), "Component 1 Loading",
                "Component 2 Loading", col("sectors", "group_letter"), right, BODY_Y, right_w, top_h, labels=True, axis_titles=False),
        bars("Component shares (%)", col("components", "component"), ["Component Share"], right, y2, share_w, bottom_h),
        table("Groups that move together", [col("groups", "group_letter"), col("groups", "sectors")],
              right + share_w + GAP, y2, right_w - share_w - GAP, bottom_h,
              widths={col("groups", "group_letter"): 50, col("groups", "sectors"): 260}),
    ]


def page_oos() -> list[dict]:
    w1 = 620
    right = GAP + w1 + GAP
    h1, h2 = 290, 262
    names = ["strategy", "cagr", "volatility", "sharpe", "sharpe_vs_equal", "vs_equal_p", "vs_equal_p_adjusted", "turnover"]
    widths = [130, 62, 72, 58, 72, 45, 72, 76]
    sens = ["setting", "months", "sharpe_rule", "sharpe_equal_weight", "difference", "p"]
    sens_widths = [150, 60, 85, 90, 80, 60]
    return cards_row([
        ("Best 3: Sharpe out of sample", "Winners Sharpe"),
        ("Equal weight Sharpe", "Equal Weight Sharpe"),
        ("Best 3 vs equal: corrected p", "Winners p Corrected"),
        ("Months pointing the right way", "Months Pointing the Right Way"),
        ("Months tested", "Months Tested"),
    ]) + [
        line("Growth of 100 rupees when each rule sees only the past (log scale)", col("strategy_levels", "date"), ["Strategy Level"],
             GAP, BODY_Y, w1, h1, series=col("strategy_levels", "strategy_short"), log=True),
        table("The rules compared (p compares the Sharpe ratio with equal weights)", [col("strategies", n) for n in names], right, BODY_Y,
              PAGE_W - right - GAP, h1, widths={col("strategies", n): v for n, v in zip(names, widths, strict=True)}),
        columns("Did the past predict the next month? Rank correlation, by month", col("info_coeff", "decision_date"),
                ["Information Coefficient"], GAP, BODY_Y + h1 + GAP, w1, h2),
        table("Other look-backs and numbers of sectors", [col("sensitivity", n) for n in sens], right, BODY_Y + h1 + GAP,
              PAGE_W - right - GAP, h2, widths={col("sensitivity", n): v for n, v in zip(sens, sens_widths, strict=True)}),
    ]


def page_presets() -> list[dict]:
    rail, mid = 250, GAP + 250 + GAP
    width = PAGE_W - mid - GAP
    slicer_h = 128
    bars_y = GAP + slicer_h + GAP
    bars_w = 420
    right = GAP + bars_w + GAP
    line_h = 400
    names = ["preset", "cagr", "volatility", "max_drawdown", "sharpe", "sectors_held"]
    widths = [200, 110, 110, 110, 90, 110]
    return [slicer("Portfolio", col("preset_stats", "preset"), GAP, GAP, rail, slicer_h)] + cards_row([
        ("Return a year", "Preset Return a Year"), ("Volatility", "Preset Volatility"), ("Worst fall", "Preset Worst Fall"),
        ("Sharpe ratio", "Preset Sharpe"),
    ], x=mid, width=width) + [
        bars("Weight of each sector in the portfolio picked (%)", col("presets", "short_name"), ["Preset Weight"], GAP, bars_y,
             bars_w, PAGE_H - GAP - bars_y, sort="Descending"),
        line("Growth of 100 rupees: the four portfolios and the whole market (log scale)", col("preset_levels", "date"), ["Preset Level"],
             right, BODY_Y, PAGE_W - right - GAP, line_h, series=col("preset_levels", "series"), log=True),
        table("The four portfolios over the five years (monthly rebalancing, hindsight weights)", [col("preset_stats", n) for n in names],
              right, BODY_Y + line_h + GAP, PAGE_W - right - GAP, BODY_H - line_h - GAP,
              widths={col("preset_stats", n): v for n, v in zip(names, widths, strict=True)}),
    ]


def page_about() -> list[dict]:
    return [table("About the data and the method", [col("notes", "topic"), col("notes", "note")], GAP, GAP, FULL, PAGE_H - 2 * GAP,
                  widths={col("notes", "topic"): 200, col("notes", "note"): 1000})]


PAGE_NOTES = {
    "overview": "The headline: which sectors paid best for the risk, and how risk and return line up across the 22 ranked sectors.",
    "scorecard": "Every ranked sector in one sortable table: return, volatility, worst fall, Sharpe ratio with its 95% range, and the chances of finishing first.",
    "ups": "Growth of 100 rupees and falls from the last peak: the best three sectors, the market and cash, then any series you pick.",
    "detail": "One sector at a time: its numbers, its return in each twelve-month period against the market, and its rank under every way of doing the analysis.",
    "sure": "How far to trust the order: the chance each sector finishes first or in the top three in 2,000 resampled histories, and the 12 other ways of doing the analysis.",
    "alpha": "Skill or luck: alpha against beta, which sectors look real on their own and after the correction for testing 22, and more measures of risk.",
    "moves": "What moves the sectors: how much is one market-wide movement, the effect of interest rates and the rupee, and the groups that remain.",
    "oos": "Could the ranking have been used? Rules that choose weights using only the past, against equal weights, month by month.",
    "presets": "Four portfolios worked out with hindsight, held with monthly rebalancing: what diversification does.",
    "about": "Sources, definitions and caveats.",
}

PAGES = [
    ("overview", "Overview", page_overview),
    ("scorecard", "Sector scorecard", page_scorecard),
    ("ups", "Ups and downs", page_ups),
    ("detail", "Sector detail", page_detail),
    ("sure", "How sure are we?", page_sure),
    ("alpha", "Risk and alpha", page_alpha),
    ("moves", "What moves them", page_moves),
    ("oos", "Out-of-sample test", page_oos),
    ("presets", "Portfolios", page_presets),
    ("about", "About the data", page_about),
]


# ---------------------------------------------------------------------------
# serialisation
# ---------------------------------------------------------------------------
def lit(value: str) -> dict:
    return {"expr": {"Literal": {"Value": value}}}


def text(value: str) -> dict:
    return lit("'" + value.replace("'", "''") + "'")


def number(value: float) -> dict:
    return lit(f"{value}D")


def flag(value: bool) -> dict:
    return lit("true" if value else "false")


def colour(hex_code: str) -> dict:
    return {"solid": {"color": text(hex_code)}}


def projection(field: Field, header: str | None = None) -> dict:
    entity, prop = field
    kind = "Measure" if entity == "_Measures" else "Column"
    out = {"field": {kind: {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}},
           "queryRef": f"{entity}.{prop}", "active": True}
    if header:
        out["displayName"] = header
    return out


def visual_objects(v: dict) -> dict:
    """Formatting of the visual itself (data labels, slicer header)."""
    objects: dict = {}
    if v["type"] == "card":
        objects["labels"] = [{"properties": {"fontSize": number(22), "color": colour(config.NAVY), "labelDisplayUnits": number(1)}}]
        objects["categoryLabels"] = [{"properties": {"show": flag(False)}}]
    elif v["type"] == "slicer":
        objects["header"] = [{"properties": {"show": flag(False)}}]
    elif v["type"] in ("clusteredBarChart", "clusteredColumnChart") and v["labels"]:
        objects["labels"] = [{"properties": {"show": flag(True), "fontSize": number(9)}}]
    elif v["type"] == "scatterChart" and v["labels"]:
        objects["categoryLabels"] = [{"properties": {"show": flag(True), "fontSize": number(8)}}]
    elif v["type"] == "tableEx":
        objects["values"] = [{"properties": {"fontSize": number(10), "wordWrap": flag(True)}}]
        objects["columnHeaders"] = [{"properties": {"fontSize": number(10), "bold": flag(True), "wordWrap": flag(True)}}]
        if v["widths"]:
            objects["columnWidth"] = [{"selector": {"metadata": f"{entity}.{prop}"}, "properties": {"value": number(px)}}
                                      for (entity, prop), px in v["widths"].items()]
    if "Series" in v["roles"] or len(v["roles"].get("Y", [])) > 1:
        objects["legend"] = [{"properties": {"show": flag(True), "showTitle": flag(False), "fontSize": number(9)}}]
    category_axis: dict = {}
    if v["type"] == "clusteredBarChart":
        category_axis["maxMarginFactor"] = number(45)         # percent of the chart's width the labels may take (the default 25 cut sector names)
    value_axis: dict = {}
    if v["log"]:
        value_axis["logAxisScale"] = flag(True)               # the property Power BI itself writes ("axisScale" is the old name and is dropped)
    if not v["axis_titles"]:
        category_axis["showAxisTitle"] = flag(False)
        value_axis["showAxisTitle"] = flag(False)
    if category_axis:
        objects["categoryAxis"] = [{"properties": category_axis}]
    if value_axis:
        objects["valueAxis"] = [{"properties": value_axis}]
    return objects


def container_objects(title: str) -> dict:
    """Formatting of the frame around a visual: title, white panel and a light border."""
    return {
        "title": [{"properties": {"show": flag(True), "text": text(title), "fontSize": number(11), "bold": flag(True),
                                  "fontColor": colour(MUTED), "alignment": text("left")}}],
        "background": [{"properties": {"show": flag(True), "color": colour(PANEL), "transparency": number(0)}}],
        "border": [{"properties": {"show": flag(True), "color": colour(BORDER), "radius": number(8)}}],
    }


def visual_json(page_id: str, index: int, v: dict) -> dict:
    headers = v["type"] == "tableEx"
    query: dict = {"queryState": {role: {"projections": [projection(f, HEADERS.get(f[1], f[1]) if headers else None) for f in fields]}
                                  for role, fields in v["roles"].items()}}
    if v["sort"]:
        first = next(iter(v["roles"]["Y"]))
        query["sortDefinition"] = {"sort": [{"field": projection(first)["field"], "direction": v["sort"]}], "isDefaultSort": True}
    visual = {"visualType": v["type"], "query": query}
    objects = visual_objects(v)
    if objects:
        visual["objects"] = objects
    visual["visualContainerObjects"] = container_objects(v["title"])
    visual["drillFilterOtherVisuals"] = True
    return {"$schema": VISUAL_SCHEMA, "name": f"{page_id}_{index:02d}",
            "position": {"x": v["x"], "y": v["y"], "z": index * 1000, "height": v["h"], "width": v["w"], "tabOrder": index * 1000},
            "visual": visual}


def page_json(page_id: str, display: str) -> dict:
    return {"$schema": PAGE_SCHEMA, "name": page_id, "displayName": display, "displayOption": "FitToPage",
            "height": PAGE_H, "width": PAGE_W,
            "objects": {"background": [{"properties": {"color": colour(PAGE_BACKGROUND), "transparency": number(0)}}]}}


def _dump(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_report(folder: Path, theme: dict) -> None:
    """Replace the report folder's definition with the current pages. Local settings (.pbi) are left alone."""
    for stale in ("definition", "StaticResources"):
        shutil.rmtree(folder / stale, ignore_errors=True)
    definition = folder / "definition"

    _dump(folder / "definition.pbir", {"version": "4.0", "datasetReference": {"byPath": {"path": f"../{PROJECT}.SemanticModel"}}})
    (folder / ".platform").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "Report", "displayName": PROJECT},
        "config": {"version": "2.0", "logicalId": tag("platform", "Report")},
    }, indent=2), encoding="utf-8")

    versions = {"visual": "2.14.0", "report": "3.4.0", "page": "2.3.1"}
    _dump(definition / "version.json", {"$schema": VERSION_SCHEMA, "version": "2.0.0"})
    _dump(definition / "report.json", {
        "$schema": REPORT_SCHEMA,
        "themeCollection": {"customTheme": {"name": THEME_FILE, "reportVersionAtImport": versions, "type": "RegisteredResources"}},
        "resourcePackages": [{"name": "RegisteredResources", "type": "RegisteredResources",
                              "items": [{"name": THEME_FILE, "path": THEME_FILE, "type": "CustomTheme"}]}],
        "settings": {"useStylableVisualContainerHeader": True, "exportDataMode": "AllowSummarized",
                     "defaultDrillFilterOtherVisuals": True, "allowChangeFilterTypes": True, "useEnhancedTooltips": False},
    })
    _dump(folder / "StaticResources" / "RegisteredResources" / THEME_FILE, theme)
    _dump(definition / "pages" / "pages.json", {"$schema": PAGES_SCHEMA, "pageOrder": [p[0] for p in PAGES], "activePageName": PAGES[0][0]})
    for page_id, display, builder in PAGES:
        _dump(definition / "pages" / page_id / "page.json", page_json(page_id, display))
        for i, v in enumerate(builder()):
            _dump(definition / "pages" / page_id / "visuals" / f"{page_id}_{i:02d}" / "visual.json", visual_json(page_id, i, v))
