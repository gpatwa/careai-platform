# Pharmacy Exception Policy

Version: 2026.06

This synthetic policy describes how a demo operations team handles pharmacy exception requests. It does not name real medications, real formularies, or real members.

## Exception Types

- Step requirement exception for synthetic therapy categories.
- Quantity threshold exception for synthetic dispensing limits.
- Coverage exception for non-preferred synthetic medication categories.
- Urgent access exception for time-sensitive operational review.

## Required Information

The request must include synthetic medication category, plan type, exception reason, prescriber attestation, and urgency. It must not include names, real medication histories, addresses, dates of birth, or other PHI/PII-like values.

## Decision Path

Routine exceptions are evaluated against synthetic policy criteria. Urgent exceptions are routed to a reviewer with pharmacy operations role access. Ambiguous cases receive a human-in-the-loop flag and require a second reviewer before final disposition.

## Monitoring

Exception decisions are monitored for volume spikes, role-based access violations, stale documentation, and repeated missing-information reason codes.
