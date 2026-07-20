from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = (
    ROOT / "README.md",
    ROOT / "docs" / "architecture.md",
    ROOT / "docs" / "benchmark-contract.md",
    ROOT / "docs" / "evidence-ledger.md",
    ROOT / "docs" / "evaluation.md",
    ROOT / "docs" / "limitations.md",
    ROOT / "docs" / "reproducibility.md",
    ROOT / "docs" / "demo-guide.md",
    ROOT / "docs" / "references.md",
)


def test_required_public_documentation_exists() -> None:
    missing = [str(path.relative_to(ROOT)) for path in DOCS if not path.is_file()]
    assert not missing


def test_public_boundary_language_is_present() -> None:
    corpus = "\n".join(path.read_text(encoding="utf-8") for path in DOCS)
    assert "SIMULATED RUN — NOT A LAB MEASUREMENT" in corpus
    assert "does not control" in corpus
    assert "No LLM" in corpus or "no LLM" in corpus
    assert "scientific-agent-lab" in corpus
    assert "post_run_reveal" in corpus
    assert "not a complete" in corpus.lower() or "not a validated" in corpus.lower()


def test_relative_markdown_links_resolve() -> None:
    link_pattern = re.compile(r"\[[^]]+\]\(([^)]+)\)")
    broken: list[str] = []
    for document in DOCS:
        for target in link_pattern.findall(document.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            clean_target = target.split("#", 1)[0]
            if not clean_target:
                continue
            if not (document.parent / clean_target).resolve().exists():
                broken.append(f"{document.relative_to(ROOT)} -> {target}")
    assert not broken


def test_demo_has_accessibility_and_trust_hooks() -> None:
    html = (ROOT / "demo" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "demo" / "styles.css").read_text(encoding="utf-8")
    assert 'class="skip-link"' in html
    assert 'aria-live="polite"' in html
    assert 'role="tablist"' in html
    assert 'role="tabpanel"' in html
    assert 'aria-labelledby="replay-tab-random"' in html
    assert 'id="truth-panel"' in html and 'tabindex="-1"' in html
    assert "SIMULATED RUN — NOT A LAB MEASUREMENT" in html
    assert "prefers-reduced-motion" in css
    assert ":focus-visible" in css
