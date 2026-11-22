"""The Power BI semantic model, written as TMDL files in the layout Power BI Desktop itself saves.

Each table is a Power Query partition whose rows are stored inside the model (compressed text, the way Power BI's
"Enter data" stores them), so the project opens from any folder with nothing else alongside it.

Lineage tags are left out, so Power BI treats the project as new and regenerating it gives identical files.
"""

from __future__ import annotations

import base64
import json
import re
import uuid
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

from .measures import DESCRIPTIONS, MEASURES, Measure, measure_lines

PROJECT = "PSX_Sector_Risk_Return"
CULTURE = "en-US"
COMPATIBILITY_LEVEL = 1606
NAMESPACE = uuid.UUID("0b5f7d1e-8a3c-4c62-9f1d-5d7e2a4b9c31")

# pandas dtype family -> (Power Query type, TMDL data type)
TYPES = {"int": ("Int64.Type", "int64"), "float": ("type number", "double"), "bool": ("type logical", "boolean"),
         "text": ("type text", "string"), "date": ("type date", "dateTime")}

# many-side column -> one-side column (a slicer on the one side filters the many side)
RELATIONSHIPS = [
    ("year_returns_to_sectors", "year_returns.sector", "sectors.sector"),
    ("rank_choices_to_sectors", "rank_choices.sector", "sectors.sector"),
    ("presets_to_preset_stats", "presets.preset", "preset_stats.preset"),
]

# A text column that should sort by another column instead of alphabetically (this also fixes the order of legend entries).
SORT_BY = {
    ("year_returns", "period"): "period_index", ("rank_choices", "choice"): "choice_order", ("rank_choices", "choice_short"): "choice_order",
    ("strategies", "strategy"): "strategy_order", ("strategy_levels", "strategy"): "strategy_order",
    ("strategy_levels", "strategy_short"): "strategy_order",
    ("components", "component"): "component_number", ("presets", "preset"): "preset_order",
    ("preset_stats", "preset"): "preset_order", ("preset_levels", "series"): "series_order",
    ("levels_top", "series"): "series_order", ("sensitivity", "setting"): "setting_order",
    ("robustness_summary", "choice"): "choice_order", ("sectors", "alpha_class"): "alpha_class_order",
}

FRACTION = "0.0%"
WHOLE_PCT = "0%"
TWO = "0.00"
THREE = "0.000"
WHOLE = "#,0"
MONTH = "mmm yyyy"

# Number formats of the columns that tables and axes show (Power BI shows a plain number otherwise).
FORMATS = {
    "sectors": {"n_companies": WHOLE, "cagr": FRACTION, "volatility": FRACTION, "max_drawdown": WHOLE_PCT, "sharpe": TWO, "sharpe_lo": TWO,
                "sharpe_hi": TWO, "p_top1": WHOLE_PCT, "p_top3": WHOLE_PCT, "p_beats_market": WHOLE_PCT, "dividend_points": FRACTION,
                "usd_cagr": FRACTION, "beta": TWO, "alpha": WHOLE_PCT, "alpha_t": "0.0", "alpha_p": THREE, "alpha_p_adjusted": THREE,
                "alpha_q": THREE, "dsr": TWO, "sortino": TWO, "cvar_95": FRACTION, "var_95": FRACTION, "up_capture": WHOLE_PCT,
                "down_capture": WHOLE_PCT, "longest_fall_months": "0", "rate_beta": TWO, "fx_beta": TWO, "component_1": TWO,
                "component_2": TWO, "rank_median": "0.0"},
    "market_years": {"period_return": WHOLE_PCT},
    "levels_top": {"date": MONTH, "level": "0"}, "levels": {"date": MONTH, "level": "0", "drawdown_pct": "0.0"},
    "year_returns": {"period_return": WHOLE_PCT}, "rank_choices": {"sharpe": TWO},
    "robustness_summary": {"rank_correlation": TWO},
    "strategies": {"cagr": FRACTION, "volatility": FRACTION, "max_drawdown": WHOLE_PCT, "sharpe": TWO, "sharpe_vs_equal": "+0.00;-0.00",
                   "vs_equal_lo": "+0.00;-0.00", "vs_equal_hi": "+0.00;-0.00", "vs_equal_p": THREE, "vs_equal_p_adjusted": THREE,
                   "turnover": WHOLE_PCT},
    "strategy_levels": {"date": MONTH, "level": "0"}, "info_coeff": {"decision_date": MONTH, "information_coefficient": "+0.00;-0.00"},
    "sensitivity": {"sharpe_rule": TWO, "sharpe_equal_weight": TWO, "difference": "+0.00;-0.00", "p": THREE,
                    "mean_information_coefficient": "+0.00;-0.00"},
    "presets": {"weight": FRACTION}, "preset_stats": {"cagr": FRACTION, "volatility": FRACTION, "max_drawdown": WHOLE_PCT, "sharpe": TWO},
    "preset_levels": {"date": MONTH, "level": "0"}, "components": {"share": FRACTION},
}

LINEAGE_TAGS = False


def tag(*parts: str) -> str:
    """A stable lineage tag for an object, from its path in the model."""
    return str(uuid.uuid5(NAMESPACE, "/".join(parts)))


def tag_line(indent: int, *parts: str) -> list[str]:
    """The lineageTag property line for an object (none when lineage tags are switched off)."""
    return [f"{chr(9) * indent}lineageTag: {tag(*parts)}"] if LINEAGE_TAGS else []


def name_token(name: str) -> str:
    """TMDL object names are quoted only when they are not plain identifiers."""
    return name if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) else f"'{name}'"


def kind(series: pd.Series) -> str:
    dtype = str(series.dtype)
    if dtype.startswith("datetime"):
        return "date"
    if dtype.startswith("int"):
        return "int"
    if dtype.startswith("float"):
        return "float"
    if dtype == "bool":
        return "bool"
    return "text"


def _cell(value) -> str | None:
    """A value as text, the way Power BI's inline tables hold it (it converts back with the column type)."""
    if value is None or value is pd.NaT or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, (bool, np.bool_)):
        return "true" if bool(value) else "false"
    if isinstance(value, float):
        return format(value, ".10g")
    return str(value)


def inline_payload(df: pd.DataFrame) -> str:
    """Rows as JSON text, raw-deflated and base64 encoded: what Table.FromRows(Json.Document(Binary.Decompress(...))) reads."""
    rows = [[_cell(v) for v in row] for row in df.itertuples(index=False, name=None)]
    raw = json.dumps(rows, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    packer = zlib.compressobj(level=9, wbits=-15)
    return base64.b64encode(packer.compress(raw) + packer.flush()).decode("ascii")


def partition_lines(table: str, df: pd.DataFrame) -> list[str]:
    kinds = {c: kind(df[c]) for c in df.columns}
    typed = ", ".join(f'{{"{c}", {TYPES[k][0]}}}' for c, k in kinds.items())
    columns = ", ".join(f"{c} = _t" for c in df.columns)
    return [
        f"\tpartition {table} = m", "\t\tmode: import", "\t\tsource =", "\t\t\t\tlet",
        f'\t\t\t\t\tSource = Table.FromRows(Json.Document(Binary.Decompress(Binary.FromText("{inline_payload(df)}", '
        f"BinaryEncoding.Base64), Compression.Deflate)), "
        f"let _t = ((type nullable text) meta [Serialized.Text = true]) in type table [{columns}]),",
        f'\t\t\t\t\tTyped = Table.TransformColumnTypes(Source, {{{typed}}}, "{CULTURE}")',
        "\t\t\t\tin", "\t\t\t\t\tTyped",
    ]


def table_tmdl(table: str, df: pd.DataFrame) -> str:
    formats = FORMATS.get(table, {})
    lines = [f"table {table}", *tag_line(1, table)]
    for column in df.columns:
        lines += ["", f"\tcolumn {column}", f"\t\tdataType: {TYPES[kind(df[column])][1]}"]
        if column in formats:
            lines.append(f"\t\tformatString: {formats[column]}")
        lines += [*tag_line(2, table, column), "\t\tsummarizeBy: none", f"\t\tsourceColumn: {column}"]
        if (table, column) in SORT_BY:
            lines.append(f"\t\tsortByColumn: {SORT_BY[(table, column)]}")
    lines += [""] + partition_lines(table, df)
    return "\n".join(lines) + "\n\n"


def measure_tmdl(m: Measure) -> str:
    """One measure. Continuation lines sit three tabs in and properties two tabs in."""
    body = measure_lines(m)
    out = []
    if m.name in DESCRIPTIONS:
        out.append(f"\t/// {DESCRIPTIONS[m.name]}")
    if len(body) == 1:
        out.append(f"\tmeasure {name_token(m.name)} = {body[0]}")
    else:
        out.append(f"\tmeasure {name_token(m.name)} =")
        out += ["\t\t\t" + ln for ln in body]
    if m.fmt:
        out.append(f"\t\tformatString: {m.fmt}")
    out += [f"\t\tdisplayFolder: {m.folder}", *tag_line(2, "_Measures", m.name)]
    return "\n".join(out)


def measures_tmdl() -> str:
    lines = ["table _Measures", *tag_line(1, "_Measures")]
    for m in MEASURES:
        lines += ["", measure_tmdl(m)]
    lines += ["", "\tcolumn Placeholder", "\t\tdataType: string", "\t\tisHidden",
              *tag_line(2, "_Measures", "Placeholder"), "\t\tsummarizeBy: none", "\t\tsourceColumn: Placeholder",
              "", "\tpartition _Measures = m", "\t\tmode: import", "\t\tsource =", "\t\t\t\tlet",
              '\t\t\t\t\tSource = #table(type table [Placeholder = text], {{"measures"}})', "\t\t\t\tin", "\t\t\t\t\tSource"]
    return "\n".join(lines) + "\n\n"


def platform(kind_name: str) -> str:
    return json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": kind_name, "displayName": PROJECT},
        "config": {"version": "2.0", "logicalId": tag("platform", kind_name)},
    }, indent=2)


def model_tmdl(table_names: list[str]) -> str:
    refs = "".join(f"ref table {name}\n" for name in [*table_names, "_Measures"])
    return (f"model Model\n\tculture: {CULTURE}\n\tdefaultPowerBIDataSourceVersion: powerBI_V3\n"
            f"\tdiscourageImplicitMeasures\n\tsourceQueryCulture: {CULTURE}\n\tdataAccessOptions\n"
            f"\t\tlegacyRedirects\n\t\treturnErrorValuesAsNull\n\n{refs}\n")


def write_model(folder: Path, tables: dict[str, pd.DataFrame]) -> None:
    definition = folder / "definition"
    tdir = definition / "tables"
    tdir.mkdir(parents=True, exist_ok=True)
    for stale in tdir.glob("*.tmdl"):
        stale.unlink()
    (folder / "definition.pbism").write_text(json.dumps({"version": "4.2", "settings": {}}, indent=2), encoding="utf-8")
    (folder / ".platform").write_text(platform("SemanticModel"), encoding="utf-8")
    (definition / "database.tmdl").write_text(f"database\n\tcompatibilityLevel: {COMPATIBILITY_LEVEL}\n\n", encoding="utf-8")
    (definition / "model.tmdl").write_text(model_tmdl(list(tables)), encoding="utf-8")
    (definition / "relationships.tmdl").write_text(
        "\n".join(f"relationship {name}\n\tfromColumn: {a}\n\ttoColumn: {b}\n" for name, a, b in RELATIONSHIPS) + "\n",
        encoding="utf-8")
    for name, df in tables.items():
        (tdir / f"{name}.tmdl").write_text(table_tmdl(name, df), encoding="utf-8")
    (tdir / "_Measures.tmdl").write_text(measures_tmdl(), encoding="utf-8")
