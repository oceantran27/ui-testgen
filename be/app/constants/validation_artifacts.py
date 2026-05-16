"""Artifact type strings for scenario validation / evidence audit reports.

Agent 7 persists `SCENARIO_EVIDENCE_AUDIT_REPORT`; older runs may use legacy name.
"""

SCENARIO_EVIDENCE_AUDIT_REPORT_ARTIFACT = "scenario_evidence_audit_report"
LEGACY_SCENARIO_VALIDATION_REPORT_ARTIFACT = "scenario_validation_report"

SCENARIO_VALIDATION_ARTIFACT_TYPES: tuple[str, ...] = (
    SCENARIO_EVIDENCE_AUDIT_REPORT_ARTIFACT,
    LEGACY_SCENARIO_VALIDATION_REPORT_ARTIFACT,
)
