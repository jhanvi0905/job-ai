"""Role taxonomy v2 (config/role_families.yaml): loading, id normalisation,
Stage-0 title matching and prompt compaction.

Used only by the multi-tenant product path. The legacy single-user pipeline
keeps config/roles.yaml (RF01–RF04); `normalize_family` maps those ids — and the
free-text tags resume parsing emits — onto v2 family ids.
"""
from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from collections.abc import Iterable
from functools import lru_cache

from jobai.core.config import CONFIG_DIR, load_yaml

TAXONOMY_FILE = "role_families.yaml"
OTHER = "other"

# Loose keyword -> family for free-text achievement tags ("customer support",
# "Marketing", "devops"). Exact ids and legacy_aliases are tried first.
_TAG_KEYWORDS: tuple[tuple[str, str], ...] = (
    (r"machine learning|\bml\b|\bai\b|llm|nlp|computer vision", "ai_ml"),
    (r"\bdata\b|analytic|\bbi\b|business intelligence|statistic", "data_analytics"),
    (r"software|backend|frontend|full.?stack|devops|\bsre\b|mobile|web dev", "software_engineering"),
    (r"product manage|product own", "product_management"),
    (r"\bit\b|infrastructure|network|security|sysadmin|system admin|help ?desk", "it_security"),
    (r"\bux\b|\bui\b|design", "design"),
    (r"marketing|brand|content|growth|communications|\bseo\b", "marketing"),
    (r"sales|account exec|business develop|account manage", "sales"),
    (r"customer|client success|support|service", "customer_success"),
    (r"operations|project manage|program manage|supply chain|logistics|admin", "operations"),
    (r"financ|accounting|accountant|payroll|audit|\btax\b|bookkeep", "finance"),
    (r"\bhr\b|human resources|recruit|talent|people (ops|operations|partner)|learning (and|&) development", "people_hr"),
)


@lru_cache(maxsize=1)
def load_taxonomy() -> dict:
    return load_yaml(TAXONOMY_FILE)


def family_ids() -> list[str]:
    return list(load_taxonomy()["families"])


def taxonomy_digest() -> str:
    """Changes whenever the taxonomy file changes (part of the verdict cache key)."""
    return hashlib.sha256((CONFIG_DIR / TAXONOMY_FILE).read_bytes()).hexdigest()[:16]


def normalize_family(value: str | None, *, fuzzy: bool = False) -> str | None:
    """A v2 family id for an id, legacy alias (RF02, data_engineering) or — with
    `fuzzy` — a free-text tag. None when nothing matches."""
    if not value:
        return None
    tax = load_taxonomy()
    raw = str(value).strip()
    key = raw.lower().replace("-", "_").replace(" ", "_")
    if key in tax["families"]:
        return key
    aliases = tax.get("legacy_aliases", {})
    if raw in aliases:
        return aliases[raw]
    if key in aliases:
        return aliases[key]
    if fuzzy:
        text = raw.lower().replace("_", " ")
        for pattern, family in _TAG_KEYWORDS:
            if re.search(pattern, text):
                return family
    return None


def normalize_families(values: Iterable[str], *, fuzzy: bool = False) -> list[str]:
    """Order-preserving, de-duplicated v2 ids; unknown values are dropped."""
    out: list[str] = []
    for v in values:
        fid = normalize_family(v, fuzzy=fuzzy)
        if fid and fid not in out:
            out.append(fid)
    return out


def adjacent_of(families: Iterable[str]) -> list[str]:
    """Union of the families' adjacent lists, minus the families themselves."""
    fams = load_taxonomy()["families"]
    chosen = list(families)
    out: list[str] = []
    for fid in chosen:
        for adj in fams[fid].get("adjacent", []):
            if adj not in chosen and adj not in out:
                out.append(adj)
    return out


def infer_families(tag_lists: Iterable[Iterable[str]], *, min_count: int = 2, max_families: int = 3) -> list[str]:
    """Families the user's evidence points at: each achievement votes once per
    family it is tagged with. A family needs `min_count` votes AND at least a
    quarter of the tagged achievements, so one stray tag never sets a search."""
    votes: Counter[str] = Counter()
    tagged = 0
    for tags in tag_lists:
        fams = set(normalize_families(tags, fuzzy=True))
        if fams:
            tagged += 1
            votes.update(fams)
    if not tagged:
        return []
    floor = max(min_count, math.ceil(0.25 * tagged))
    ranked = sorted(votes.items(), key=lambda kv: (-kv[1], family_ids().index(kv[0])))
    return [fid for fid, n in ranked if n >= floor][:max_families]


# --------------------------------------------------------------------------- Stage 0


def family_filter(families: Iterable[str]) -> dict:
    """The Stage-0 config for these families (stored in career_rules["family_filter"]).
    Plain data, so it is hashed into the verdict cache key."""
    tax = load_taxonomy()
    return {
        "families": {
            fid: {
                "title_signals": list(tax["families"][fid]["title_signals"]),
                "negative_signals": list(tax["families"][fid].get("negative_signals", [])),
            }
            for fid in families
        },
        "global_negative_signals": list(tax.get("global_negative_signals", [])),
    }


def _first_hit(patterns: Iterable[str], text: str) -> str | None:
    return next((p for p in patterns if re.search(p, text, re.I)), None)


def match_title(title: str, ff: dict) -> tuple[list[str], str | None]:
    """(families the title belongs to, reason if it belongs to none).

    A family matches when one of its title_signals hits and none of its
    negative_signals does. Reasons all start with "no title-family match" so
    they map onto the existing `no_signal` Stage-0 code."""
    global_hit = _first_hit(ff.get("global_negative_signals", []), title)
    if global_hit:
        return [], f"no title-family match: title looks like gig/task work ({global_hit})"
    matched: list[str] = []
    vetoed: list[str] = []
    for fid, fam in ff["families"].items():
        if _first_hit(fam["title_signals"], title):
            if _first_hit(fam["negative_signals"], title):
                vetoed.append(fid)
            else:
                matched.append(fid)
    if matched:
        return matched, None
    if vetoed:
        return [], f"no title-family match: title is excluded for {', '.join(vetoed)}"
    return [], f"no title-family match for the selected role families ({', '.join(ff['families'])})"


def title_families(title: str) -> list[str]:
    """Every taxonomy family the title matches (diagnostics and evaluation)."""
    return match_title(title, family_filter(family_ids()))[0]


def not_too_senior_phrases(families: Iterable[str]) -> list[str]:
    fams = load_taxonomy()["families"]
    out: list[str] = []
    for fid in families:
        out += [p for p in fams[fid].get("seniority", {}).get("not_too_senior", []) if p not in out]
    return out


def vocab_weights(families: Iterable[str]) -> dict[str, int]:
    fams = load_taxonomy()["families"]
    return {term: 1 for fid in families for term in fams[fid].get("vocab", [])}


# --------------------------------------------------------------------------- prompt


def compact_taxonomy(prompt_families: Iterable[str]) -> str:
    """One short line per family the model may choose from, plus `other`.
    Only the user's families and their adjacents are sent, never all twelve."""
    fams = load_taxonomy()["families"]
    lines = [f"{fid}: {fams[fid]['summary']}" for fid in prompt_families]
    lines.append(f"{OTHER}: none of the above")
    return "\n".join(lines)


def public_list() -> list[dict]:
    """[{id, label, adjacent}] for the API."""
    return [{"id": fid, "label": f["label"], "adjacent": list(f.get("adjacent", []))}
            for fid, f in load_taxonomy()["families"].items()]
