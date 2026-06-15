# Claims Review Policy

Version: 2026.06

This synthetic policy defines claims review steps for the careai-platform demo. It uses invented operational categories and should never be treated as payer guidance, legal advice, or clinical policy.

## Review Goals

Claims review should identify data-quality issues, duplicate submission patterns, missing synthetic service codes, and cases that require manual review. The process supports transparent audit trails and reproducible decisions.

## Triage Categories

- Clean claim: required synthetic fields are complete and no risk signals are present.
- Data-quality hold: required synthetic fields are missing, stale, or inconsistent.
- Duplicate review: a claim resembles another synthetic claim by service window and operational category.
- Manual review: the claim has high cost impact, unusual utilization, or policy ambiguity.

## Reviewer Actions

Reviewers assign a safe reason code and decision status. They may approve, pend for additional synthetic documentation, deny for missing operational requirements, or escalate to a supervisor role.

## Audit Requirements

Each review event must capture actor role, action, target type, target identifier, correlation ID, and non-sensitive metadata. The audit record should support lineage from claim intake through final disposition without storing raw PHI or PII-like values.
