# Direct LLM baseline

This baseline receives only the frozen user requirement and the shared output
contract. Each trial may make at most three independent generation calls. It
does not receive a planner output, retrieved examples, evaluator targets,
benchmark-family labels, simulator feedback, or prior candidate responses.

All candidates are evaluated by the same shared SPICE evaluator used for the
other methods. The trial succeeds if any of its independent candidates passes;
all failed, duplicate, timed-out, and non-finite attempts remain recorded.
