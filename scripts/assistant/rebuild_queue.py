#!/usr/bin/env python3
"""Rebuild the Notion review queue under the current rules.

Re-evaluates every automation-created, still-untouched page ("Source =
Automation" AND "Status = Discovered") from scratch through the same pipeline
the daily run uses, then:

  KEEP/UPGRADE  pages whose job passes -> properties refreshed (Priority, Fit
                Band, Seniority, evidence, gaps, why-it-fits...)
  ADD           newly-passing jobs not yet in Notion
  TRASH         everything else: fails Stage 0 / AI, duplicate of a kept role,
                or no longer posted. Goes to Notion's trash (recoverable for
                30 days) — never a hard delete.

Pages you've touched (any other Status) or added yourself are never read as
candidates and never modified.

Two phases so the AI is only paid for once:
  python scripts/assistant/rebuild_queue.py            # plan: evaluates, writes data/rebuild_plan.json, changes nothing
  python scripts/assistant/rebuild_queue.py --apply    # executes that saved plan
"""
import json
import sys

from dotenv import load_dotenv  # noqa: E402

load_dotenv()


from jobai.assistant.integrations.job_record import base_properties, evaluation_properties  # noqa: E402
from jobai.assistant.integrations.notion import NotionClient  # noqa: E402
from jobai.assistant.workflows.process_job import (  # noqa: E402
    DedupIndex,
    build_sources,
    evaluate,
    fetch_all,
    stage0_filter_and_dedupe,
)
from jobai.core.config import (  # noqa: E402
    load_career_rules,
    load_models,  # noqa: E402
    load_roles,
)
from jobai.core.ledger.db import Ledger  # noqa: E402
from jobai.core.paths import DATA_DIR  # noqa: E402
from jobai.core.telemetry.logging import RunSummary, configure_logging  # noqa: E402
from jobai.engine.ai.provider import LLMProvider  # noqa: E402
from jobai.engine.jobs.decisions import DecisionCache  # noqa: E402

PLAN_PATH = DATA_DIR / "rebuild_plan.json"


def _label(page: dict) -> str:
    return f"{page.get('Role')} @ {page.get('Company')}"


def plan() -> None:
    notion = NotionClient()
    career_rules, roles = load_career_rules(), load_roles()
    summary = RunSummary()

    pages = notion.list_all_pages()
    managed = [p for p in pages if p.get("Source") == "Automation" and p.get("Status") == "Discovered"]
    protected = [p for p in pages if p not in managed]
    print(f"{len(pages)} pages: {len(managed)} untouched automation pages to rebuild, "
          f"{len(protected)} protected (yours / in progress)")

    managed_by_fp: dict[str, list[dict]] = {}
    for p in managed:
        managed_by_fp.setdefault(p.get("Job Fingerprint") or "", []).append(p)
    for group in managed_by_fp.values():
        group.sort(key=lambda p: p.get("created_time") or "")

    # Only protected pages block duplicates; managed pages are being re-judged.
    ledger = Ledger()
    decisions = DecisionCache(ledger, persist=False)  # reads remembered rejections, never writes
    candidates = stage0_filter_and_dedupe(
        fetch_all(build_sources(), summary), DedupIndex(protected), decisions, career_rules, roles, summary
    )
    print(f"{summary.fetched} fetched -> {len(candidates)} pass Stage 0 + dedup; evaluating with AI...")
    run_id = ledger.start_run("rebuild-plan", budget_usd=load_models().get("budget", {}).get("per_run_usd"))
    try:
        approved = evaluate(candidates, decisions, career_rules, summary, LLMProvider(ledger, run_id))
        ledger.finish_run(run_id, "degraded" if summary.ai_errors else "ok")
    except Exception as exc:
        ledger.finish_run(run_id, "failed", f"{type(exc).__name__}: {exc}"[:300])
        raise

    keep_page_ids: set[str] = set()
    writes = []
    for cand in approved:
        fp = cand.job.job_fingerprint
        existing = (managed_by_fp.get(fp) or [None])[0]
        properties = {
            **base_properties(cand.job, is_new=existing is None),
            **evaluation_properties(cand.classification, cand.match),
        }
        if existing:
            keep_page_ids.add(existing["notion_page_id"])
        writes.append(
            {
                "action": "update" if existing else "create",
                "page_id": existing["notion_page_id"] if existing else None,
                "label": f"{cand.job.title} @ {cand.job.company_name}",
                "properties": properties,
            }
        )

    trash = [
        {"page_id": p["notion_page_id"], "label": _label(p)}
        for p in managed
        if p["notion_page_id"] not in keep_page_ids
    ]
    cost = ledger.spent_in_run(run_id)
    ledger.close()

    PLAN_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLAN_PATH.write_text(json.dumps({"writes": writes, "trash": trash, "rejections": summary.rejections}, indent=2), encoding="utf-8")

    updates = [w for w in writes if w["action"] == "update"]
    creates = [w for w in writes if w["action"] == "create"]
    print(f"\n=== PLAN (nothing changed yet; AI cost ${cost:.4f}) ===")
    print(f"KEEP + upgrade: {len(updates)}   ADD new: {len(creates)}   TRASH: {len(trash)}\n")
    print("Approved queue:")
    for a in summary.approvals:
        print("  +", a[:200])
    print(f"\nAI/filter rejections sample ({len(summary.rejections)} AI rejections):")
    for r in summary.rejections[:25]:
        print("  -", r[:170])
    print(f"\nTo trash ({len(trash)}):")
    for t in trash[:60]:
        print("  x", t["label"][:120])
    if len(trash) > 60:
        print(f"  ... and {len(trash) - 60} more")
    print(f"\nPlan saved to {PLAN_PATH}. Review, then: python scripts/assistant/rebuild_queue.py --apply")


def apply() -> None:
    if not PLAN_PATH.exists():
        sys.exit("No plan found. Run without --apply first.")
    saved = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    notion = NotionClient()
    done = {"updated": 0, "created": 0, "trashed": 0, "errors": 0}

    for w in saved["writes"]:
        try:
            if w["action"] == "update":
                notion.update_job_page(w["page_id"], w["properties"])
                done["updated"] += 1
            else:
                notion.create_job_page(w["properties"])
                done["created"] += 1
        except Exception as exc:  # noqa: BLE001
            done["errors"] += 1
            print(f"write failed for {w['label']}: {exc}")
    if done["errors"]:
        print(f"{done['errors']} write(s) failed — NOT trashing anything. Fix and re-run --apply.")
        print(done)
        return
    for t in saved["trash"]:
        try:
            notion.archive_page(t["page_id"])
            done["trashed"] += 1
        except Exception as exc:  # noqa: BLE001
            done["errors"] += 1
            print(f"trash failed for {t['label']}: {exc}")
    print(done)
    PLAN_PATH.rename(PLAN_PATH.with_suffix(".applied.json"))


if __name__ == "__main__":
    configure_logging()
    apply() if "--apply" in sys.argv else plan()
