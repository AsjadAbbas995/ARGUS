"""ARGUS AI layer: hybrid local/cloud router, structured-output validator, deterministic
Phase-6 model demos, and Phase-7 typed-context agents.

Phase-6 scope ("10_IMPLEMENTATION_PLAN.md" §Phase 6): the AI Router selects local vs. cloud per
the documented criteria in "07_AI_AGENTS.md" §AI Router (task complexity, context size, expected
reasoning requirements, cost, latency, and local-model availability, plus a forced
``local``/``cloud``/``hybrid`` mode); the Validator enforces the Common Output Contract in
"07_AI_AGENTS.md" §Output Schemas and the structured-output schema in "12_AI_PROMPTS.md" —
off-schema output (missing evidence, invalid truth labels, unreferenced claims) is **rejected**,
never silently accepted.

Phase-7 scope ("10_IMPLEMENTATION_PLAN.md" §Phase 7): the agents in ``ai/*_agent.py``
(``recon_agent``/``api_agent``/``js_agent``/``authz_agent``/``logic_agent``/``triage_agent``/
``hypothesis_agent``) are pure, deterministic consumers of the typed records in ``ai/context.py``.
Each emits exactly one Common Output Contract proposal (or ``None`` when the documented
no-proposal condition holds), citing only caller-supplied evidence, never self-validating, and
never proposing out-of-scope targets. Every proposal passes the Phase-6 validator; off-contract
proposals are rejected at construction (``ai/contract.py``).

No agent has shell/network access; every output is a proposal.
"""
