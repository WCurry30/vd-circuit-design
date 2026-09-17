# Third-party sources

`LOCK.json` pins the repositories and commits used by the reproducibility scripts:

- EDA Last base framework: `WCurry30/vd-circuit-design`.
- AnalogCoder: adapted to the shared task and evaluator; this is not an unmodified reproduction of its benchmark.
- SPICEPilot: its pinned Prompt Pilot is used as an adapted prompt baseline; the complete official system is not claimed.

External repositories are installed under ignored `.runtime/` and are not vendored here.
