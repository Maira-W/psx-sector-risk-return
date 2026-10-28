"""The documents, dashboard and notebook are generated, so they can be tested like code."""

import json
import re

import numpy as np
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


def test_the_second_layer_text_matches_the_results(summary):
    """The wording about skill, luck and the walk-forward test must follow the numbers; nothing may claim a finding they do not show."""
    a, m, w = summary["alpha"], summary["macro"], summary["walk_forward"]
    n, win, eq = a["trials"], w["strategies"]["winners"], w["strategies"]["equal_weight"]
    readme, memo = text_of(config.ROOT / "README.md"), text_of(config.ROOT / "docs/recommendation_memo.md")
    for text in (readme, memo):
        assert f"{a['best_alpha_p_adjusted']:.3f}" in text and f"{win['sharpe']:.2f}" in text and f"{eq['sharpe']:.2f}" in text
        assert f"{len(m['rate_fdr'])} of the {n} sectors react clearly to interest rates" in text
        assert f"{summary['structure']['effective_bets']:.1f} independent bets" in text
    for name in ("README.md", "docs/recommendation_memo.md", "docs/methodology.md"):
        text = text_of(config.ROOT / name)
        if a["alpha_adjusted_significant"] == 0:
            assert "keep a significant alpha" not in text, name
        if win["sharpe_vs_equal"] <= 0 or win["vs_equal_p"] >= 0.05:
            assert "The past ranking beat equal weighting out of sample." not in text, name       # that sentence is only for a gain that is more than luck
    table = [line for line in memo.split("## Is it skill or luck?")[1].split("## What moves")[0].splitlines() if line.startswith("| ") and not line.startswith("| ---")]
    assert len(table) == n + 1                                                       # a header and one row for every ranked sector
    rows = [line for line in memo.split("## Could you have used the ranking?")[1].splitlines() if line.startswith("| ") and "Rule" not in line and "---" not in line]
    assert any(config.STRATEGIES["winners"] in row for row in rows) and any(config.STRATEGIES["min_variance"] in row for row in rows)


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
    assert {"sectors", "stocks", "weeks", "levels", "drawdowns", "robust", "corr", "stats", "daily", "presets", "walkForward", "structure"} <= set(data)
    assert "NaN" not in page and "__DATA__" not in page and "__PLOTLY__" not in page
    assert all(len(v) == len(data["weeks"]) for v in data["levels"].values())
    assert {r["sector"] for r in data["sectors"]} >= set(data["rankedOrder"])


def test_the_dashboard_carries_what_the_second_layer_needs(summary, daily):
    data = dashboard.payload()
    ranked, days = data["rankedOrder"], data["daily"]
    assert days["scale"] == dashboard.DAILY_SCALE and len(days["dates"]) == len(daily) and len(days["safe"]) == len(daily)
    assert set(days["returns"]) == {*ranked, dashboard.MARKET} and all(len(v) == len(daily) for v in days["returns"].values())
    for name in (ranked[0], dashboard.MARKET):                                  # the builder works from these numbers, so they must be the results rounded, not changed
        assert np.allclose(np.array(days["returns"][name]) / days["scale"], daily[name], atol=0.6 / days["scale"])
    assert np.allclose(days["safe"], daily[dashboard.CASH], atol=1e-8)
    for name, weights in data["presets"].items():
        assert len(weights) == len(ranked) and min(weights) >= 0 and abs(sum(weights) - 1) < 1e-6, name
    walk = data["walkForward"]
    assert set(walk["levels"]) == set(walk["names"]) == set(config.STRATEGIES)
    assert all(len(v) == len(walk["weeks"]) for v in walk["levels"].values())
    assert len(walk["ic"]) == len(walk["icDates"]) == summary["walk_forward"]["ic"]["months"]
    names, matrix = data["structure"]["names"], np.array(data["structure"]["matrix"])
    assert sorted(names) == sorted(ranked) and matrix.shape == (len(names), len(names)) and np.allclose(matrix, matrix.T, atol=1e-3)
    assert [name for group in summary["structure"]["groups"] for name in group] == names       # the heatmap draws each group as a block of rows


def test_the_dashboard_has_a_tab_for_every_section_and_no_leftover_hooks():
    page = text_of(config.DASHBOARD / "dashboard.html")
    tabs = re.findall(r'\["(\w+)", "([^"]+)"\]', re.search(r"const tabs = (\[.*?\]);", page, re.S).group(1))
    ids = [i for i, _ in tabs]
    assert ids == ["answer", "table", "ups", "sure", "risk", "moves", "port", "method"]
    assert all(f'<section id="{i}" hidden></section>' in page or i == "answer" for i in ids) and 'id="answer"' in page
    assert "console.log" not in page and "debugger" not in page


def test_figures_exist_and_are_not_empty():
    names = re.findall(r"docs/figures/([\w.]+\.png)", text_of(config.ROOT / "README.md"))
    assert names
    for name in names:
        assert (config.FIGURES / name).stat().st_size > 10_000
    assert len(list(config.FIGURES.glob("*.png"))) == 13
    mentioned = set(re.findall(r"figures/([\w.]+\.png)", "".join(text_of(path) for path in DOCUMENTS)))
    assert {p.name for p in config.FIGURES.glob("*.png")} <= mentioned, "a figure is not used in any document"


def test_the_notebook_has_the_code_in_notebook_py_and_ran_without_errors():
    saved = json.loads(text_of(notebook.PATH))
    expected = notebook.cells()
    assert [c["cell_type"] for c in saved["cells"]] == [kind for kind, _ in expected]
    for cell, (kind, source) in zip(saved["cells"], expected, strict=True):
        assert "".join(cell["source"]) == source, "the notebook is out of date: run `python -m psxsec notebook`"
        if kind == "code":
            assert cell["execution_count"] is not None, "a code cell was never run"
            assert not [o for o in cell["outputs"] if o.get("output_type") == "error"], "a code cell failed"
