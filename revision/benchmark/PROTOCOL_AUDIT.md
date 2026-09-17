# Unified20 protocol audit

Critical OP gap demonstrated by pilot-v8: a saturated BJT (Vce=0.07325547 V)
meets the old scalar gain tolerance and topology predicate. Dataset v4 and
unified_benchmark.py now require a reliably converged forward-active operating
point for eda_007/203/204, including numerically passing candidates. The archived
v8 result remains a historical observation under its old protocol. All eligible
archives still need consistent final-version replay before reuse.

CE follow-up: collector feed, base-divider arms and resistive emitter return are
now checked on each matched CE stage. Split emitter resistors are supported;
direct, split-resistor and capacitor-chain rail bypass are rejected for the
unbypassed task. Both stage bases require bias in the two-stage case. All 34 tests
and the complete reference/negative gate pass. General RC impedance-equivalence
and buffered bias networks remain outside the validated recognizer scope.

Status: development; not ready to freeze the formal comparison.
2026-09-10 reconciliation: current `test_amplifier_path.py` passes six tests.
The original checklist's eda_005 dual-rail item is implemented, including an
alternate-voltage/reversed-source equivalence test. The eda_209 reference-divider
item is implemented with same-amplifier binding, disconnected/capacitive-only
negative cases, and the v5 public requirement flag. `testbench_connections`
also checks op-amp VCC/VEE pin binding for explicitly conditioned dual rails.
These closures do not establish powered-rail validity for all other tasks.
Sources: `synthesis_20.json`, `development/benchmark_structure.py`,
`development/revision_spec.py`, and the executed development archives.
No new-task model responses were inspected for this audit.

Implemented since initial audit: named RLOAD conditions now require a unique
top-level load across the measured output and ground. Named VDD/VCC/VEE supply
conditions require a unique top-level source with the public rail and polarity.
Detached dummy loads/sources and nested substitutes are rejected. This closes
the named-element placement gap for the currently declared supply/load conditions;
it does not add missing supply conditions, verify all unconditioned rails, or
complete the remaining topology/bias checks. Twenty-nine tests and the complete
20-reference/20-negative gate pass (`qualification-testbench-connections-v1`).

Supply-condition update: dataset version `unified20-development-v3` explicitly
sets VCC=12 V and VEE=-12 V for every check of eda_202, eda_205 and eda_206.
Public acceptance-test text is regenerated from the same structured conditions.
All twenty reference/negative pairs pass (`qualification-dual-supply-v3`).
These tasks remain unexposed to model generation. The named-placement checks
above validate the corresponding source terminals. Other audit items remain open.

Amplifier-path update: non-inverting stage predicates now require that the same
amplifier whose input coupling and feedback match has a passive signal path to
measured OUT. Single-supply audio requires output AC coupling from that amplifier
and a VCC/ground divider with a resistive connection to its positive input.
Tests reject detached amplifiers, broken output coupling, missing divider arms
and disconnected input bias. Thirty-one tests and the complete reference/negative
gate pass (`qualification-amplifier-path-v1`). CE bias/indirect-bypass and the
other explicitly open audit items still require work.

## Task coverage

Single-opamp update: active_rc now requires exactly one recognized op-amp,
matching eda_027's explicit request. Tests reject both detached and output-driven
extra op-amps while retaining the original feedback witness. All 55 local tests
pass and all twenty reference/negative pairs qualify in
`evidence/qualification-single-opamp-v1`. This closes the stage-count item only;
power-rail and bias validation remain separate audit items.

The table below is the original audit checklist, not a current list of open
defects. Updates above close the named-element placement issue, explicit dual
12 V conditions for 202/205/206, output binding for 006, same-amplifier virtual
bias for 024, and the bounded CE bias/bypass cases for 007/203/204. Remaining
equivalent-network limitations and other rows still require assessment.

| Task | Request/check comparison | Required action before freeze |
| --- | --- | --- |
| eda_005 | Inverting feedback and grounded positive input checked; requested dual supplies not checked here. | Validate actual dual rails. |
| eda_006 | Input coupling and feedback divider checked; amplifier output need not be tied to measured OUT by this predicate. | Bind the detected amplifier to measured output. |
| eda_007 | Coupling and direct emitter resistor checked; collector resistor and bias divider not checked; split emitter networks rejected. | Check the requested CE circuit with resistive emitter return and bias network. |
| eda_008 | Requires non-inverting topology although request only names an op-amp gain stage; microphone bias tied specifically to VCC. | Decide and publish admissible stage polarity and bias interface, without assuming a hidden topology. |
| eda_009 | Series R/shunt C checks match explicit request; passive check permits additional passive elements. | State whether component count is exact or role based. |
| eda_010 | RC input and unity buffer match request. | Verify output and rail validity in shared electrical checks. |
| eda_016 | Direct Zener and unity-buffered reference supported after correction. | Publish this admissible output-path rule and retain versioned replay. |
| eda_024 | Input/output coupling, non-inverting feedback and single supply checked; virtual-ground divider not checked. | Bind all features to the same amplifier and verify bias divider. |
| eda_027 | Parallel RC feedback matches named roles; non-inverting bias and one-op-amp count not checked. | Audit polarity/bias and explicit single-stage count. |
| eda_037 | Series LED load now supported; low-side topology assumed; reference/supply validity incomplete. | Publish low-side interface explicitly; verify powered reference and series sensing. |
| eda_201 | Required supplies and load altered by element name; input/gain topology checked. | Confirm named sources/load connect to intended rails/output, not detached dummy elements. |
| eda_202 | Difference network and common-mode test present; requested dual 12 V supplies not imposed in conditions. | Add explicit supply conditions and validate their connections. |
| eda_203 | Supply/load altered; unbypassed check only excludes a direct emitter-ground capacitor. | Detect indirect AC bypass; require collector and base bias paths. |
| eda_204 | Coupled CE pair checked; independent bias dividers not checked. | Validate each stage's bias and output loading; support valid emitter networks. |
| eda_205 | Two buffered sections and low-frequency unity gain checked; dual 12 V supplies not imposed. | Add supply conditions and verify section count/connection. |
| eda_206 | Sallen-Key topology, cutoff and two gain samples checked; dual 12 V supplies not imposed. | Add supply conditions; sampled response alone is not a full Butterworth-shape proof. |
| eda_207 | Two supply cases and load implemented; direct shunt path required. | Publish direct-shunt scope explicitly; verify testbench element placement. |
| eda_208 | NPN follower and two load conditions match request. | Verify supply/load placement and preserved transistor after cleanup. |
| eda_209 | 5 V condition and feedback loop checked; resistor-divider reference not checked. | Check requested divider drives the positive input with a valid DC path. |
| eda_210 | Two supply cases and BJT feedback loop checked. | Validate base feed and probe polarity/output binding. |

## Shared issues and next sequence

1. Define the public acceptance scope once for all methods. Keep requirements,
   interfaces, conditions and topology rules consistent. Distinguish explicit
   design constraints from descriptive component roles. Do not broaden or narrow
   a rule solely because a method passed or failed.
2. Fix electrical-testbench integrity: specified sources and loads must connect
   to the intended nodes; do not rely on element names alone. Require genuine
   powered supplies rather than interpreting model-internal sources as external
   power. Use fixed supply conditions where the request specifies voltage.
3. Bind topology checks to the evaluated signal/output path. Add adversarial
   cases for dummy subcircuits, detached loads, bypass paths and missing bias.
   Existing twenty negative fixtures are useful but do not cover these defects.
4. Resolve documented overconstraints with equivalent valid circuits. Continue
   preserving old evaluator outcomes; apply each revised evaluator to all
   eligible method archives. Replays are not new trials and cannot recover
   counterfactual later generations under changed feedback.
5. Only then freeze code, public dataset, evaluator, provider settings, budgets,
   repeats, run order and formal matrix. Run all prespecified trials, including
   unsuccessful trials. Compare Full, baselines and ablations under that protocol.

The dataset has twenty qualified reference circuits, not twenty demonstrated
Full successes. The broader planning-only corpus is a different evaluation
scope and must not be pooled into end-to-end success denominators. Development
pilots cannot establish SOTA or guarantee positive ablations.
