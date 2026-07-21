"use strict";

const REFERENCE_URL = "/tempo/reference-v1.json";
const ANALYZE_URL = "/api/tempo/analyze";
const CONDUCTIVITY_URL = "/api/tempo/conductivity";
const INFERENCE_SCHEMA = "tempo-inference-v1";

const EXPECTED_ATLAS = Object.freeze({
  "4ht": { name: "4-hydroxy-TEMPO", e0: 0.812, d: 3.14e-6, k0: 4.45e-3, water: 2.11, kcl: 1.25, capacity: 33.5 },
  "4ot": { name: "4-oxo-TEMPO", e0: 0.910, d: 4.61e-6, k0: 1.05e-2, water: 1.22, kcl: 0.79, capacity: 21.2 },
  "4at": { name: "4-amino-TEMPO", e0: 0.895, d: 3.77e-6, k0: 4.01e-3, water: 5.79, kcl: 4.80, capacity: 128.6 },
  "4cyt": { name: "4-cyano-TEMPO", e0: 0.881, d: 6.23e-6, k0: 4.29e-3, water: 2.6e-2, kcl: null, capacity: null },
  "4cat": { name: "4-carboxy-TEMPO", e0: 0.776, d: 2.64e-6, k0: 2.25e-3, water: 2.1e-2, kcl: null, capacity: null },
});

const QUANTITY_KEYS = Object.freeze({
  e0: "formal_potential_v_vs_she",
  d: "diffusion_coefficient_cm2_s",
  k0: "electron_transfer_rate_constant_cm_s",
  water: "solubility_water_mol_l",
  kcl: "solubility_kcl_mol_l",
  capacity: "theoretical_capacity_ah_l",
});

const state = {
  atlas: null,
  selectedSamples: new Set(),
  analysisController: null,
  conductivityController: null,
  analysisRequestId: null,
  conductivityRequestId: null,
};

const byId = (id) => document.getElementById(id);

function create(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined && text !== null) element.textContent = String(text);
  if (className) element.className = className;
  return element;
}

function stableValue(value) {
  if (Array.isArray(value)) return value.map(stableValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, stableValue(value[key])]));
  }
  return value;
}

function stableStringify(value) {
  return JSON.stringify(stableValue(value));
}

async function sha256Hex(value) {
  const bytes = new TextEncoder().encode(typeof value === "string" ? value : stableStringify(value));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: { "Accept": "application/json", ...(options.body ? { "Content-Type": "application/json" } : {}), ...(options.headers || {}) },
  });
  let body;
  try {
    body = await response.json();
  } catch {
    throw new Error(`${url} returned malformed JSON`);
  }
  if (!response.ok) {
    const refusal = body?.refusal || body?.error || body;
    const message = refusal?.message || `${url} returned HTTP ${response.status}`;
    const error = new Error(message);
    error.status = response.status;
    error.payload = body;
    throw error;
  }
  return body;
}

function quantity(sample, key) {
  const item = sample?.quantities?.[QUANTITY_KEYS[key]];
  if (!item || typeof item !== "object") throw new Error(`sample ${sample?.sample_id || "unknown"} is missing typed quantity ${QUANTITY_KEYS[key]}`);
  if (!["reported", "not_reported"].includes(item.status)) throw new Error(`invalid status for ${sample.sample_id}.${QUANTITY_KEYS[key]}`);
  if (item.status === "not_reported") {
    if (item.value !== null) throw new Error(`not-reported ${sample.sample_id}.${QUANTITY_KEYS[key]} must be null`);
    return null;
  }
  if (typeof item.value !== "number" || !Number.isFinite(item.value)) throw new Error(`invalid numeric value for ${sample.sample_id}.${QUANTITY_KEYS[key]}`);
  if (!item.unit || !item.condition_id || !item.method_id) throw new Error(`incomplete provenance for ${sample.sample_id}.${QUANTITY_KEYS[key]}`);
  return item.value;
}

function validateReferenceDataset(dataset) {
  if (!dataset || dataset.schema_version !== "tempo-reference-v1") throw new Error("reference schema mismatch");
  if (dataset.doi !== "10.1039/D0RA03424J") throw new Error("reference DOI mismatch");
  if (dataset.license_id !== "CC-BY-NC-3.0") throw new Error("reference licence mismatch");
  if (!dataset.record_checksum || typeof dataset.record_checksum !== "string") throw new Error("reference record checksum missing");
  if (!Array.isArray(dataset.conditions) || !Array.isArray(dataset.samples) || dataset.samples.length !== 5) throw new Error("reference must contain its conditions and exactly five samples");
  const ids = dataset.samples.map((sample) => sample.sample_id);
  if (new Set(ids).size !== 5 || Object.keys(EXPECTED_ATLAS).some((id) => !ids.includes(id))) throw new Error("reference sample identity mismatch");

  dataset.samples.forEach((sample) => {
    const expected = EXPECTED_ATLAS[sample.sample_id];
    if (sample.preferred_name !== expected.name || sample.provenance !== "published_reported_scalar" || sample.source_table !== "Table 1") {
      throw new Error(`reference identity/provenance mismatch for ${sample.sample_id}`);
    }
    Object.keys(QUANTITY_KEYS).forEach((key) => {
      const actual = quantity(sample, key);
      if (actual !== expected[key]) throw new Error(`reference value mismatch for ${sample.sample_id}.${key}`);
    });
  });
  return dataset;
}

function formatValue(value, key) {
  if (value === null) return "not reported";
  if (key === "d" || key === "k0") return Number(value).toExponential(2);
  if (key === "e0") return Number(value).toFixed(3);
  if (key === "water" || key === "kcl") return Number(value).toLocaleString(undefined, { maximumSignificantDigits: 3 });
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function renderAtlas(dataset) {
  const cards = byId("sample-cards");
  const tbody = byId("atlas-table-body");
  cards.replaceChildren();
  tbody.replaceChildren();
  state.selectedSamples = new Set(dataset.samples.map((sample) => sample.sample_id));

  dataset.samples.forEach((sample) => {
    const expected = EXPECTED_ATLAS[sample.sample_id];
    const wrapper = create("div", null, "sample-card");
    const label = create("label");
    const checkbox = create("input");
    checkbox.type = "checkbox";
    checkbox.checked = true;
    checkbox.value = sample.sample_id;
    checkbox.setAttribute("aria-label", `Include ${sample.preferred_name} in the reported-value comparison`);
    label.append(checkbox, create("b", sample.preferred_name), create("span", `${sample.sample_id.toUpperCase()} · E0 ${formatValue(expected.e0, "e0")} V vs SHE`), create("span", "◆ Zhou Table 1 · reported scalar"));
    wrapper.appendChild(label);
    cards.appendChild(wrapper);

    const row = create("tr");
    row.dataset.sampleId = sample.sample_id;
    row.dataset.selected = "true";
    const includeCell = create("td");
    const rowCheckbox = create("input");
    rowCheckbox.type = "checkbox";
    rowCheckbox.checked = true;
    rowCheckbox.setAttribute("aria-label", `Include ${sample.preferred_name} in comparison`);
    includeCell.appendChild(rowCheckbox);
    row.append(includeCell, create("th", sample.preferred_name));
    row.lastChild.scope = "row";
    ["e0", "d", "k0", "water", "kcl", "capacity"].forEach((key) => {
      const value = quantity(sample, key);
      const cell = create("td", formatValue(value, key), value === null ? "not-reported" : "");
      if (value === null) cell.setAttribute("aria-label", `${sample.preferred_name}: ${QUANTITY_KEYS[key]} not reported by the source`);
      row.appendChild(cell);
    });
    tbody.appendChild(row);

    const setSelected = (selected) => {
      if (selected) state.selectedSamples.add(sample.sample_id);
      else state.selectedSamples.delete(sample.sample_id);
      checkbox.checked = selected;
      rowCheckbox.checked = selected;
      row.dataset.selected = String(selected);
      updateAtlasSelectionSummary();
    };
    checkbox.addEventListener("change", () => setSelected(checkbox.checked));
    rowCheckbox.addEventListener("change", () => setSelected(rowCheckbox.checked));
  });

  updateAtlasSelectionSummary();
  byId("atlas-status").hidden = true;
  byId("atlas-content").hidden = false;
}

function updateAtlasSelectionSummary() {
  const selected = [...state.selectedSamples].map((id) => EXPECTED_ATLAS[id].name);
  byId("atlas-selection-summary").textContent = selected.length
    ? `Comparison set (${selected.length}): ${selected.join(", ")}. No overall score, winner, or rank is calculated.`
    : "Comparison set is empty. Choose at least one reported record; missing source values will remain not reported.";
}

async function loadAtlas() {
  try {
    const dataset = validateReferenceDataset(await fetchJson(REFERENCE_URL));
    state.atlas = dataset;
    renderAtlas(dataset);
  } catch (error) {
    byId("atlas-status").hidden = true;
    byId("atlas-content").hidden = true;
    const failure = byId("atlas-error");
    failure.hidden = false;
    failure.querySelector("p").textContent = `The published reference record could not be verified (${error.message}). No substitute values or synthetic curves are shown.`;
  }
}

function numberValue(input) {
  if (input.value.trim() === "") return null;
  const value = Number(input.value);
  return Number.isFinite(value) ? value : null;
}

function peakRows() {
  return [...byId("peak-table").tBodies[0].rows].map((row) => {
    const inputs = row.querySelectorAll("input");
    return {
      rate_mV_s: Number(row.dataset.rate),
      epa_v: numberValue(inputs[0]),
      epc_v: numberValue(inputs[1]),
      ipa_mA: numberValue(inputs[2]),
      ipc_mA: numberValue(inputs[3]),
      reviewed: inputs[4].checked,
    };
  });
}

function buildSyntheticTrace(row, index) {
  const potential = [];
  const current = [];
  for (let point = 0; point < 24; point += 1) {
    const fraction = point / 23;
    const e = 0.72 + fraction * 0.20;
    const anodic = row.ipa_mA * Math.exp(-Math.pow((e - row.epa_v) / 0.022, 2));
    const cathodic = row.ipc_mA * Math.exp(-Math.pow((e - row.epc_v) / 0.024, 2));
    potential.push(e);
    current.push((anodic + cathodic) / 1000);
  }
  return {
    trace_id: `synthetic-rate-${row.rate_mV_s}`,
    scan_rate_v_s: row.rate_mV_s / 1000,
    replicate_id: "synthetic-fixture-1",
    cycle_number: 1,
    potential_v: potential,
    current_a: current,
    potential_scale: "SHE",
    transformation: "raw",
    fixture_order: index,
  };
}

async function buildAnalysisRequest() {
  const rows = peakRows();
  const fixtureChecksum = await sha256Hex({ rows, fixture: "tempo-six-rate-reviewed-peaks-v1" });
  const request = {
    schema_version: INFERENCE_SCHEMA,
    request_id: crypto.randomUUID(),
    source: {
      provenance: "synthetic_teaching",
      source_id: "tempo-six-rate-reviewed-peaks-v1",
      checksum: fixtureChecksum,
    },
    sample: {
      sample_id: "tempo-teaching-a",
      preferred_name: byId("sample-name").value.trim(),
      molecular_form: byId("molecular-form").value.trim(),
      concentration_mol_cm3: numberValue(byId("concentration")),
    },
    condition: {
      condition_id: "synthetic-tempo-kcl-298k-v1",
      solvent: "water",
      supporting_electrolyte: { name: "KCl", concentration_mol_l: 0.5 },
      ph: { status: "measured", value: 7 },
      temperature_k: numberValue(byId("temperature")),
      working_electrode: { material: "glassy carbon", area_cm2: numberValue(byId("electrode-area")) },
      counter_electrode: "Pt foil",
      reference_electrode: "SCE",
      potential_scale: "SHE",
      electron_count: numberValue(byId("electron-count")),
      atmosphere: "N2 teaching context",
      preprocessing_description: "none; deterministic synthetic teaching fixture",
      units: { potential: "V", current: "A", scan_rate: "V/s", area: "cm2", concentration: "mol/cm3", temperature: "K" },
    },
    traces: rows.map(buildSyntheticTrace),
    peak_assignments: rows.map((row) => ({
      trace_id: `synthetic-rate-${row.rate_mV_s}`,
      epa_v: row.epa_v,
      epc_v: row.epc_v,
      ipa_a: row.ipa_mA === null ? null : row.ipa_mA / 1000,
      ipc_a: row.ipc_mA === null ? null : row.ipc_mA / 1000,
      assignment_source: "manual",
      reviewed: row.reviewed,
    })),
    requested: [...document.querySelectorAll('input[name="requested"]:checked')].map((input) => input.value),
  };
  if (byId("request-ir").checked) {
    if (!byId("ir-record-reviewed").checked) throw new Error("Review and confirm the independent iR record before requesting correction.");
    const operationId = byId("resistance-operation-id").value.trim();
    const sharedContext = {
      sample_id: request.sample.sample_id,
      cell_id: byId("ir-cell-id").value.trim(),
      geometry_id: byId("ir-geometry-id").value.trim(),
      electrolyte_id: byId("ir-electrolyte-id").value.trim(),
      condition_id: request.condition.condition_id,
    };
    request.ir_correction = {
      ru_ohm: numberValue(byId("ru-ohm")),
      resistance_source: {
        operation_id: operationId,
        provenance: "independent_resistance_measurement",
      },
      measurement_method: byId("resistance-method").value,
      measurement_context: {
        reviewed: byId("ir-record-reviewed").checked,
        resistance: { operation_id: operationId, ...sharedContext },
        cv: { ...sharedContext },
      },
      fraction: numberValue(byId("ir-fraction")),
    };
  }
  return request;
}

function resetAnalysisResults(message = "Inputs changed. Submit the reviewed assignments to request a new analysis.") {
  state.analysisController?.abort();
  state.analysisController = null;
  state.analysisRequestId = null;
  byId("analysis-error").hidden = true;
  const cards = byId("result-cards");
  cards.replaceChildren(
    noEstimateCard("Apparent midpoint potential (E1/2)", message),
    noEstimateCard("Diffusion coefficient", "Requires eligible metadata and at least three distinct reviewed scan rates."),
    noEstimateCard("Reversibility evidence", "INCONCLUSIVE · descriptors only; no categorical class or ranking."),
    noEstimateCard("iR-corrected view", "Requires eligible independent Ru provenance; raw arrays remain recoverable."),
  );
  byId("response-audit").textContent = "No current response. Upstream input changed or no request has been sent.";
  byId("request-audit").textContent = "No current request. Input changed or no request has been sent.";
}

function noEstimateCard(title, message, refusal) {
  const card = create("article", null, "result-card no-estimate");
  card.append(create("b", "— NO ESTIMATE"), create("h4", title), create("p", message));
  if (refusal) {
    const list = create("dl");
    [["Code", refusal.code], ["Missing", refusal.missing_fields?.join(", ")], ["Invalid", refusal.invalid_fields?.join(", ")], ["Excluded traces", refusal.excluded_trace_ids?.join(", ")], ["Audit ID", refusal.audit_id]].forEach(([label, value]) => {
      if (!value) return;
      list.append(create("dt", label), create("dd", value));
    });
    card.appendChild(list);
  }
  return card;
}

function summaryCard(title, status, primary, rows, note) {
  const card = create("article", null, "result-card");
  card.append(create("b", `ƒ DERIVED FROM SELECTED DATA · ${status}`), create("h4", title));
  if (primary) card.append(create("strong", primary, "result-primary"));
  if (rows?.length) {
    const list = create("dl", null, "result-summary");
    rows.forEach(([label, value]) => list.append(create("dt", label), create("dd", value)));
    card.appendChild(list);
  }
  if (note) card.append(create("p", note));
  return card;
}

function displayNumber(value, digits = 3) {
  return typeof value === "number" && Number.isFinite(value) ? value.toPrecision(digits) : "not available";
}

function aggregateMean(value) {
  if (typeof value === "number") return value;
  return value && typeof value.mean === "number" ? value.mean : null;
}

function rangeText(values, unit, digits = 3) {
  const eligible = values.filter((value) => typeof value === "number" && Number.isFinite(value));
  if (!eligible.length) return "not available";
  const minimum = Math.min(...eligible);
  const maximum = Math.max(...eligible);
  return minimum === maximum ? `${displayNumber(minimum, digits)} ${unit}` : `${displayNumber(minimum, digits)}–${displayNumber(maximum, digits)} ${unit}`;
}

function validateNoEstimate(payload) {
  const refusal = payload.refusal || payload.error || payload;
  const required = ["code", "message", "missing_fields", "invalid_fields", "excluded_trace_ids", "audit_id"];
  if (required.some((key) => !(key in refusal))) throw new Error("NO ESTIMATE response is missing its refusal audit fields");
  if (!["missing_fields", "invalid_fields", "excluded_trace_ids"].every((key) => Array.isArray(refusal[key]))) throw new Error("NO ESTIMATE refusal lists are invalid");
  return refusal;
}

async function validateAnalysisResponse(response, request, expectedHash) {
  if (!response || response.schema_version !== INFERENCE_SCHEMA) throw new Error("analysis response schema mismatch");
  if (response.request_id !== request.request_id || response.request_id !== state.analysisRequestId) throw new Error("stale or mismatched analysis response discarded");
  if (!["estimate_available", "no_estimate"].includes(response.status)) throw new Error("analysis response status missing or invalid");
  if (response.status === "no_estimate") return { response, refusal: validateNoEstimate(response) };
  if (response.provenance !== "derived") throw new Error("analysis result is not labelled derived");
  if (!response.method_version || !response.input_hash || !response.results || typeof response.results !== "object") throw new Error("analysis result is missing method, hash, or results");
  if (!Array.isArray(response.warnings) || !Array.isArray(response.limitations) || !response.audit) throw new Error("analysis result is missing warnings, limitations, or audit");
  if (response.input_hash !== expectedHash) throw new Error("analysis input hash mismatch; stale result withheld");
  validateAnalysisResults(response.results);
  return { response, refusal: null };
}

function validateSubresultStatus(result, label) {
  if (!result || typeof result !== "object") throw new Error(`${label} result is not an object`);
  if (!["estimate_available", "no_estimate"].includes(result.status)) throw new Error(`${label} result status is invalid`);
}

function validateAnalysisResults(results) {
  if (results.peak_descriptors) {
    const peaks = results.peak_descriptors;
    validateSubresultStatus(peaks, "peak descriptors");
    if (peaks.status === "estimate_available") {
      if (!Array.isArray(peaks.per_trace) || !peaks.aggregate || typeof peaks.aggregate !== "object") throw new Error("peak descriptors are missing per-trace or aggregate evidence");
      ["e_half_v", "delta_ep_v", "peak_current_ratio"].forEach((key) => {
        if (!(key in peaks.aggregate)) throw new Error(`peak aggregate is missing ${key}`);
      });
      if (!("reversibility_evidence" in peaks)) throw new Error("peak descriptors are missing reversibility evidence");
    }
  }

  if (results.diffusion) {
    const diffusion = results.diffusion;
    validateSubresultStatus(diffusion, "diffusion");
    if (diffusion.status === "estimate_available") {
      if (!diffusion.model || !diffusion.branches || typeof diffusion.branches !== "object") throw new Error("diffusion result is missing its model or branches");
      ["anodic", "cathodic"].forEach((name) => {
        const branch = diffusion.branches[name];
        validateSubresultStatus(branch, `${name} diffusion branch`);
        if (branch.branch !== name) throw new Error(`${name} diffusion branch identity mismatch`);
        if (branch.status === "estimate_available") {
          ["diffusion_coefficient_cm2_s", "ci95_cm2_s", "slope_a_per_sqrt_v_s", "slope_standard_error", "intercept_a", "r_squared", "residuals_a", "included_trace_ids", "excluded_trace_ids", "qc_gate", "flags"].forEach((key) => {
            if (!(key in branch)) throw new Error(`${name} diffusion branch is missing ${key}`);
          });
        }
      });
    }
  }

  if (results.ir_correction) {
    const correction = results.ir_correction;
    validateSubresultStatus(correction, "iR correction");
    if (correction.status === "estimate_available") {
      ["ru_ohm", "fraction", "resistance_source", "measurement_method", "measurement_context", "traces", "limitation"].forEach((key) => {
        if (!(key in correction)) throw new Error(`iR correction is missing ${key}`);
      });
      if (!Array.isArray(correction.traces)) throw new Error("iR correction traces are invalid");
    }
  }
}

function renderAnalysisResponse(validated) {
  const { response, refusal } = validated;
  const cards = byId("result-cards");
  cards.replaceChildren();
  if (refusal) {
    const titles = ["Apparent midpoint potential (E1/2)", "Diffusion coefficient", "Reversibility evidence", "iR-corrected view"];
    titles.forEach((title) => cards.appendChild(noEstimateCard(title, refusal.message, refusal)));
    byId("analysis-live").textContent = `No estimate. ${refusal.message}`;
    return;
  }

  const results = response.results;
  const peaks = results.peak_descriptors || null;
  const diffusion = results.diffusion || null;
  const evidence = results.peak_descriptors?.reversibility_evidence || null;
  const ir = results.ir_correction || null;
  const peakRows = peaks?.per_trace || [];
  const eHalfMean = aggregateMean(peaks?.aggregate?.e_half_v);
  const anodic = diffusion?.branches?.anodic;
  const cathodic = diffusion?.branches?.cathodic;
  cards.append(
    peaks ? summaryCard(
      "Peak descriptors",
      "ESTIMATE AVAILABLE",
      eHalfMean === null ? "Mean E1/2 unavailable" : `${displayNumber(eHalfMean, 4)} V vs SHE`,
      [
        ["Mean apparent midpoint", "E1/2 across reviewed pairs"],
        ["ΔEp range", rangeText(peakRows.map((item) => item.delta_ep_v), "V")],
        ["|ipa/ipc| range", rangeText(peakRows.map((item) => item.peak_current_ratio), "")],
      ],
      `${peakRows.length} reviewed peak pair${peakRows.length === 1 ? "" : "s"}.`,
    ) : noEstimateCard("Apparent midpoint potential (E1/2)", "The API returned no eligible peak descriptor."),
    diffusion ? summaryCard(
      "Diffusion coefficient",
      "MODEL-DEPENDENT",
      "Separate branch fits",
      [
        ["Anodic D", anodic ? `${displayNumber(anodic.diffusion_coefficient_cm2_s)} cm² s⁻¹ · R² ${displayNumber(anodic.r_squared, 4)}` : "not available"],
        ["Cathodic D", cathodic ? `${displayNumber(cathodic.diffusion_coefficient_cm2_s)} cm² s⁻¹ · R² ${displayNumber(cathodic.r_squared, 4)}` : "not available"],
      ],
      "R² is a software QC gate, not proof of diffusion control.",
    ) : noEstimateCard("Diffusion coefficient", "The API returned no eligible diffusion estimate."),
    evidence ? summaryCard(
      "Reversibility evidence",
      evidence.summary || "PARTIAL EVIDENCE",
      evidence.summary || "PARTIAL EVIDENCE",
      [["Descriptors", Array.isArray(evidence.descriptors) ? evidence.descriptors.join(" · ") : "ΔEp · current ratio · peak drift"]],
      evidence.limitation || "Descriptors do not establish a categorical reversibility class.",
    ) : noEstimateCard("Reversibility evidence", "INCONCLUSIVE · no categorical class or ranking."),
    ir ? summaryCard(
      "iR-corrected view",
      "POINTWISE PREVIEW",
      `${displayNumber(ir.fraction * 100, 3)}% of iRu applied`,
      [["Independent Ru", `${displayNumber(ir.ru_ohm, 4)} Ω`], ["Corrected traces", String(ir.traces?.length || 0)]],
      ir.limitation || "Raw arrays remain available in the audit record.",
    ) : noEstimateCard("iR-corrected view", "No eligible independent Ru correction was returned; raw arrays remain unchanged."),
  );
  const caution = [...response.warnings, ...response.limitations].join(" ");
  byId("analysis-live").textContent = `Analysis complete. ${caution || "Review derived cards and audit details."}`;
}

async function submitAnalysis(event) {
  event.preventDefault();
  state.analysisController?.abort();
  const controller = new AbortController();
  state.analysisController = controller;
  byId("analysis-error").hidden = true;
  try {
    const request = await buildAnalysisRequest();
    state.analysisRequestId = request.request_id;
    const inputHash = await sha256Hex(request);
    byId("request-audit").textContent = JSON.stringify({ ...request, browser_input_hash: inputHash }, null, 2);
    byId("response-audit").textContent = "Waiting for the same-origin analysis API…";
    byId("analysis-live").textContent = "Analysis request sent. Existing results were cleared.";
    const body = stableStringify(request);
    const response = await fetchJson(ANALYZE_URL, { method: "POST", body, headers: { "X-Tempo-Input-Hash": inputHash }, signal: controller.signal });
    if (controller.signal.aborted) return;
    const validated = await validateAnalysisResponse(response, request, inputHash);
    byId("response-audit").textContent = JSON.stringify(response, null, 2);
    renderAnalysisResponse(validated);
  } catch (error) {
    if (error.name === "AbortError") return;
    const payload = error.payload;
    byId("response-audit").textContent = JSON.stringify(payload || { error: error.message }, null, 2);
    const failure = byId("analysis-error");
    failure.hidden = false;
    failure.replaceChildren(create("b", "NO ESTIMATE"), create("p", error.message));
    let refusal = null;
    try { if (payload) refusal = validateNoEstimate(payload); } catch { refusal = null; }
    const cards = byId("result-cards");
    cards.replaceChildren(
      noEstimateCard("Apparent midpoint potential (E1/2)", refusal?.message || error.message, refusal),
      noEstimateCard("Diffusion coefficient", refusal?.message || error.message, refusal),
      noEstimateCard("Reversibility evidence", "INCONCLUSIVE · no hard class is emitted.", refusal),
      noEstimateCard("iR-corrected view", "Raw arrays only; no eligible correction was returned.", refusal),
    );
    byId("analysis-live").textContent = `No estimate. ${error.message}`;
  } finally {
    if (state.analysisController === controller) state.analysisController = null;
  }
}

function buildConductivityRequest() {
  if (!byId("calibration-record-reviewed").checked || !byId("conductivity-record-reviewed").checked) {
    throw new Error("Review and confirm both the calibration and independent resistance records before calculating conductivity.");
  }
  const calibrationId = byId("calibration-id").value.trim();
  const sampleId = byId("conductivity-sample-id").value.trim();
  const cellId = byId("conductivity-cell-id").value.trim();
  const geometryId = byId("conductivity-geometry-id").value.trim();
  const conditionId = byId("conductivity-condition-id").value.trim();
  const matchingContext = {
    sample_id: sampleId,
    cell_id: cellId,
    geometry_id: geometryId,
    condition_id: conditionId,
  };
  return {
    schema_version: INFERENCE_SCHEMA,
    request_id: crypto.randomUUID(),
    resistance_ohm: numberValue(byId("conductivity-resistance")),
    cell_constant_m_inv: numberValue(byId("cell-constant")),
    calibration_source: {
      calibration_id: calibrationId,
      method: byId("calibration-method").value,
      cell_id: cellId,
      geometry_id: geometryId,
      reviewed: byId("calibration-record-reviewed").checked,
    },
    measurement_context: {
      calibration_id: calibrationId,
      reviewed: byId("conductivity-record-reviewed").checked,
      resistance: {
        operation_id: byId("conductivity-operation-id").value.trim(),
        independent: byId("conductivity-record-reviewed").checked,
        resistance_kind: "conductivity_cell",
        ...matchingContext,
      },
      measurement: { ...matchingContext },
    },
    temperature_k: numberValue(byId("conductivity-temperature")),
  };
}

function resetConductivityResult() {
  state.conductivityController?.abort();
  state.conductivityController = null;
  state.conductivityRequestId = null;
  const result = byId("conductivity-result");
  result.className = "conductivity-result no-estimate";
  result.replaceChildren(create("b", "— NO ESTIMATE"), create("h3", "Electrolyte conductivity"), create("p", "Inputs changed. Submit an independently measured resistance and calibrated cell constant for the same context."));
  byId("conductivity-response-audit").textContent = "No current response. Input changed or no request has been sent.";
  byId("conductivity-request-audit").textContent = "No current request. Input changed or no request has been sent.";
}

async function submitConductivity(event) {
  event.preventDefault();
  state.conductivityController?.abort();
  const controller = new AbortController();
  state.conductivityController = controller;
  try {
    const request = buildConductivityRequest();
    state.conductivityRequestId = request.request_id;
    const expectedHash = await sha256Hex(request);
    byId("conductivity-request-audit").textContent = JSON.stringify({ ...request, browser_input_hash: expectedHash }, null, 2);
    byId("conductivity-response-audit").textContent = "Waiting for the independent conductivity API…";
    const body = stableStringify(request);
    const response = await fetchJson(CONDUCTIVITY_URL, { method: "POST", body, headers: { "X-Tempo-Input-Hash": expectedHash }, signal: controller.signal });
    if (controller.signal.aborted) return;
    if (!response || response.schema_version !== INFERENCE_SCHEMA || response.request_id !== request.request_id || response.request_id !== state.conductivityRequestId) throw new Error("stale or mismatched conductivity response discarded");
    if (!["estimate_available", "no_estimate"].includes(response.status)) throw new Error("conductivity response status missing or invalid");
    byId("conductivity-response-audit").textContent = JSON.stringify(response, null, 2);
    const result = byId("conductivity-result");
    if (response.status === "no_estimate") {
      const refusal = validateNoEstimate(response);
      result.className = "conductivity-result no-estimate";
      result.replaceChildren(create("b", "— NO ESTIMATE"), create("h3", "Electrolyte conductivity"), create("p", refusal.message));
      byId("conductivity-live").textContent = `No conductivity estimate. ${refusal.message}`;
      return;
    }
    if (response.provenance !== "derived" || !response.method_version || response.input_hash !== expectedHash || !response.results || !response.audit || !Array.isArray(response.warnings) || !Array.isArray(response.limitations)) throw new Error("conductivity response failed provenance, hash, method, or audit validation");
    const conductivity = response.results.conductivity;
    if (!conductivity || conductivity.status !== "estimate_available" || typeof conductivity.conductivity_s_m !== "number" || conductivity.unit !== "S/m") throw new Error("conductivity result missing or invalid");
    result.className = "conductivity-result";
    result.replaceChildren(create("b", "ƒ DERIVED FROM INDEPENDENT MEASUREMENT INPUTS"), create("h3", "Electrolyte conductivity"), create("p", `${conductivity.conductivity_s_m} S m⁻¹ · κ = Kcell / R · not derived from CV`));
    byId("conductivity-live").textContent = "Independent conductivity calculation complete.";
  } catch (error) {
    if (error.name === "AbortError") return;
    byId("conductivity-response-audit").textContent = JSON.stringify(error.payload || { error: error.message }, null, 2);
    const result = byId("conductivity-result");
    result.className = "conductivity-result no-estimate";
    result.replaceChildren(create("b", "— NO ESTIMATE"), create("h3", "Electrolyte conductivity"), create("p", error.message));
    byId("conductivity-live").textContent = `No conductivity estimate. ${error.message}`;
  } finally {
    if (state.conductivityController === controller) state.conductivityController = null;
  }
}

function configureEvents() {
  const analysisForm = byId("analysis-form");
  analysisForm.addEventListener("submit", submitAnalysis);
  analysisForm.addEventListener("input", () => resetAnalysisResults());
  analysisForm.addEventListener("reset", () => setTimeout(() => {
    byId("ir-fields").disabled = true;
    resetAnalysisResults("Teaching inputs reset. Submit again to request a new analysis.");
  }, 0));
  byId("request-ir").addEventListener("change", () => { byId("ir-fields").disabled = !byId("request-ir").checked; });
  byId("load-ir-teaching-record").addEventListener("click", () => {
    byId("ru-ohm").value = "20";
    byId("ir-fraction").value = "0.85";
    byId("resistance-operation-id").value = "operation-eis-teaching-01";
    byId("resistance-method").value = "EIS high-frequency resistance";
    byId("ir-cell-id").value = "cell-tempo-teaching-01";
    byId("ir-geometry-id").value = "geometry-gce-teaching-01";
    byId("ir-electrolyte-id").value = "electrolyte-kcl-teaching-01";
    byId("ir-record-reviewed").checked = false;
    resetAnalysisResults("Structured iR teaching record loaded but not reviewed. Confirm it, then submit.");
  });

  const conductivityForm = byId("conductivity-form");
  conductivityForm.addEventListener("submit", submitConductivity);
  conductivityForm.addEventListener("input", resetConductivityResult);
  byId("load-conductivity-teaching-record").addEventListener("click", () => {
    byId("conductivity-resistance").value = "100";
    byId("cell-constant").value = "100";
    byId("conductivity-temperature").value = "298.15";
    byId("calibration-method").value = "certified_cell_constant";
    byId("calibration-id").value = "calibration-kcl-teaching-01";
    byId("conductivity-operation-id").value = "resistance-operation-teaching-01";
    byId("conductivity-sample-id").value = "tempo-sample-teaching-01";
    byId("conductivity-cell-id").value = "conductivity-cell-teaching-01";
    byId("conductivity-geometry-id").value = "conductivity-geometry-teaching-01";
    byId("conductivity-condition-id").value = "conductivity-condition-teaching-298k";
    byId("calibration-record-reviewed").checked = false;
    byId("conductivity-record-reviewed").checked = false;
    resetConductivityResult();
    byId("conductivity-live").textContent = "Structured conductivity teaching record loaded but not reviewed. Confirm both records, then calculate.";
  });
}

async function start() {
  configureEvents();
  await loadAtlas();
}

start();
