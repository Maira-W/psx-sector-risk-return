"""Write the Power BI project: a semantic model and a report, as files Power BI Desktop opens.

    powerbi/PSX_Sector_Risk_Return.pbip                  open this in Power BI Desktop
    powerbi/PSX_Sector_Risk_Return.SemanticModel/        tables, relationships and DAX measures (TMDL)
    powerbi/PSX_Sector_Risk_Return.Report/               ten report pages (PBIR) and a colour theme
    powerbi/measures.dax                                 the measures as text

Everything is generated from data/processed, so the report always matches the dashboard and the documents.

A project holds no data cache, so Power BI Desktop shows a "Refresh now" banner the first time it opens one. The
PSX_Sector_Risk_Return.pbix beside it is a snapshot saved from the opened project (File > Save as), with the data
inside, for readers who just want to look at the report. Regenerating the project does not change that file.
"""

from __future__ import annotations

import json
from pathlib import Path

from .. import config
from .measures import MEASURES, measures_text
from .model import PROJECT, write_model
from .report import write_report
from .tables import make_tables

THEME = {
    "name": "PSX sector risk and return",
    "dataColors": [config.NAVY, config.TEAL, config.ORANGE, config.AMBER, config.GREY, config.PURPLE],
    "background": "#FFFFFF", "foreground": "#1D2733", "tableAccent": config.NAVY,
    "good": config.TEAL, "bad": config.ORANGE, "neutral": config.GREY,
    "textClasses": {
        "callout": {"fontSize": 24, "fontFace": "Segoe UI Semibold", "color": config.NAVY},
        "title": {"fontSize": 12, "fontFace": "Segoe UI Semibold", "color": config.NAVY},
        "header": {"fontSize": 11, "fontFace": "Segoe UI Semibold", "color": config.NAVY},
        "label": {"fontSize": 10, "fontFace": "Segoe UI", "color": "#4A5568"},
    },
    "visualStyles": {"*": {"*": {"*": [{"fontFamily": "Segoe UI"}]}}},
}


def build(folder: Path = config.POWERBI) -> None:
    tables = make_tables()
    folder.mkdir(parents=True, exist_ok=True)
    write_model(folder / f"{PROJECT}.SemanticModel", tables)
    write_report(folder / f"{PROJECT}.Report", THEME)
    (folder / f"{PROJECT}.pbip").write_text(json.dumps({
        "version": "1.0", "artifacts": [{"report": {"path": f"{PROJECT}.Report"}}],
        "settings": {"enableAutoRecovery": True},
    }, indent=2), encoding="utf-8")
    (folder / "measures.dax").write_text(measures_text(), encoding="utf-8")
    print(f"[powerbi] {len(tables)} tables, {len(MEASURES)} measures -> {folder / (PROJECT + '.pbip')}")
