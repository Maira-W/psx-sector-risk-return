"""The documents, dashboard and notebook are generated, so they can be tested like code."""

import json
import re

import pytest

from psxsec import config, dashboard, docs, notebook

DOCUMENTS = list(docs.OUTPUTS.values())


def text_of(path):
    return path.read_text(encoding="utf-8")


def test_committed_documents_are_what_the_templates_and_data_produce():
    for path, expected in docs.render_all().items():
        assert text_of(path) == expected, f"{path.name} is out of date: run `python -m psxsec report`"


def test_every_template_is_used_and_every_value_exists():
    assert {p.name for p in docs.TEMPLATE_DIR.glob("*.md")} == set(docs.OUTPUTS)
    values = docs.context()
    for template in docs.TEMPLATE_DIR.glob("*.md"):
        for name, _ in docs.PLACEHOLDER.findall(template.read_text(encoding="utf-8")):
            assert name in values, f"{template.name} uses {name}"


def test_a_missing_value_is_an_error_not_a_blank():
    with pytest.raises(KeyError):
        docs.render("{{no_such_value}}", {})
    assert docs.render("{{x:.1f}} points", {"x": 2.345}) == "2.3 points"


def test_no_leftover_placeholders_or_nan():
    for path in DOCUMENTS:
        text = text_of(path)
        assert "{{" not in text and "}}" not in text, path.name
        assert not re.search(r"\bnan\b|\bNaN\b|\binf\b", text), path.name


def test_relative_links_and_images_resolve():
    link = re.compile(r'(?:\]\(|src=")([^)"#\s]+)')
    for path in DOCUMENTS:
        for target in link.findall(text_of(path)):
            if re.match(r"[a-z]+:", target):
                continue
            assert (path.parent / target).exists(), f"{path.name} links to missing {target}"


def test_the_readme_headline_numbers_come_from_the_results(summary):
    readme = text_of(config.ROOT / "README.md")
    assert f"{summary['market']['cagr'] * 100:.1f}%" in readme
    assert summary["top_sharpe"][0]["sector"] in readme
    assert f"{summary['n_companies']} companies" in readme


def test_no_document_overstates_the_ranking(summary):
    """When no sector is a clear leader, every place that names the top sector must say the top group is a shortlist."""
    top = summary["top_sharpe"][0]
    if summary["max_p_top1"] < 0.6:
        for name in ("README.md", "docs/recommendation_memo.md"):
            text = text_of(config.ROOT / name).lower()
            assert "shortlist" in text and "not a winner" in text, name
    else:
        assert top["p_top1"] >= 0.6
    for path in DOCUMENTS:
        assert "guarantee" not in text_of(path).lower() or "no guarantee" in text_of(path).lower(), path.name


def test_every_document_says_it_is_not_investment_advice():
    for name in ("README.md", "docs/recommendation_memo.md", "docs/methodology.md"):
        assert "not investment advice" in text_of(config.ROOT / name).lower(), name


def test_raw_prices_are_not_in_the_repository():
    gitignore = text_of(config.ROOT / ".gitignore")
    assert "data/raw/*" in gitignore and "!data/raw/MANIFEST.json" in gitignore
    assert not list(config.RAW.glob("**/*.csv.gz")) or "data/raw/*" in gitignore


def test_dashboard_is_current_and_its_data_are_valid_json():
    page = text_of(config.DASHBOARD / "dashboard.html")
    assert page == dashboard.render()
    data = json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', page, re.S).group(1))
    assert {"sectors", "stocks", "weeks", "levels", "drawdowns", "robust", "corr", "stats"} <= set(data)
    assert "NaN" not in page and "__DATA__" not in page and "__PLOTLY__" not in page
    assert all(len(v) == len(data["weeks"]) for v in data["levels"].values())
    assert {r["sector"] for r in data["sectors"]} >= set(data["rankedOrder"])


def test_figures_exist_and_are_not_empty():
    names = re.findall(r"docs/figures/([\w.]+\.png)", text_of(config.ROOT / "README.md"))
    assert names
    for name in names:
        assert (config.FIGURES / name).stat().st_size > 10_000
    assert len(list(config.FIGURES.glob("*.png"))) == 9


def test_the_notebook_has_the_code_in_notebook_py_and_ran_without_errors():
    saved = json.loads(text_of(notebook.PATH))
    expected = notebook.cells()
    assert [c["cell_type"] for c in saved["cells"]] == [kind for kind, _ in expected]
    for cell, (kind, source) in zip(saved["cells"], expected, strict=True):
        assert "".join(cell["source"]) == source, "the notebook is out of date: run `python -m psxsec notebook`"
        if kind == "code":
            assert cell["execution_count"] is not None, "a code cell was never run"
            assert not [o for o in cell["outputs"] if o.get("output_type") == "error"], "a code cell failed"
