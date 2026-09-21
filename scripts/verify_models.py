#!/usr/bin/env python3
"""Gate 1 equivalent: before Phase 2/3 spend a single real token in the
pipeline, confirm the configured AI/ML API models actually exist and return
well-formed structured JSON. Run this manually after editing config/models.yaml
and before wiring classifier.py/matcher.py into the workflow.

Usage: python scripts/verify_models.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from src.ai.provider import LLMProvider  # noqa: E402
from src.config import load_models  # noqa: E402


def main() -> int:
    routing = load_models()["routing"]
    provider = LLMProvider()
    if not provider.api_key:
        print("AIMLAPI_KEY is not set (check .env) — nothing to verify.")
        return 1

    ok = True
    for stage, cfg in routing.items():
        model = cfg["model"]
        print(f"[{stage}] model={model} ...", end=" ")
        try:
            result = provider._chat(  # noqa: SLF001
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": 'Reply with exactly this JSON: {"ok": true}',
                    }
                ],
                max_tokens=20,
                temperature=0,
                workflow="verify_models",
                job_id="gate1-check",
            )
            if result.get("ok") is True:
                print("OK — valid model, returns well-formed JSON.")
            else:
                print(f"WARNING — responded but not in the expected shape: {result}")
                ok = False
        except Exception as exc:  # noqa: BLE001
            print(f"FAILED — {exc}")
            print(
                f"  -> '{model}' is likely not a real slug on your AI/ML API account. "
                f"Check https://aimlapi.com/app for the exact model name and update config/models.yaml."
            )
            ok = False

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
