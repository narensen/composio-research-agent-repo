"""Pass 2: Automated Verification Loop (HTTP link check + targeted re-crawl + Critic LLM)."""
import argparse
import asyncio
import json
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from openai import AsyncOpenAI
from rich.console import Console

from schema import AppResearchRecord, CriticReview

load_dotenv()
console = Console()

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PASS1_PATH = DATA_DIR / "pass1.json"
PASS2_PATH = DATA_DIR / "pass2.json"
DIFF_PATH = DATA_DIR / "verification_diff.json"

CRITIC_PROMPT = """You are an adversarial QA Verifier auditing Pass 1 research for Composio Product Ops.
Given a Pass 1 JSON record and freshly fetched HTTP responses from its evidence URLs:
1. Check if any evidence URL returned 404/5xx or failed to confirm the claimed auth method.
2. Check if 'Self-Serve (Free / Trial)' should actually be 'Sandbox Free, Prod Gated' or 'Partner / Sales-Gated'.
3. Check if an Official MCP server or recent API deprecation was missed.
If the Pass 1 record has any material error, set has_discrepancy=True, return the corrected_record, list changed_fields, and explain concisely why.
"""


async def check_urls(urls: list[str], client: httpx.AsyncClient) -> list[dict]:
    results = []
    for u in urls:
        try:
            r = await client.get(u, follow_redirects=True, timeout=12.0)
            results.append({"url": u, "status": r.status_code, "snippet": r.text[:2500] if r.status_code < 400 else ""})
        except Exception as exc:
            results.append({"url": u, "status": 0, "error": str(exc), "snippet": ""})
    return results


async def verify_record(
    rec: dict,
    llm: AsyncOpenAI,
    http_client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    model: str,
) -> tuple[dict, dict | None]:
    async with sem:
        checks = await check_urls(rec["evidence_urls"], http_client)
        dead_links = [c["url"] for c in checks if c["status"] == 0 or c["status"] >= 400]
        needs_critic = bool(dead_links) or rec.get("confidence", 1.0) < 0.88 or rec["access_tier"] in (
            "Self-Serve (Free / Trial)",
            "No Public API / CLI-Only",
        )
        if not needs_critic:
            return rec, None

        payload = {
            "pass1_record": rec,
            "url_checks": [{"url": c["url"], "status": c["status"], "snippet": c["snippet"][:1800]} for c in checks],
        }
        completion = await llm.beta.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": CRITIC_PROMPT},
                {"role": "user", "content": json.dumps(payload)},
            ],
            response_format=CriticReview,
            temperature=0.0,
        )
        review = completion.choices[0].message.parsed
        if review.has_discrepancy and review.corrected_record is not None:
            fixed = review.corrected_record.model_dump()
            diff_entry = {
                "app_id": rec["id"],
                "app_name": rec["name"],
                "category": rec["category"],
                "field": " / ".join(review.changed_fields) or "multiple",
                "pass1_value": f"{rec['access_tier']} | {rec['existing_mcp']} | {rec['buildability_verdict']}",
                "pass2_value": f"{fixed['access_tier']} | {fixed['existing_mcp']} | {fixed['buildability_verdict']}",
                "reason": review.reason,
            }
            return fixed, diff_entry
        return rec, None


async def main(limit: int | None) -> None:
    if not PASS1_PATH.exists():
        raise FileNotFoundError(f"Run pass1_research.py first; missing {PASS1_PATH}")

    records = json.loads(PASS1_PATH.read_text())
    if limit:
        records = records[:limit]

    llm = AsyncOpenAI()
    model = os.getenv("CRITIC_MODEL", "gpt-4o")
    sem = asyncio.Semaphore(int(os.getenv("MAX_CONCURRENCY", "5")))

    verified: list[dict] = []
    diffs: list[dict] = []
    async with httpx.AsyncClient(headers={"User-Agent": "ComposioVerifierBot/1.0"}) as http_client:
        tasks = [verify_record(r, llm, http_client, sem, model) for r in records]
        for fixed, diff in await asyncio.gather(*tasks):
            verified.append(fixed)
            if diff:
                diffs.append(diff)

    verified.sort(key=lambda x: x["id"])
    PASS2_PATH.write_text(json.dumps(verified, indent=2))
    DIFF_PATH.write_text(json.dumps(diffs, indent=2))
    console.print(f"[green]Pass 2 complete: {len(verified)} records verified, {len(diffs)} corrections logged.[/green]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pass 2: Link + Critic verification loop")
    parser.add_argument("--limit", type=int, default=None, help="Verify first N records")
    args = parser.parse_args()
    asyncio.run(main(args.limit))
