"""Draw the figures, build the dashboard and the Power BI project, and write the documents."""

from __future__ import annotations


def run() -> None:
    from . import charts, dashboard, docs, powerbi
    charts.make_all()
    dashboard.build()
    powerbi.build()
    docs.build()
    print("[report] figures, dashboard, Power BI project and documents written")
