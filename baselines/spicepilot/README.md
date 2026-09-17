# SPICEPilot Prompt Adapter

This baseline addresses the reviewer-requested SPICEPilot comparison with the
smallest faithful shared-task experiment. The upstream repository publishes its
Prompt Pilot and PySpice outputs but not a reusable API runner. Consequently,
the harness pins the upstream source and labels this method as adapted.

Frozen behavior:

- V4 Flash only, 10 tasks x 3 repeats;
- upstream `Pilot_prompt.md` retained;
- evaluator targets and EDA Last planning state hidden;
- at most three independent PySpice generations;
- sandboxed raw-deck export and unchanged common evaluation;
- all failures, usage and artifacts retained.
