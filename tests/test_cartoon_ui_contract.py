"""Executable contract for the frozen CV cartoon design.

These tests intentionally check stable hooks and safety copy, not layout, element order,
whitespace, or pixels. They should survive visual refactors while failing if the scientific story
or accessible nonanimated path is removed.
"""

from __future__ import annotations

import html
import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML_PATH = ROOT / "demo" / "index.html"
JS_PATH = ROOT / "demo" / "app.js"


REAL_SCENE_IDS = (
    "real-lab-scene",
    "real-sample-shelf",
    "real-sample-base",
    "real-sample-glycine",
    "real-sample-lactic",
    "real-sample-record",
    "real-waste-tray",
    "real-rinse-tool",
    "real-cell",
    "real-cell-liquid",
    "real-cell-sample-tag",
    "real-electrode-we",
    "real-electrode-re",
    "real-electrode-ce",
    "real-lead-we",
    "real-lead-re",
    "real-lead-ce",
    "real-potentiostat",
    "real-potential-command",
    "real-current-signal",
    "real-sweep-waveform",
    "real-sweep-cursor",
    "real-scan-rate",
    "real-cycle-counter",
    "real-cv-display",
    "real-cv-path",
    "real-cv-cursor",
    "real-provenance-badge",
)

SYNTHETIC_SCENE_IDS = (
    "synthetic-scene",
    "synthetic-virtual-sample",
    "synthetic-response-plot",
    "synthetic-planner-fixed-grid",
    "synthetic-planner-information-gain",
    "synthetic-planner-random",
    "synthetic-validator",
    "synthetic-virtual-instrument",
    "synthetic-belief-bars",
    "synthetic-budget-status",
    "synthetic-post-run-reveal",
)

REAL_STEP_LABELS = (
    "1 · Select formulation",
    "2 · Check sample change",
    "3 · Remove and prepare",
    "4 · Load and identify",
    "5 · Assemble and check cell",
    "6 · Sweep potential and record current",
    "7 · Retain the published curve",
)

BRANCH_COPY = (
    "EMPTY / FRESH START",
    "No previous sample to remove",
    "SKIPPED — NO PREVIOUS SAMPLE",
    "SAME LOADED FORMULATION — CONDITION REPLAY",
    "Same formulation → keep sample loaded",
    "SKIPPED — SAME FORMULATION",
    "SKIPPED — ALREADY LOADED",
    "NEW FORMULATION — SAMPLE REPLACEMENT REQUIRED",
    "Different formulation → remove, prepare, and load before measurement",
    "Previous sample removed",
    "Cell/electrodes prepared — exact cleaning follows the laboratory protocol",
)

SYNTHETIC_STATE_LABELS = (
    "1 · SELECT RATE",
    "2 · VALIDATE REQUEST",
    "3 · EXECUTE VIRTUAL OPERATION",
    "4 · UPDATE BELIEFS",
    "5 · CONTINUE OR STOP",
)


def normalize(value: str) -> str:
    """Normalize only presentation whitespace and HTML entities."""

    return " ".join(html.unescape(value).split())


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []
        self.inputs: list[dict[str, str]] = []
        self.buttons: list[str] = []
        self.labels_for: dict[str, str] = {}
        self.outputs_for: dict[str, str] = {}
        self.live_regions: list[dict[str, str]] = []
        self._text: list[str] = []
        self._button_depth = 0
        self._button_text: list[str] = []
        self._label_for: str | None = None
        self._label_text: list[str] = []
        self._output_for: str | None = None
        self._output_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name: value or "" for name, value in attrs}
        if values.get("id"):
            self.ids.append(values["id"])
        if tag == "input":
            self.inputs.append(values)
        if values.get("aria-live"):
            self.live_regions.append(values)
        if tag == "button":
            self._button_depth += 1
            self._button_text = []
        elif tag == "label" and values.get("for"):
            self._label_for = values["for"]
            self._label_text = []
        elif tag == "output" and values.get("for"):
            self._output_for = values["for"]
            self._output_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "button" and self._button_depth:
            self.buttons.append(normalize(" ".join(self._button_text)))
            self._button_depth -= 1
            self._button_text = []
        elif tag == "label" and self._label_for:
            self.labels_for[self._label_for] = normalize(" ".join(self._label_text))
            self._label_for = None
            self._label_text = []
        elif tag == "output" and self._output_for:
            self.outputs_for[self._output_for] = normalize(" ".join(self._output_text))
            self._output_for = None
            self._output_text = []

    def handle_data(self, data: str) -> None:
        self._text.append(data)
        if self._button_depth:
            self._button_text.append(data)
        if self._label_for:
            self._label_text.append(data)
        if self._output_for:
            self._output_text.append(data)

    @property
    def visible_text(self) -> str:
        return normalize(" ".join(self._text))


def page() -> tuple[str, str, PageParser]:
    markup = HTML_PATH.read_text(encoding="utf-8")
    script = JS_PATH.read_text(encoding="utf-8")
    parser = PageParser()
    parser.feed(markup)
    return markup, script, parser


def assert_copy_in(corpus: str, expected: tuple[str, ...]) -> None:
    normalized = normalize(corpus)
    missing = [item for item in expected if normalize(item) not in normalized]
    assert not missing, f"missing frozen visible/state copy: {missing}"


def test_all_frozen_scene_ids_exist_exactly_once() -> None:
    _, _, parser = page()
    counts = Counter(parser.ids)
    required = (*REAL_SCENE_IDS, *SYNTHETIC_SCENE_IDS, "cartoon-status-live")
    missing = [stable_id for stable_id in required if counts[stable_id] == 0]
    duplicates = [stable_id for stable_id in required if counts[stable_id] > 1]
    assert not missing, f"missing stable cartoon IDs: {missing}"
    assert not duplicates, f"duplicate stable cartoon IDs: {duplicates}"
    assert all(count == 1 for count in counts.values()), "every document ID must be unique"


def test_static_html_preserves_visible_provenance_and_hard_boundary() -> None:
    _, _, parser = page()
    assert_copy_in(
        parser.visible_text,
        (
            "How a CV experiment becomes evidence",
            "◆ REAL — published, author-processed CV data",
            "◇ SYNTHETIC — saved policy replay, not a lab measurement",
            "PUBLISHED, AUTHOR-PROCESSED EXPERIMENTAL DATA",
            "Illustrated replay — no hardware connection",
            "PHYSICAL CONTEXT ENDS HERE",
            "Above: published, author-processed experimental curves from named formulations at 10 mV/s.",
            "Below: a separate synthetic response-scaling benchmark using one unnamed virtual sample.",
            "The published curves are context only. They do not fit, train, calibrate, validate, or supply observations to the synthetic benchmark.",
            "SYNTHETIC TEACHING EMULATOR · SAVED REPLAY · NOT A LAB MEASUREMENT",
        ),
    )


def test_real_workflow_has_exact_seven_steps_and_all_three_branch_messages() -> None:
    markup, script, _ = page()
    corpus = f"{markup}\n{script}"
    assert_copy_in(corpus, REAL_STEP_LABELS)
    assert_copy_in(corpus, BRANCH_COPY)
    for label in REAL_STEP_LABELS:
        assert normalize(corpus).count(normalize(label)) >= 1


def test_synthetic_loop_has_exact_five_states_and_unitless_output_copy() -> None:
    markup, script, _ = page()
    corpus = f"{markup}\n{script}"
    assert_copy_in(corpus, SYNTHETIC_STATE_LABELS)
    assert_copy_in(
        corpus,
        (
            "Normalized response vs scan rate — synthetic teaching model",
            "Unitless normalized response",
            "Planner belief within three predefined synthetic models",
            "One unnamed virtual sample for every scan-rate request",
            "One fixed synthetic scenario/run — not evidence of a universally best planner",
        ),
    )


def test_ranges_have_accessible_names_and_non_drag_alternatives() -> None:
    _, _, parser = page()
    ranges = [item for item in parser.inputs if item.get("type", "").lower() == "range"]
    names = {
        normalize(item.get("aria-label") or parser.labels_for.get(item.get("id", ""), ""))
        for item in ranges
    }
    assert "Replay position, 0 to 100 percent" in names
    assert any(name.startswith("Campaign event, 0 to") for name in names)
    assert all(
        item.get("aria-valuetext")
        or item.get("aria-describedby")
        or item.get("id") in parser.outputs_for
        for item in ranges
    )

    buttons = set(parser.buttons)
    assert {
        "Previous step",
        "Next step",
        "Reset lab",
        "Previous event",
        "Next event",
        "Reset synthetic replay",
    }.issubset(buttons)


def test_live_region_and_reduced_motion_javascript_hooks_are_present() -> None:
    _, script, parser = page()
    live_regions = [item for item in parser.live_regions if item.get("id") == "cartoon-status-live"]
    assert len(live_regions) == 1
    assert live_regions[0].get("aria-live") == "polite"
    assert live_regions[0].get("aria-atomic") == "true"

    assert re.search(r"matchMedia\s*\(\s*['\"]\(prefers-reduced-motion:\s*reduce\)['\"]", script)
    assert re.search(r"addEventListener\s*\(\s*['\"]change['\"]", script)
    assert "clearInterval" in script
    assert re.search(r"visibilitychange", script, re.IGNORECASE)


def test_exact_object_level_nonclaims_remain_visible_without_javascript() -> None:
    _, _, parser = page()
    assert_copy_in(
        parser.visible_text,
        (
            "Explanatory schematic — not to scale",
            "Published, author-processed experimental data",
            "The animation reveals saved published points; it does not generate measurements.",
            "The published curves are context only — not simulator input.",
            "Synthetic teaching emulator — saved replay, not a lab measurement",
            "Unitless normalized response — not experimental current density",
            "Synthetic truth, not experimental truth",
            "No LLM, no real instrument call, no laboratory control, and no institutional endorsement.",
        ),
    )


def test_controls_and_visible_claims_do_not_use_forbidden_language() -> None:
    _, _, parser = page()
    forbidden_control_labels = (
        "start instrument",
        "run potentiostat",
        "run experiment",
    )
    lower_buttons = [label.casefold() for label in parser.buttons]
    for forbidden in forbidden_control_labels:
        assert all(forbidden not in label for label in lower_buttons)

    visible = parser.visible_text.casefold()
    permitted_planner_nonclaim = normalize(
        "One fixed synthetic scenario/run — not evidence of a universally best planner"
    ).casefold()
    assert permitted_planner_nonclaim in visible
    visible_without_permitted_nonclaim = visible.replace(permitted_planner_nonclaim, "")

    for forbidden_claim in (
        "mechanism discovered",
        "autonomous laboratory",
        "identical physical state",
    ):
        assert forbidden_claim not in visible

    assert "universally best planner" not in visible_without_permitted_nonclaim
