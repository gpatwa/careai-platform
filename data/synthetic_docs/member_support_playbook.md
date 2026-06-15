# Member Support Playbook

Version: 2026.06

This synthetic playbook helps demonstrate retrieval-augmented generation for member support operations. It contains fictional workflows and excludes real member data.

## Support Principles

Support agents should answer with empathy, plain language, and operational clarity. If the question requests clinical advice, legal interpretation, or account-specific details, the agent should decline and route to the appropriate human team.

## Common Scenarios

### Prior Authorization Status

Explain that routine synthetic prior authorization requests target a two-business-day review window, while expedited requests target one business day. Do not invent approval status if the source system does not provide it.

### Claims Review Status

Explain whether a synthetic claim is clean, pending data-quality review, under duplicate review, or escalated for manual review. Use only safe reason codes and avoid raw claim details.

### Pharmacy Exception

Describe the exception intake steps, including required synthetic medication category, plan type, prescriber attestation, and reason for exception. Do not mention real drug names or patient history.

## Escalation

Escalate when a request is urgent, ambiguous, safety-sensitive, or outside the agent role. Escalation notes must contain only synthetic identifiers and safe operational metadata.
