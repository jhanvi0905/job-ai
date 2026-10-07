"""Shared between capabilities.py and process_job.py — kept as its own module
so neither has to import the other (avoids a circular import) just to reuse
this one mapping."""

# Must match the Notion "Role Family" select options exactly (see the schema
# diff applied to the live Job Pipeline database) — not derived from
# roles.yaml's free-text family names, which don't share that exact format.
ROLE_FAMILY_LABELS = {
    "RF01": "RF01 - Senior/Lead AI Engineer",
    "RF02": "RF02 - Senior ML/Applied AI Engineer",
    "RF03": "RF03 - Senior Data/ML Systems Engineer",
    "RF04": "RF04 - Lead/Early AI Engineer (Startup)",
}
