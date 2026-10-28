"""Draw the figures, build the dashboard and write the documents."""

from __future__ import annotations


def run() -> None:
    from . import charts, dashboard, docs
    charts.make_all()
    dashboard.build()
    docs.build()
    print("[report] figures, dashboard and documents written")
