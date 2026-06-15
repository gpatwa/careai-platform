# Prior Authorization Policy

Version: 2026.06

This synthetic policy describes how a healthcare operations team reviews prior authorization requests for non-emergency services. It is for platform demonstration only and does not describe real patient data, payer rules, or clinical advice.

## Purpose

Prior authorization review confirms that a requested service has enough supporting information for operational approval. Reviewers should consider the requested service category, synthetic plan type, documented utilization pattern, and whether the request needs human review.

## Intake Requirements

- Request category and synthetic member segment.
- Ordering provider attestation that the request is complete.
- Service urgency: routine, expedited, or emergency.
- Supporting documentation summary without raw PHI or PII-like values.

## Review Workflow

Routine requests are reviewed within the demo service-level objective of two business days. Expedited requests are reviewed within one business day. Emergency requests should bypass prior authorization review and move directly to the emergency exception workflow.

If documentation is incomplete, the reviewer records a synthetic missing-document reason code and routes the case to member support. If the request involves high operational impact, the reviewer flags it for a human-in-the-loop decision.

## Governance Notes

Every decision must include a correlation identifier, reviewer role, decision timestamp, and safe reason code. Logs must not include names, member identifiers, addresses, dates of birth, or real clinical details.
