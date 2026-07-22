"""Stable public UI contract for the approved restricted-v1 diagnosis loop."""

from __future__ import annotations

import re
import shutil
import subprocess
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "demo" / "index.html"
JS = ROOT / "demo" / "app.js"
CSS = ROOT / "demo" / "styles.css"
RECONCILIATION_TEST = ROOT / "tests" / "js" / "test_diagnosis_reconciliation.mjs"


class Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []
        self.links: list[str] = []
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if values.get("id"):
            self.ids.append(values["id"])
        if tag == "a" and values.get("href"):
            self.links.append(values["href"])

    def handle_data(self, data: str) -> None:
        self.text.append(data)


@pytest.fixture(scope="module")
def sources() -> tuple[str, str, str, Parser]:
    markup = HTML.read_text(encoding="utf-8")
    script = JS.read_text(encoding="utf-8")
    styles = CSS.read_text(encoding="utf-8")
    parser = Parser()
    parser.feed(markup)
    return markup, script, styles, parser


def test_diagnosis_is_first_and_prior_experiences_remain_secondary(sources) -> None:
    markup, _, _, _ = sources
    assert markup.index('id="diagnosis-workbench"') < markup.index('id="real-workbench"')
    assert markup.index('id="real-workbench"') < markup.index('id="synthetic-benchmark"')
    assert "supporting context and prior benchmark" in markup
    assert "How a CV experiment becomes evidence" in markup
    assert "Three planners, one committed synthetic scenario" in markup


def test_required_hooks_are_unique_and_conductivity_is_separate(sources) -> None:
    _, _, _, parser = sources
    required = {
        "diagnosis-workbench",
        "diagnosis-status",
        "diagnosis-error",
        "diagnosis-question",
        "diagnosis-measurement-budget",
        "diagnosis-attempt-budget",
        "diagnosis-beliefs",
        "diagnosis-recommendation",
        "diagnosis-reason",
        "diagnosis-cost",
        "diagnosis-run",
        "diagnosis-retry",
        "diagnosis-chart",
        "diagnosis-chart-desc",
        "diagnosis-curve-table",
        "diagnosis-result",
        "diagnosis-belief-delta",
        "diagnosis-timeline",
        "diagnosis-audit",
        "diagnosis-reveal",
        "diagnosis-truth",
    }
    counts = Counter(parser.ids)
    assert required <= set(counts)
    assert all(counts[item] == 1 for item in required)
    assert "/tempo/#conductivity" in parser.links


def test_beginner_copy_preserves_scope_and_five_hypotheses(sources) -> None:
    markup, script, _, _ = sources
    corpus = f"{markup}\n{script}"
    for text in (
        "Why did peak separation grow relative to the frozen healthy control?",
        "Saved synthetic diagnosis run · not a diagnosis of a real sample · no hardware control",
        "Working beliefs within five predefined synthetic hypotheses",
        "Slow electron-transfer kinetics",
        "Uncompensated resistance",
        "Reference-electrode drift",
        "Electrode fouling",
        "Concentration or preparation error",
        "Full curves come from the verified synthetic response",
        "The browser does not reconstruct them from peak markers",
    ):
        assert text in corpus


def test_browser_uses_one_closed_decoder_and_exact_recommendation(sources) -> None:
    _, script, _, _ = sources
    for field in (
        "schema_version",
        "response_id",
        "response_hash",
        "request_id",
        "idempotency_input_hash",
        "scenario_id",
        "campaign_id",
        "previous_state_version",
        "state_version",
        "previous_ledger_hash",
        "ledger_hash",
        "status",
        "payload",
        "planner_version",
        "expected_information_gain_nats",
        "action_input_hash",
    ):
        assert f'"{field}"' in script
    assert "diagnosisExactObject(envelope, DIAGNOSIS_ENVELOPE_FIELDS" in script
    assert 'payload.type === "scenario"' in script
    assert 'payload.type === "state"' in script
    assert 'payload.type === "ledger"' in script
    assert 'payload.type === "reveal"' in script
    assert 'payload.type === "error"' in script
    assert "The browser never" not in script or "posterior" not in script


def test_full_curve_is_verified_and_never_reconstructed_from_peaks(sources) -> None:
    markup, script, _, _ = sources
    assert "curve.potential_v.length === 122" in script
    assert "curve.current_a.length === 122" in script
    assert 'curve.potential_reference === "synthetic_SHE"' in script
    assert "diagnosisExtractPeak(curve)" in script
    assert "diagnosisValidatePeakAgainstCurve" in script
    assert 'diagnosisWithout(curve, "curve_hash")' in script
    assert "diagnosisCurvePath(curve, frame)" in script
    assert "browser does not reconstruct" in markup


def test_run_binds_exact_server_recommendation_and_raw_request_bytes(sources) -> None:
    _, script, _, _ = sources
    body = re.search(r"const body = \{ request_id: diagnosisRequestId\(\), expected_state_version: diagnosis\.campaign\.state_version, recommendation_id: recommendation\.recommendation_id, action_input_hash: recommendation\.action_input_hash, operation: recommendation\.operation, controls: recommendation\.controls \};", script)
    assert body
    assert "const rawBody = JSON.stringify(body);" in script
    assert 'method: "POST"' in script
    assert "request_body_hash: requestBodyHash" in script
    assert "diagnosis.pending" in script
    assert "Retry uses the identical request ID and bytes" in script
    assert "event.idempotency_input_hash === prepared.inputHash" in script


def test_422_stale_failure_and_leakage_paths_fail_closed(sources) -> None:
    markup, script, _, _ = sources
    corpus = f"{markup}\n{script}"
    assert "[200, 422].includes(response.status)" in script
    assert "Action response is stale against the submitted verified state" in script
    assert "Request rejected · attempt charged · no experiment executed · working beliefs unchanged." in corpus
    assert "Pre-reveal response leaked private fixture data" in script
    assert "diagnosisHasSecretKey(envelope)" in script
    assert "No replacement value was created" in corpus
    assert "diagnosis.latestCurve = diagnosisLatestCurveFromEvents(verified.events)" in script
    assert "DIAGNOSIS_REJECTION_MESSAGES[event.rejection_code] === event.rejection_message" in script
    assert "diagnosisReconcileTransition(diagnosis.campaign, responseState, event)" in script
    assert "diagnosisReconcileLedger(envelope.payload.state, envelope.payload.events, diagnosis.scenario.prior)" in script
    assert "diagnosisValidateGetIdentity(envelope, path)" in script
    assert "diagnosisValidatePreparedIdentity(envelope, prepared, response.status)" in script
    assert "diagnosisSame(verified.state, responseState)" in script


def test_reveal_requires_click_terminal_state_and_original_commitment(sources) -> None:
    _, script, _, _ = sources
    assert 'byId("diagnosis-reveal").addEventListener("click", revealDiagnosisTruth)' in script
    assert "!diagnosis.campaign?.stop.terminal" in script
    assert "diagnosis.scenario.commitment" in script
    assert "diagnosisCanonicalJson(payload)" in script
    assert "Reveal does not open the original Scenario commitment" in script
    load_body = script[script.index("async function loadDiagnosis()") : script.index("function configureDiagnosis()")]
    assert "revealDiagnosisTruth" not in load_body


def test_accessible_and_responsive_paths_are_present(sources) -> None:
    markup, _, styles, _ = sources
    assert 'role="status" aria-live="polite"' in markup
    assert 'role="alert" tabindex="-1"' in markup
    assert 'aria-labelledby="diagnosis-chart-title diagnosis-chart-desc"' in markup
    assert "Complete verified synthetic CV points" in (markup + JS.read_text(encoding="utf-8"))
    assert "@media (max-width: 420px)" in styles
    assert "@media (max-width: 720px)" in styles
    assert "@media (prefers-reduced-motion: reduce)" in styles
    assert ".diagnosis-belief-row" in styles
    assert "#diagnosis-curve-table { contain: strict; }" in styles
    assert "@media (max-width: 1100px)" in styles
    narrow = styles[styles.index("@media (max-width: 420px)") :]
    assert ".diagnosis-question-strip .status-pill" in narrow
    assert "max-width: 100%" in narrow
    assert "white-space: normal" in narrow


def test_javascript_parses() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is unavailable")
    completed = subprocess.run(
        [node, "--check", str(JS)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_browser_reconciliation_rejects_cross_object_tampering() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is unavailable")
    completed = subprocess.run(
        [node, str(RECONCILIATION_TEST)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "adversarial vectors passed" in completed.stdout
