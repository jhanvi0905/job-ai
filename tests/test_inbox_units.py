"""Rules, matcher and status policy: pure functions, no I/O."""
import pytest

from src.inbox import policy, rules
from src.inbox.matcher import company_key, match_email, role_score


# ------------------------------------------------------------------ rules
@pytest.mark.parametrize("subject,snippet,expected", [
    ("Thank you for applying to Acme", "We received your application", "confirmation"),
    ("Your application to Acme", "Unfortunately, we will not be moving forward", "rejection"),
    ("Update on your application", "Thank you for applying. Unfortunately we decided to move forward with other candidates", "rejection"),
    ("Next steps", "We'd like to schedule a call with you", "interview_request"),
    ("Coding challenge for ML Engineer", "Please complete the take-home", "assessment"),
    ("Offer letter", "We are pleased to offer you the role", "offer"),
])
def test_rules_classify_the_common_templates(subject, snippet, expected):
    klass, conf = rules.classify_by_rules(subject, snippet)
    assert klass == expected and conf >= 0.85


def test_no_pattern_or_conflicting_patterns_defer_to_the_model():
    assert rules.classify_by_rules("Hello", "Just checking in") == (None, 0.0)
    assert rules.classify_by_rules("Interview and coding challenge", "schedule a call and take-home") == (None, 0.0)


def test_prefilter_costs_nothing_and_only_lets_job_mail_through():
    assert not rules.looks_like_application_mail("news.example.com", "Weekly digest", "10 tips for your career")
    assert rules.looks_like_application_mail("us.greenhouse-mail.io", "Hello", "anything")  # ATS sender
    assert rules.looks_like_application_mail("acme.com", "Interview invitation", "")
    assert rules.sender_is_ats("hire.lever.co") and not rules.sender_is_ats("notlever.co.evil.com")


# ---------------------------------------------------------------- matcher
def page(company, role, status="Applied", fp=None):
    return {"Company": company, "Role": role, "Status": status, "Job Fingerprint": fp or f"fp-{company}-{role}", "notion_page_id": f"p-{role}"}


def test_company_key_strips_legal_suffixes_and_punctuation():
    assert company_key("Featherless AI, Inc.") == "featherless ai"
    assert company_key("Cummins Ltd") == "cummins"


def test_single_company_match_uses_sender_name_subject_or_domain():
    pages = [page("Featherless AI", "ML Engineer"), page("Cummins", "Data Engineer")]
    assert match_email(pages, "Featherless AI", "greenhouse-mail.io", "Thanks", "").page["Company"] == "Featherless AI"
    assert match_email(pages, "Recruiting", "cummins.com", "Hello", "").page["Company"] == "Cummins"
    assert match_email(pages, "No-reply", "greenhouse.io", "Your application to Cummins", "").method == "company"


def test_unrelated_mail_and_partial_word_collisions_do_not_match():
    pages = [page("Scale", "ML Engineer"), page("Ramp", "Engineer")]
    assert match_email(pages, "Newsletter", "example.com", "Escalate your career", "trampoline sale").method == "none"


def test_pages_without_a_fingerprint_are_never_matched():
    p = page("Acme", "Engineer")
    p["Job Fingerprint"] = None
    assert match_email([p], "Acme", "acme.com", "Hi", "").page is None


def test_same_company_many_roles_is_resolved_by_role_text_else_refused():
    pages = [page("Featherless AI", "Machine Learning Engineer — Distillation", "Discovered"),
             page("Featherless AI", "Machine Learning Engineer — Training Optimization", "Discovered")]
    hit = match_email(pages, "Featherless AI", "x.io", "Application for Machine Learning Engineer Distillation", "")
    assert hit.method == "company+role" and "Distillation" in hit.page["Role"]
    vague = match_email(pages, "Featherless AI", "x.io", "Thanks for applying", "")
    assert vague.page is None and vague.method == "ambiguous" and vague.candidates == 2


def test_status_breaks_a_tie_only_when_exactly_one_page_is_engaged():
    a, b = page("Acme", "Role One", "Applied"), page("Acme", "Role Two", "Discovered")
    assert match_email([a, b], "Acme", "acme.com", "Update", "").method == "company+status"
    c = page("Acme", "Role Three", "Interview")
    assert match_email([a, b, c], "Acme", "acme.com", "Update", "").method == "ambiguous"


def test_role_score_ignores_seniority_noise():
    assert role_score("Senior AI Engineer", "Your AI Engineer application", "") == 1.0


# ----------------------------------------------------------------- policy
CASES = [
    # current, class, text, outcome, new
    ("Discovered", "confirmation", "", "update", "Applied"),
    ("Shortlisted", "confirmation", "", "update", "Applied"),
    ("Applied", "confirmation", "", "no_change", None),
    ("Interview", "confirmation", "", "no_change", None),
    ("Applied", "interview_request", "quick intro call", "update", "Recruiter Screen"),
    ("Applied", "interview_request", "interview with the team", "update", "Interview"),
    ("Interview", "interview_request", "chat with recruiter", "no_change", None),  # never backwards
    ("Recruiter Screen", "assessment", "", "no_change", None),                     # same rank
    ("Applied", "assessment", "", "update", "Assessment"),
    ("Interview", "assessment", "", "no_change", None),
    ("Final", "offer", "", "update", "Offer"),
    ("Applied", "rejection", "", "update", "Rejected"),
    ("Discovered", "rejection", "", "update", "Rejected"),
    ("Interview", "rejection", "", "update", "Rejected"),
    ("Rejected", "rejection", "", "no_change", None),
    ("Offer", "rejection", "", "blocked_protected", None),       # a rescinded offer is for a human
    ("Rejected", "interview_request", "", "blocked_protected", None),
    ("Withdrawn", "confirmation", "", "blocked_protected", None),
    ("No Response", "interview_request", "", "update", "Interview"),  # a late reply revives it
    (None, "confirmation", "", "update", "Applied"),
    ("Applied", "other", "", "other_class", None),
]


@pytest.mark.parametrize("current,klass,text,outcome,new", CASES)
def test_status_policy_table(current, klass, text, outcome, new):
    assert policy.decide(current, klass, text) == (outcome, new)


def test_every_notion_status_has_a_rank_or_is_protected():
    from tests.test_feedback import LIVE_STATUSES
    assert set(policy.RANK) | policy.PROTECTED == LIVE_STATUSES


# ------------------------------------------------------------- role guard
from src.inbox.matcher import role_conflict  # noqa: E402


@pytest.mark.parametrize("role,subject,snippet,conflict", [
    # the real GitLab case: rejection names AI Engineer, the page is the NLP role
    ("Senior Software Engineer, NLP", "Information about your application to GitLab - AI Engineer", "the AI Engineer role", True),
    # the real FourKites case: same role -> fine
    ("Senior Data Scientist", "Follow up from FourKites", "apply for the Senior Data Scientist position", False),
    ("Machine Learning Engineer", "Update", "We are not moving forward", False),                  # no role named -> no conflict
    ("Data Engineer", "Interview at Cummins", "Cummins would like to schedule a call", False),   # 'Cummins' is not a title word
    ("Data Engineer", "Update", "your Backend Developer application", True),
])
def test_role_conflict(role, subject, snippet, conflict):
    company = "GitLab" if "GitLab" in subject else "FourKites" if "FourKites" in subject else "Cummins"
    assert role_conflict(role, company, subject, snippet) is conflict
