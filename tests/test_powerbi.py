"""The Power BI project is generated, so its internal consistency can be tested without opening Power BI."""

import base64
import itertools
import json
import re
import zipfile
import zlib

import pytest

from psxsec import config, powerbi
from psxsec.powerbi import measures, model, report, tables

PBIX = config.POWERBI / f"{model.PROJECT}.pbix"
RECORD = config.POWERBI / "measure_values.json"           # what Power BI Desktop returned for every measure, saved when the .pbix was
LOCAL_ONLY = {".pbi", "diagramLayout.json", ".pbix"}      # files Power BI writes on a machine, or snapshots


@pytest.fixture(scope="module")
def model_tables():
    return tables.make_tables()


def normalised(text: str) -> str:
    """Replace each compressed data block by the rows it holds, so the comparison does not depend on how zlib packs bytes."""
    def unpack(match: re.Match) -> str:
        return 'Binary.FromText("' + zlib.decompress(base64.b64decode(match.group(1)), -15).decode() + '"'

    return re.sub(r'Binary\.FromText\("([A-Za-z0-9+/=]+)"', unpack, text)


# --------------------------------------------------------------------------- measures
def test_measure_names_are_unique_and_safe_to_quote():
    names = [m.name for m in measures.MEASURES]
    assert len(names) == len(set(names))
    assert not any(ch in n for n in names for ch in "'[]")


def test_measure_formats_and_folders_are_filled_in():
    for m in measures.MEASURES:
        assert m.folder and m.fmt, m.name
        assert measures.measure_lines(m), m.name


def test_every_column_a_measure_reads_exists(model_tables):
    pattern = re.compile(r"'?\b([A-Za-z_][A-Za-z0-9_]*)'?\[([A-Za-z0-9_]+)\]")
    for m in measures.MEASURES:
        for table, column in pattern.findall(m.dax):
            assert table in model_tables, (m.name, table)
            assert column in model_tables[table].columns, (m.name, f"{table}[{column}]")


def test_a_table_name_power_bi_reads_as_a_keyword_is_always_quoted():
    """Power BI rejects the bare word: "The syntax for 'levels' is incorrect" (found by evaluating every measure in Desktop)."""
    for m in measures.MEASURES:
        assert not re.search(r"(?<!')\blevels\[", m.dax), m.name


def test_a_count_that_can_be_zero_is_never_blank():
    """CALCULATE over no rows is blank, and a card shows "(Blank)" for it, so a count is wrapped in COALESCE."""
    for m in measures.MEASURES:
        if "COUNTROWS" in m.dax and "CALCULATE" in m.dax and "DIVIDE" not in m.dax:
            assert m.dax.startswith("COALESCE ("), m.name


def test_every_measure_a_measure_calls_exists():
    names = {m.name for m in measures.MEASURES}
    for m in measures.MEASURES:
        for called in re.findall(r"(?<![A-Za-z0-9_'])\[([^\]]+)\]", m.dax):
            assert called in names, (m.name, called)


def test_no_measure_filters_a_column_by_a_measure():
    """A column compared with a measure inside CALCULATE made measures invalid in Power BI; values are held in a VAR."""
    names = {m.name for m in measures.MEASURES}
    for m in measures.MEASURES:
        for called in re.findall(r"\w+\[\w+\]\s*=\s*\[([^\]]+)\]", m.dax):
            assert called not in names, (m.name, called)


def test_descriptions_belong_to_real_measures():
    assert set(measures.DESCRIPTIONS) <= {m.name for m in measures.MEASURES}


def test_measures_dax_lists_every_measure():
    text = measures.measures_text()
    for m in measures.MEASURES:
        assert f"\n{m.name} =" in text, m.name


def test_text_valued_measures_use_selectedvalue_not_max():
    """MAX of a text column is not valid DAX; a one-row table's text is read with SELECTEDVALUE."""
    for m in measures.MEASURES:
        if m.fmt == measures.TEXT:
            assert m.dax.strip().startswith("SELECTEDVALUE"), m.name


# --------------------------------------------------------------------------- model
def test_relationships_join_existing_columns_and_a_unique_key(model_tables):
    for name, many, one in model.RELATIONSHIPS:
        (t1, c1), (t2, c2) = many.split("."), one.split(".")
        assert c1 in model_tables[t1].columns and c2 in model_tables[t2].columns, name
        assert model_tables[t2][c2].is_unique, name
        assert set(model_tables[t1][c1]) <= set(model_tables[t2][c2]), name       # no row without a parent


def test_sort_by_columns_exist_and_follow_their_column(model_tables):
    for (table, column), by in model.SORT_BY.items():
        frame = model_tables[table]
        assert column in frame.columns and by in frame.columns, (table, column)
        assert frame.groupby(column)[by].nunique().max() == 1, (table, column)      # each label has one place in the order


def test_every_table_has_a_note_for_the_documents(model_tables):
    assert list(tables.TABLE_NOTES) == list(model_tables)


def test_column_formats_name_real_columns(model_tables):
    for table, formats in model.FORMATS.items():
        assert set(formats) <= set(model_tables[table].columns), table


def test_table_and_column_names_are_plain_identifiers(model_tables):
    reserved = {"key", "group", "rank", "return", "table", "column", "measure", "partition", "model", "date"}
    for name, df in model_tables.items():
        assert re.fullmatch(r"[a-z_]+", name), name
        for column in df.columns:
            assert re.fullmatch(r"[a-z_0-9]+", column), (name, column)
            assert column not in reserved - {"date"}, (name, column)


def test_inline_table_data_round_trips(model_tables):
    for name, df in model_tables.items():
        rows = json.loads(zlib.decompress(base64.b64decode(model.inline_payload(df)), -15))
        assert len(rows) == len(df) and all(len(row) == len(df.columns) for row in rows), name


def test_dates_travel_as_plain_dates(model_tables):
    for name in ("levels", "levels_top", "strategy_levels", "info_coeff", "preset_levels"):
        frame = model_tables[name]
        column = "decision_date" if name == "info_coeff" else "date"
        assert model.kind(frame[column]) == "date", name
        rows = json.loads(zlib.decompress(base64.b64decode(model.inline_payload(frame[[column]])), -15))
        assert all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", row[0]) for row in rows), name


def test_every_column_has_a_power_query_type(model_tables):
    for df in model_tables.values():
        for column in df.columns:
            assert model.kind(df[column]) in model.TYPES


# --------------------------------------------------------------------------- what Power BI Desktop computed
SIMPLE = re.compile(r"^(AVERAGE|MAX|MIN|SUM)\s*\(\s*(\w+)\[(\w+)\]\s*\)$")
SINGLE = re.compile(r"^SELECTEDVALUE\s*\(\s*(\w+)\[(\w+)\]\s*\)$")
COUNT = re.compile(r"^COUNTROWS\s*\(\s*(\w+)\s*\)$")
COUNT_IF = re.compile(r"^COALESCE \( CALCULATE \( COUNTROWS \( (\w+) \), (\w+)\[(\w+)\] (>=|<=|<|>) ([0-9.]+) \), 0 \)$")
PICKED = re.compile(r'^CALCULATE \( AVERAGE \( (\w+)\[(\w+)\] \), (\w+)\[(\w+)\] = "(\w+)" \)$')
OPERATORS = {">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b, "<": lambda a, b: a < b, ">": lambda a, b: a > b}
BLANK = object()


def python_value(m, t):
    """What a measure must return when no slicer is set, worked out from the tables with pandas."""
    explicit = {
        "Market Excess Return a Year": lambda: t["market"]["market_cagr"].iloc[0] - t["market"]["cash_cagr"].iloc[0],
        "Market Year Return": lambda: t["market_years"]["period_return"].mean(),
        "Months Pointing the Right Way": lambda: (t["info_coeff"]["information_coefficient"] > 0).mean(),
        "Selected Level": lambda: BLANK, "Selected Drawdown": lambda: BLANK,       # more than eight series are in view, so nothing is drawn
    }
    if m.name in explicit:
        return explicit[m.name]()
    dax = " ".join(measures.measure_lines(m))
    if match := SIMPLE.match(dax):
        function, table, column = match.groups()
        return getattr(t[table][column], {"AVERAGE": "mean", "MAX": "max", "MIN": "min", "SUM": "sum"}[function])()
    if match := SINGLE.match(dax):
        values = t[match.group(1)][match.group(2)].unique()
        assert len(values) == 1, m.name
        return values[0]
    if match := COUNT.match(dax):
        return len(t[match.group(1)])
    if match := COUNT_IF.match(dax):
        table, same_table, column, op, bound = match.groups()
        assert table == same_table
        return int(OPERATORS[op](t[table][column], float(bound)).sum())
    if match := PICKED.match(dax):
        table, column, key_table, key_column, key = match.groups()
        return t[table].loc[t[key_table][key_column] == key, column].mean()
    raise AssertionError(f"no Python value is defined for the measure {m.name!r}: add one to python_value")


def test_power_bi_desktop_evaluated_every_measure_and_the_values_equal_python(model_tables):
    """The record is what Desktop returned for each measure when the .pbix was saved. It fails if a measure was added or changed
    without evaluating it again, and it proves the DAX gives the numbers the Python results give."""
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    names = {m.name for m in measures.MEASURES}
    assert set(record["measures"]) == names
    assert not [k for k, v in record["measures"].items() if isinstance(v, str) and v.startswith("ERROR")]
    for m in measures.MEASURES:
        want, got = python_value(m, model_tables), record["measures"][m.name]
        if want is BLANK:
            assert got is None, m.name
        elif isinstance(want, str):
            assert got == want, m.name
        else:
            assert got == pytest.approx(float(want), rel=1e-9, abs=1e-9), (m.name, got, want)
    counts = {name: len(df) for name, df in model_tables.items()}
    assert {k: v for k, v in record["tables"].items() if k in counts} == counts
    assert record["tables"]["_Measures"] == 1


# --------------------------------------------------------------------------- the numbers the report shows
def test_tables_have_the_row_counts_the_report_relies_on(model_tables, summary):
    n = summary["n_sectors_ranked"]
    assert len(model_tables["sectors"]) == n and len(model_tables["market"]) == 1 and len(model_tables["market_years"]) == 5
    assert len(model_tables["year_returns"]) == 5 * n and len(model_tables["strategies"]) == len(config.STRATEGIES)
    assert len(model_tables["rank_choices"]) == n * (1 + summary["robustness"]["n_choices"])
    assert len(model_tables["levels"]) == (n + 2) * model_tables["levels"]["date"].nunique()          # every sector, the market and cash
    assert model_tables["levels_top"]["series"].nunique() == 5 and model_tables["preset_levels"]["series"].nunique() == 5
    assert len(model_tables["info_coeff"]) == summary["walk_forward"]["ic"]["months"]
    assert len(model_tables["components"]) == 8 and len(model_tables["groups"]) == config.CLUSTERS


def test_sector_table_is_ranked_by_sharpe_and_matches_the_results(model_tables, sectors):
    t = model_tables["sectors"]
    assert t["sharpe"].is_monotonic_decreasing and list(t["rank_sharpe"]) == list(range(1, len(t) + 1))
    ranked = sectors[sectors["ranked"]].set_index("sector")
    for column in ("cagr", "volatility", "max_drawdown", "sharpe", "beta", "alpha", "alpha_p_adjusted", "p_top1"):
        assert t.set_index("sector")[column].to_numpy() == pytest.approx(ranked.loc[t["sector"], column].to_numpy(), abs=1e-6)
    assert set(t["alpha_class"]) <= set(tables.CLASSES) and t["group_letter"].isin(list(config.GROUP_LETTERS)).all()


def test_market_table_matches_the_summary(model_tables, summary):
    m = model_tables["market"].iloc[0]
    assert m["market_cagr"] == pytest.approx(summary["market"]["cagr"], abs=1e-6) and m["cash_cagr"] == pytest.approx(summary["safe"]["cagr"], abs=1e-6)
    assert m["top_sector"] == summary["top_sharpe"][0]["sector"] and m["n_companies"] == summary["n_companies"]
    assert m["n_rate_fdr"] == len(summary["macro"]["rate_fdr"]) and m["n_fx_fdr"] == len(summary["macro"]["fx_fdr"])
    assert m["best_alpha_p_adjusted"] == pytest.approx(summary["alpha"]["best_alpha_p_adjusted"], abs=1e-6)


def test_weekly_levels_end_where_the_daily_returns_end(model_tables, daily, summary):
    levels = model_tables["levels"]
    last = levels[levels["date"] == levels["date"].max()].set_index("series")["level"]
    name = summary["top_sharpe"][0]["sector"]
    assert last[name] == pytest.approx(100 * (1 + daily[name]).prod(), abs=0.06)
    assert last["Whole market"] == pytest.approx(100 * (1 + daily["Whole market"]).prod(), abs=0.06)
    assert levels["drawdown_pct"].max() <= 0 and levels["drawdown_pct"].min() > -100


def test_strategy_and_information_coefficient_tables_match_the_summary(model_tables, summary):
    s = model_tables["strategies"].set_index("strategy_key")
    wf = summary["walk_forward"]
    for key, row in wf["strategies"].items():
        assert s.loc[key, "sharpe"] == pytest.approx(row["sharpe"], abs=1e-4)             # the results file keeps six significant digits
        if row["vs_equal_p"] is not None:
            assert s.loc[key, "vs_equal_p_adjusted"] == pytest.approx(row["vs_equal_p_adjusted"], abs=1e-4)
    assert model_tables["info_coeff"]["information_coefficient"].mean() == pytest.approx(wf["ic"]["mean"], abs=2e-3)
    assert (model_tables["info_coeff"]["information_coefficient"] > 0).mean() == pytest.approx(wf["ic"]["share_positive"], abs=1e-9)


def test_preset_tables_are_valid_portfolios(model_tables):
    weights = model_tables["presets"].groupby("preset")["weight"].sum()
    assert (weights > 0.999).all() and (weights < 1.0 + 1e-6).all()          # a holding below 0.05% is left out, so the sum is a hair under one
    stats = model_tables["preset_stats"].set_index("preset")
    assert stats["sectors_held"].to_dict() == model_tables["presets"].groupby("preset")["sector"].nunique().to_dict()
    assert (stats["max_drawdown"] < 0).all() and (stats["volatility"] > 0).all()
    steady, equal = stats.loc["Minimum variance"], stats.loc["Equal weight"]
    assert steady["volatility"] < equal["volatility"]                       # the steadiest mix is the least volatile of the two


def test_rank_choices_rank_only_sectors_in_the_analysis(model_tables):
    t = model_tables["rank_choices"]
    assert t["position"].isna().equals(t["sharpe"].isna())
    main = t[t["choice"] == "Main result"].set_index("sector")["position"]
    assert sorted(main) == list(range(1, len(main) + 1))
    assert set(t["kind"]) == {"Main result", "Method", "Dates"}


# --------------------------------------------------------------------------- report
def test_every_field_a_visual_uses_exists(model_tables):
    names = {m.name for m in measures.MEASURES}
    for page_id, _, builder in report.PAGES:
        for visual in builder():
            for fields in visual["roles"].values():
                for entity, prop in fields:
                    if entity == "_Measures":
                        assert prop in names, (page_id, prop)
                    else:
                        assert prop in model_tables[entity].columns, (page_id, entity, prop)


def test_visuals_stay_on_the_page_and_do_not_overlap():
    for page_id, _, builder in report.PAGES:
        boxes = [(v["x"], v["y"], v["x"] + v["w"], v["y"] + v["h"]) for v in builder()]
        for x0, y0, x1, y1 in boxes:
            assert 0 <= x0 < x1 <= report.PAGE_W and 0 <= y0 < y1 <= report.PAGE_H, page_id
        for a, b in itertools.combinations(boxes, 2):
            overlap = min(a[2], b[2]) - max(a[0], b[0]) > 0 and min(a[3], b[3]) - max(a[1], b[1]) > 0
            assert not overlap, (page_id, a, b)


def test_every_page_has_a_note_and_a_title():
    assert [p[0] for p in report.PAGES] == list(report.PAGE_NOTES)
    for page_id, display, builder in report.PAGES:
        assert report.PAGE_NOTES[page_id] and display and builder()


def test_titles_are_short_enough_to_show():
    """Power BI cuts a title that is wider than its visual and adds "...". The limit is what fitted when the pages were checked in
    Desktop: about 7.1 pixels a character in the bold 11 pt title, less a margin of 20 pixels and one character."""
    for page_id, _, builder in report.PAGES:
        for v in builder():
            if v["type"] != "slicer" or v["w"] < 400:
                limit = int((v["w"] - 20) / 7.1) - 1
                assert len(v["title"]) <= limit, (page_id, v["title"], len(v["title"]), limit)


def test_table_columns_have_a_header():
    for page_id, _, builder in report.PAGES:
        for v in builder():
            if v["type"] == "tableEx":
                for _, prop in v["roles"]["Values"]:
                    assert prop in report.HEADERS, (page_id, prop)


def test_sorted_charts_sort_by_a_measure():
    for page_id, _, builder in report.PAGES:
        for v in builder():
            if v["sort"]:
                assert v["roles"]["Y"][0][0] == "_Measures", (page_id, v["title"])


def test_a_log_axis_is_written_as_power_bi_writes_it():
    """Desktop drops the old "axisScale" text property when it saves; the property it keeps is the boolean logAxisScale."""
    seen = 0
    for page_id, _, builder in report.PAGES:
        for index, v in enumerate(builder()):
            axis = report.visual_json(page_id, index, v)["visual"].get("objects", {}).get("valueAxis", [{}])[0].get("properties", {})
            assert "axisScale" not in axis
            if v["log"]:
                seen += 1
                assert axis["logAxisScale"] == report.flag(True)
    assert seen >= 4


def test_a_log_axis_is_only_asked_of_a_line_chart():
    for page_id, _, builder in report.PAGES:
        for v in builder():
            assert not v["log"] or v["type"] == "lineChart", (page_id, v["title"])


# --------------------------------------------------------------------------- the files on disk
def test_committed_project_is_what_the_generator_writes(tmp_path):
    powerbi.build(folder=tmp_path)
    generated = {p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_file()}
    committed = {p.relative_to(config.POWERBI) for p in config.POWERBI.rglob("*")
                 if p.is_file() and not LOCAL_ONLY & set(p.relative_to(config.POWERBI).parts) and p.suffix != ".pbix" and p != RECORD}
    assert generated == committed
    for relative in sorted(generated):
        fresh = normalised((tmp_path / relative).read_text(encoding="utf-8"))
        assert fresh == normalised((config.POWERBI / relative).read_text(encoding="utf-8")), relative


def test_no_lineage_tags_so_power_bi_loads_the_project_as_new():
    assert not model.LINEAGE_TAGS
    assert "lineageTag" not in (config.POWERBI / f"{model.PROJECT}.SemanticModel" / "definition" / "model.tmdl").read_text()


def test_pbix_snapshot_is_a_real_package_and_matches_the_report():
    """The .pbix is saved from Power BI Desktop by hand; this fails if the report was regenerated and the snapshot not."""
    assert zipfile.is_zipfile(PBIX)
    z = zipfile.ZipFile(PBIX)
    names = set(z.namelist())
    assert {"Version", "DataModel", "Report/definition/report.json", "Report/definition/pages/pages.json"} <= names
    assert z.getinfo("DataModel").file_size > 50_000
    pages = json.loads(z.read("Report/definition/pages/pages.json"))
    assert pages["pageOrder"] == [p[0] for p in report.PAGES]

    for page_id, _, builder in report.PAGES:
        for index, visual in enumerate(builder()):
            path = f"Report/definition/pages/{page_id}/visuals/{page_id}_{index:02d}/visual.json"
            assert path in names, path
            saved = json.loads(z.read(path))
            wanted = report.visual_json(page_id, index, visual)
            assert saved["visual"]["visualType"] == wanted["visual"]["visualType"], path
            assert saved["visual"]["query"] == wanted["visual"]["query"], path
            assert saved["position"] == wanted["position"], path
            title = saved["visual"]["visualContainerObjects"]["title"][0]["properties"]["text"]
            assert title == wanted["visual"]["visualContainerObjects"]["title"][0]["properties"]["text"], path


def test_theme_is_registered_and_present():
    folder = config.POWERBI / f"{model.PROJECT}.Report"
    theme = json.loads((folder / "StaticResources" / "RegisteredResources" / report.THEME_FILE).read_text(encoding="utf-8"))
    assert theme["dataColors"] == powerbi.THEME["dataColors"]
    definition = json.loads((folder / "definition" / "report.json").read_text(encoding="utf-8"))
    assert definition["themeCollection"]["customTheme"]["name"] == report.THEME_FILE
