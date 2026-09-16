"""ARGUS AI layer: hybrid local/cloud router, structured-output validator, and deterministic
Phase-6 model demos.

Phase-6 scope ("10_IMPLEMENTATION_PLAN.md" §Phase 6): the AI Router selects local vs. cloud per
the documented criteria in "07_AI_AGENTS.md" §AI Router (task complexity, context size, expected
reasoning requirements, cost, latency, and local-model availability, plus a forced
``local``/``cloud``/``hybrid`` mode); the Validator enforces the Common Output Contract in
"07_AI_AGENTS.md" §Output Schemas and the structured-output schema in "12_AI_PROMPTS.md" —
off-schema output (missing evidence, invalid truth labels, unreferenced claims) is **rejected**,
never silently accepted. No agent has shell/network access; every output is a proposal.
"""
