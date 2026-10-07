"""JobRecord mapping (PRD §29): pipeline objects -> Notion Job Pipeline
properties. One place decides what every column means and what values are
legal, so the database stops filling up with inconsistent junk.
"""
from __future__ import annotations

from datetime import date

from jobai.core.config import load_career_rules
from jobai.engine.ai.role_labels import ROLE_FAMILY_LABELS
from jobai.engine.jobs.schemas import JobClassification, JobMatch, NormalizedJob

# Fixed vocabulary — the classifier is told to emit exactly these keys.
SENIORITY_LABELS = {
    "junior": "Junior",
    "mid": "Mid",
    "senior": "Senior",
    "lead": "Lead",
    "staff_plus": "Staff+",
    "manager": "Manager",
    "director_plus": "Director+",
}

# Where the posting actually came from. Himalayas is an aggregator, not the
# company's own careers page — labelling it "Company Careers" (as before) was wrong.
SOURCE_CHANNELS = {
    "greenhouse": "Company Careers",
    "lever": "Company Careers",
    "ashby": "Company Careers",
    "smartrecruiters": "Company Careers",
    "himalayas": "Other",
}

_MAX_LIST_CHARS = 1800  # Notion rich_text blocks cap at 2000


def location_display(job: NormalizedJob) -> str | None:
    """Short, scannable location. Himalayas hands back a raw country list
    ('Armenia, Australia, Canada, India, ...') that's unreadable in a column."""
    loc = job.location
    if not loc:
        return None
    if loc == "Worldwide":
        return "Worldwide (remote)"
    if job.source == "himalayas":
        home = load_career_rules()["location"]["candidate_country"]
        countries = [c.strip() for c in loc.split(",") if c.strip()]
        if home in countries:
            return f"{home} (remote)" if len(countries) == 1 else f"{home} + {len(countries) - 1} more (remote)"
    return loc


def _join(items: list[str]) -> str | None:
    text = "; ".join(i for i in items if i)
    return text[:_MAX_LIST_CHARS] or None


def base_properties(job: NormalizedJob, is_new: bool) -> dict:
    today = date.today().isoformat()
    props = {
        "Opportunity": f"{job.title} — {job.company_name}",
        "Company": job.company_name,
        "Role": job.title,
        "Location": location_display(job),
        "Job URL": job.job_url or None,
        "Source": "Automation",
        "Source Channel": SOURCE_CHANNELS.get(job.source, "Other"),
        "Work Mode": job.workplace_type,
        "External Key": f"{job.source}:{job.external_job_id}",
        "Job Fingerprint": job.job_fingerprint,
        "JD Hash": job.description_hash,
        "Last Checked": today,
        "Date Posted": job.posted_at.date().isoformat() if job.posted_at else None,
    }
    if is_new:
        # Never reset what the user may have changed on an existing page.
        props["Status"] = "Discovered"
        props["Found Date"] = today
    return props


def evaluation_properties(
    classification: JobClassification | None, match: JobMatch | None
) -> dict:
    """The AI verdict, written so every populated column means something."""
    exp = load_career_rules()["experience"]
    props: dict = {}

    if classification is not None:
        props["Role Family"] = ROLE_FAMILY_LABELS.get(classification.role_family)
        props["Seniority"] = SENIORITY_LABELS.get(classification.seniority or "")

    gaps: list[str] = []
    if classification is not None and classification.min_years_required is not None:
        if classification.min_years_required > exp["total_years"]:
            gaps.append(
                f"Asks {classification.min_years_required}+ yrs experience (you have ~{exp['total_years']})"
            )

    if match is not None:
        props["Fit Band"] = match.fit_band.capitalize()
        props["Priority"] = match.priority
        props["Matched Achievements"] = ", ".join(a.id for a in match.matched_achievements) or None
        props["Strong Evidence"] = _join(match.strong_evidence)
        props["Partial Evidence"] = _join(match.partial_evidence)
        props["Why It Fits"] = match.reason
        gaps.extend(match.gaps)
        props["Last Analysed"] = date.today().isoformat()
    elif classification is not None and classification.why:
        props["Why It Fits"] = classification.why

    props["Gaps"] = _join(gaps)
    return props
