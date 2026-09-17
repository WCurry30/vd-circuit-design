# Baseline Adaptation Boundary

Shared-task adaptation aligns only the input, output format, and evaluator. It does not add capabilities absent from the original baseline.

Allowed adaptations:

- Insert the original natural-language requirement from `synthesis_10` into the method's own prompt template.
- Require the shared `IN`, `OUT`, and `0` nodes. Load-current tasks require the method to generate its own series zero-volt sensing source, `VLOAD`.
- Execute AnalogCoder-generated PySpice code in an isolated subprocess and export only `str(circuit)` as raw SPICE.
- Remove a candidate's `.control` and analysis commands before the shared evaluator adds its own analysis commands.
- Retain the prompt, raw response, raw deck, evaluated deck, simulator log, token usage, and failure stage.

Disallowed adaptations:

- Add or modify missing AC excitation, `VLOAD`, components, nodes, models, or parameters.
- Give EDA Last planning, retrieval, expert routing, or its component library to Direct LLM or AnalogCoder.
- Put numerical answers from `targets`, `expert_family`, or the shared evaluator into a generation prompt.
- Manually repair failed netlists, selectively rerun examples, replace tasks, or retain only successful outcomes.
- Present the AnalogCoder shared adapter as an unmodified reproduction of its official benchmark.

Consequently, missing `IN`/`OUT`, AC excitation, or `VLOAD` remains a genuine failure for that method; the runner does not fill in missing elements.

AnalogCoder repair handles only native Python code that cannot be parsed or executed. After it exports raw SPICE successfully, shared evaluation is terminal: metric failures, missing AC excitation, missing nodes, or missing `VLOAD` are not sent back to the model for circuit repair. Doing so would introduce an additional capability absent from the baseline.
