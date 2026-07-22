# Closed-loop CV diagnosis — restricted-v1 contract

Status: frozen implementation contract; synthetic benchmark only; no real-sample diagnosis or hardware control.

## 1. Scope and fixed identities

- Question: what best explains the increase in apparent peak separation from the frozen synthetic healthy/control comparator to the initial abnormal synthetic CV?
- Provenance is `simulated` or `derived_from_simulated`; beliefs are model-relative working beliefs, not calibrated real-world probabilities.
- `schema_version="1.0.0"`; `scenario_id="cv_diagnosis_v1"`; `scenario_version="1.0.0"`; `planner_id="expected_information_gain_v1"`; `planner_version="1.0.0"`; `belief_method="gaussian_log_bayes_v1"`.
- Hypothesis IDs in frozen order: `slow_kinetics`, `uncompensated_resistance`, `reference_drift`, `electrode_fouling`, `concentration_preparation_error`. Prior: `[.2,.2,.2,.2,.2]`.

## 2. Actions, costs, budgets, and private fixture

| operation | exact controls | attempt/measurement cost |
|---|---|---|
| `repeat_cv` | `{"scan_rate_mv_s":r}`, `r∈[5,10,25,50,100,200]` | `1/1` |
| `measure_ru` | `{}` | `1/1` |
| `check_reference` | `{}` | `1/1` |
| `run_blank` | `{}` | `1/1` |
| `dilute_and_repeat` | `{"dilution_factor":0.5,"scan_rate_mv_s":25}` | `1/1` |
| `clean_and_repeat` | `{"scan_rate_mv_s":25}` | `1/1` |
| `run_control_sample` | `{"scan_rate_mv_s":25}` | `1/1` |

- Limits: 12 attempts and 10 measurements. Success, timeout, or QC failure costs `1/1`; parseable semantic rejection costs `1/0`; 400/404/409/500 and reveal cost `0/0`.
- Private committed fixture: cause `uncompensated_resistance`; world/noise/failure seeds `1701/2718/3141`; timeout on accepted execution attempt 2. Timeout has null observation, unchanged beliefs, and does not consume a successful-repeat index.

## 3. Exhaustive scientific wire types and CV rule

- JSON is UTF-8 RFC 8259, finite numbers only, closed objects only. `JCS(x)` is RFC 8785 canonical JSON; every hash is lowercase hex SHA-256.
- `HypothesisId="slow_kinetics"|"uncompensated_resistance"|"reference_drift"|"electrode_fouling"|"concentration_preparation_error"`; `Operation="repeat_cv"|"measure_ru"|"check_reference"|"run_blank"|"dilute_and_repeat"|"clean_and_repeat"|"run_control_sample"`; valid `(Operation,controls)` pairs are exactly the rows in §2.
- `Peak={Epa_v:number,Epc_v:number,ipa_a:number,ipc_a:number,midpoint_v:number,delta_Ep_v:number,ipa_abs_over_ipc_abs:number}`.
- `Curve={point_count:122,potential_reference:"synthetic_SHE",potential_unit:"V",current_unit:"A",potential_v:number[122],current_a:number[122],sweep_direction:("forward"|"reverse")[122],curve_hash:string}`.
- `Observation={kind:"cv"|"scalar",feature_name:null|"ru_ohm"|"reference_offset_v"|"blank_current_a"|"recovery_ratio"|"control_delta_Ep_v",value:number|null,unit:null|"ohm"|"V"|"A"|"ratio",peak:Peak|null,curve:Curve|null,qc_status:"passed",evidence_hash:string}`.
- For `kind="cv"`: `feature_name/value/unit=null`, `peak/curve` nonnull. For `kind="scalar"`: `peak/curve=null` and exact feature/unit pairs are `ru_ohm/ohm`, `reference_offset_v/V`, `blank_current_a/A`, `recovery_ratio/ratio`, `control_delta_Ep_v/V`.
- Curve grid: indices 0..60 are forward `0.650+0.005*i V`; indices 61..121 are reverse `0.950-0.005*(i-61) V`. Current is `ipa*exp(-.5*((E-Epa)/.025)^2)` forward and `ipc*exp(-.5*((E-Epc)/.025)^2)` reverse.
- Extract the public Peak from the returned discrete curve: `pa` is the lowest forward index attaining maximum current; `pc` is the lowest reverse index attaining minimum current; `Epa/ipa` and `Epc/ipc` are those points; midpoint, separation, and ratio are then derived. QC recomputes this extraction and requires potential/derived fields within `1e-12` and currents within `1e-18 A`, plus exact grid/directions/units/length/finiteness/hash.
- `curve_hash=SHA-256(JCS(Curve without curve_hash))`; `evidence_hash=SHA-256(JCS(Observation without evidence_hash))`. No curve-level noise/covariance exists. Repeat-CV first draws latent scalar features, derives continuous centers/amplitudes, generates the curve, then extracts the discrete Peak; the extracted Peak is the likelihood evidence. Curves are display geometry, not a physical simulator.

## 4. Comparator, trigger, public likelihood model, and Bayes

- `Fixture={provenance:"simulated",likelihood_role:"excluded",peak:Peak,curve:Curve}`. At 25 mV/s, 298.15 K, synthetic SHE: abnormal generator inputs are `Epa=.850,Epc=.750,ipa=14.79847620154866e-6 A,ipc=-14.508310001518294e-6 A`; healthy/control inputs are `.830,.770` with the same currents. Both Fixtures are produced by §3, consume no budget, and never enter Bayes.
- Repeat CV: `x=sqrt(rate/25)`, `I=14.79847620154866e-6*x`; latent means `[midpoint_v,delta_Ep_v,abs_ipa_a]` by hypothesis are slow `[.800,.060+.035*x,I]`, Ru `[.800,.060+.024*x,I]`, reference `[.835,.086,I]`, fouling `[.800,.080+.010*x,.60*I]`, concentration `[.800,.085+.004*x,.55*I]`; independent SE `[.004,.004,1e-6]`. Continuous generator inputs are `Epa=m+d/2,Epc=m-d/2,ipa=a,ipc=-a/1.02`.
- Scalar means/SE: `measure_ru.ru_ohm=[12,45,12,18,12]/10`; `check_reference.reference_offset_v=[0,0,.035,.005,0]/.008`; `run_blank.blank_current_a=[.5e-6,.5e-6,.5e-6,8e-6,3e-6]/1e-6`; `dilute_and_repeat.recovery_ratio=[1,1,1,1,1.45]/.12`; `clean_and_repeat.recovery_ratio=[1,1,1,1.55,1]/.12`; `run_control_sample.control_delta_Ep_v=[.060,.084,.085,.082,.060]/.006`.
- Central log-space independent-Gaussian update uses only successful scalar feature or extracted `[midpoint_v,delta_Ep_v,abs_ipa_a]`. Five values must be finite, in `[0,1]`, and sum within `1e-12`; otherwise fail closed. Comparator/trigger, curve arrays, duplicate Epa/Epc fields, conductivity, derived diffusion, rejection, timeout, and QC failure are excluded. Browser never computes or repairs beliefs.

## 5. Recommendation, eligibility, and stop

- `Recommendation={recommendation_id:string,state_version:integer,planner_id:"expected_information_gain_v1",planner_version:"1.0.0",operation:Operation,controls:exact action controls,reason_code:"max_expected_information",reason_text:"This eligible experiment has the highest expected information gain under the public five-hypothesis model.",attempt_cost:1,measurement_cost:1,expected_information_gain_nats:number,action_input_hash:string}`.
- Exact action/control is eligible iff campaign is active, cost fits, and it has fewer than two successful identical observations. Timeout/rejection does not count.
- EIG uses current beliefs/public Gaussian model with `z=[-2,-1,0,1,2]` and weights `[.0544886845,.2442013420,.4026199469,.2442013420,.0544886845]`, normalized once; tensor product for 3D. Choose maximum; ties within `1e-12` use table order then numeric rate order.
- `action_input_hash=SHA-256(JCS({operation,controls,state_version,planner_id,planner_version}))`; `recommendation_id=action_input_hash`. Client submits this binding and no rationale.
- After each charged event, terminal precedence is: (1) `budget_exhausted` if attempts=12 or measurements=10; (2) `confident_diagnosis` if at least 3 successful belief observations, 2 distinct successful operation names, max belief `>=.90`, and margin `>=.25`; (3) `low_expected_information` if at least 4 such observations, eligible set nonempty, and maximum eligible EIG `<.01` nats; else active. There is no `insufficient_budget` state.
- Exact copy: `budget_exhausted` → `Stopped · attempt or measurement budget exhausted.`; `confident_diagnosis` → `Stopped · confident diagnosis gate satisfied.`; `low_expected_information` → `Stopped · expected information is below the threshold.`

## 6. Exhaustive campaign and event types

- `Budget={attempt_limit:12,attempt_used:integer,measurement_limit:10,measurement_used:integer}`; `Stop={terminal:boolean,reason:null|"budget_exhausted"|"confident_diagnosis"|"low_expected_information"}`.
- `State={campaign_id:string,scenario_id:"cv_diagnosis_v1",scenario_version:"1.0.0",state_version:integer,status:"active"|"stopped"|"budget_exhausted",beliefs:number[5],budget:Budget,success_count:integer,successful_operations:Operation[],recommendation:Recommendation|null,last_valid_curve_hash:string|null,ledger_head_hash:string,stop:Stop}`.
- `RejectionCode="INVALID_RECOMMENDATION"|"INVALID_OPERATION"|"INVALID_CONTROLS"|"INELIGIBLE_ACTION"|"STOP_RULE_NOT_SATISFIED"`; messages respectively: `Recommendation identity does not match the current campaign state.`; `Operation is not allowed by this scenario.`; `Controls do not match the operation contract.`; `The requested experiment is not currently eligible.`; `No stop rule is satisfied.`
- `Event={event_id:string,event_index:integer,event_type:"action"|"stop",request_id:string,idempotency_input_hash:string,state_version_before:integer,state_version_after:integer,recommendation_id:string|null,operation:Operation|null,controls:object|null,status:"success"|"timeout"|"qc_failed"|"rejected",failure_code:null|"TIMEOUT"|"CURVE_QC_FAILED",failure_message:string|null,rejection_code:RejectionCode|null,rejection_message:string|null,attempt_cost:0|1,measurement_cost:0|1,observation:Observation|null,beliefs_before:number[5],beliefs_after:number[5],previous_event_hash:string,event_hash:string}`.
- Valid action events have recommendation/operation/controls nonnull. A rejected event copies `recommendation_id` only if a string, `operation` only if a known Operation, and `controls` only if the complete exact controls validate; otherwise that field is null. Timeout and QC failure use exact code/message `TIMEOUT/Operation timed out; no observation was created.` or `CURVE_QC_FAILED/Generated CV evidence failed contract QC; no observation was created.` Failure fields are nonnull only for those statuses; rejection fields only for rejected status. Timeout/QC/rejected/stop has `observation=null`.
- First `previous_event_hash=SHA-256(JCS({campaign_id,scenario_id,scenario_version}))`; later it equals prior `event_hash`; `event_hash=SHA-256(JCS(Event without event_hash))`.

## 7. One response envelope and payload decoder

- Every endpoint and error returns `Envelope={schema_version:"1.0.0",response_id:string,response_hash:string,request_id:string|null,idempotency_input_hash:string|null,scenario_id:string|null,campaign_id:string|null,previous_state_version:integer|null,state_version:integer|null,previous_ledger_hash:string|null,ledger_hash:string|null,status:"ok"|"created"|"rejected"|"error",payload:Payload}` with no extra fields. `response_hash=SHA-256(JCS(Envelope without response_hash))`.
- `Hypothesis={id:HypothesisId,label:string,order:integer}`; `ActionSpec={operation:Operation,controls:exact concrete controls,display_label:string,attempt_cost:1,measurement_cost:1}`; the Scenario carries 5 ordered hypotheses and 12 concrete actions (six repeat rates plus six other rows).
- `Scenario={scenario_id:"cv_diagnosis_v1",scenario_version:"1.0.0",planner_id:"expected_information_gain_v1",planner_version:"1.0.0",belief_method:"gaussian_log_bayes_v1",prior:number[5],attempt_limit:12,measurement_limit:10,hypotheses:Hypothesis[5],actions:ActionSpec[12],comparator:Fixture,initial_trigger:Fixture,commitment:string}`.
- Payload union by `type`: `{"type":"scenario","scenario":Scenario}`; `{"type":"state","state":State,"event":Event|null}`; `{"type":"ledger","state":State,"events":Event[]}`; `{"type":"reveal","reveal":Reveal}`; `{"type":"error","error":{"code":ErrorCode,"message":string},"state":State|null,"event":Event|null}`. No other payload/type is valid.
- `CommitmentPayload={scenario_id:"cv_diagnosis_v1",scenario_version:"1.0.0",hidden_truth:{cause:HypothesisId},seed_bundle:{world_seed:1701,noise_seed:2718,failure_seed:3141},reveal_nonce:string}`; nonce is exactly 32 CSPRNG bytes encoded base64url without padding (43 ASCII characters).
- At frozen scenario-artifact creation, generate the nonce once, persist the private CommitmentPayload, and set `Scenario.commitment=SHA-256(JCS(CommitmentPayload))`; every campaign for that scenario/version copies the same commitment. Restart/redeploy never regenerates it. Before reveal, neither payload fields nor nonce may appear anywhere public.
- `Reveal={commitment:string,commitment_payload:CommitmentPayload}`. Browser accepts it only if scenario/version match, the returned commitment equals the initially verified Scenario commitment, and `SHA-256(JCS(commitment_payload))` equals that same commitment. After terminal reveal, the preimage intentionally makes the completed synthetic replay reproducible; it is not reused for another scenario version.
- `ErrorCode="MALFORMED_JSON"|"INVALID_REQUEST_ENVELOPE"|RejectionCode|"NOT_FOUND"|"STALE_STATE"|"TERMINAL_STATE"|"IDEMPOTENCY_CONFLICT"|"REVEAL_NOT_AVAILABLE"|"REVEAL_ALREADY_COMPLETED"|"INTERNAL_ERROR"`. RejectionCode means HTTP 422/status `rejected`; all others status `error`.

## 8. Endpoint matrix and mutation semantics

- `GET /api/v1/closed-loop/scenario` → 200 Scenario payload; request/campaign/state/ledger envelope fields null. `POST /api/v1/closed-loop/campaigns` body `{request_id,scenario_id,scenario_version}` → 201 State payload, status `created`, `event=null`.
- `GET /api/v1/closed-loop/campaigns/{id}` → 200 State payload/event null. `GET .../{id}/ledger` → 200 Ledger payload. GET request IDs are null; current campaign/state/ledger envelope identity is nonnull.
- `POST .../{id}/actions` body `{request_id,expected_state_version,recommendation_id,action_input_hash,operation,controls}` → 200 State payload with one success/failure event, or 422 Error payload with resulting State and one rejected event.
- `POST .../{id}/stop` body `{request_id,expected_state_version}` is a terminal-state acknowledgement: if already terminal it returns 200 current State with `event=null` and no cost/version/hash change; if active it returns charged 422 `STOP_RULE_NOT_SATISFIED` with resulting State/rejected stop event. Terminal transitions themselves occur only through §5 precedence after charged events.
- `POST .../{id}/reveal` body `{request_id,expected_state_version}` → 200 Reveal payload only when terminal. Reveal is non-mutating: event null, cost zero, and state version/ledger hash unchanged. The first successful request/Envelope is cached; repeating the same scoped request and raw bytes returns it byte-for-byte. A different request ID after reveal returns non-mutating 409 `REVEAL_ALREADY_COMPLETED`; preterminal reveal returns non-mutating 409 `REVEAL_NOT_AVAILABLE`.
- Missing/invalid `request_id`, `expected_state_version`, or non-object/malformed/unknown top-level request fields → non-mutating 400 `INVALID_REQUEST_ENVELOPE` (or `MALFORMED_JSON`). Only a parseable base request can produce charged 422.
- A charged 200/422 appends exactly one event, increments state version once, and applies §5 precedence. A 422 charges `1/0`, preserves beliefs/measurement budget, returns exact RejectionCode/message and sanitized nullable request fields, then returns next Recommendation or terminal State.
- For every POST, canonical path is the literal route path with the canonical campaign ID substituted, no query/fragment/trailing slash; method is uppercase `POST`. The idempotency cache key is `(method,canonical_path,campaign_id|null,request_id)`; campaign creation uses null campaign ID. `request_body_hash=SHA-256(exact raw request-body bytes)` and `idempotency_input_hash=SHA-256(JCS({method,canonical_path,campaign_id,request_id,request_body_hash}))`. Event and Envelope carry this hash for every parseable base POST; GET and unparseable 400 use null.
- Same scoped key plus identical raw bytes returns original HTTP status and response bytes without event/version/draw/cost. Same scoped key with different raw bytes → non-mutating 409 `IDEMPOTENCY_CONFLICT`. Method/path are part of the key, so stop/reveal or any cross-endpoint identical body cannot collide. 404/409/500 are non-mutating; 409 supplies current State when campaign is known, otherwise state null.
- Envelope identity: creation returns State version 0 with previous version/hash null; mutating response previous/current versions and ledger hashes bracket its event; State fields equal current Envelope fields. GET/reveal/successful stop have previous=current and event null; rejected stop costs `1/0`. Verify closed schema → identity → response hash → event/evidence/curve hashes → ledger linkage → state/event/budget/belief reconciliation → Recommendation binding, then render atomically.

## 9. Truth boundary, frozen tests, and acceptance

- Commitment preimage, nonce, truth, seeds, and future failure are absent before terminal explicit reveal from every other payload, error, ledger, manifest, DOM/storage/cache/source map. Reveal verification recomputes the original Scenario commitment exactly as in §7.
- Frozen vectors: prior/no-update `[.2,.2,.2,.2,.2]`; confident pass `[.91,.04,.025,.015,.01]`; threshold fail `[.89,.05,.03,.02,.01]`.
- Acceptance pins curve extraction/QC/hash; closed endpoint decoders; exact 422 sanitation/accounting; idempotent action and reveal replay; accepted-attempt-2 timeout and successful-repeat-index routing; Bayes/EIG/ties; terminal precedence/boundaries; chain tamper; recursive leakage; renderer-only browser; accessible curve table; keyboard/screen-reader/reduced-motion/200%/320 px; five-person ten-second comprehension.
- Postponed: real instruments/samples, physical CV simulation, calibration claims, conductivity inference, diffusion in Bayes, free-form LLM planning/rationale, planner leaderboard, cross-campaign sharing, and autonomous execution.

## 10. B1–B8 disposition

| finding | frozen resolution |
|---|---|
| B1 | Exhaustive Curve/Peak/Observation/fixture shapes and discrete extraction/QC are in §3–4. |
| B2 | Exact Recommendation, EIG, eligibility, reason, identity, and controls are in §5. |
| B3 | One Envelope/Payload decoder, exhaustive enums, endpoint matrix, hashes, and nullability are in §6–8. |
| B4 | Method/path/campaign/request scope plus exact-body input hash, replay, and conflict are in §8. |
| B5 | Base parse failures are non-mutating 400; semantic 422 sanitation, reason, `1/0`, and state update are in §6/8. |
| B6 | Terminal precedence and non-mutating Reveal that opens the original commitment are exact (§5/7–8). |
| B7 | Complete finite normalized vectors are in §9. |
| B8 | Public comparator and off-model/non-likelihood trigger are exact (§4). |
