"""Pass 1: Async research agent using Composio SDK (v2 sessions) + structured Pydantic extraction."""
import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from openai import AsyncOpenAI
from rich.console import Console
from rich.progress import Progress

from schema import AppResearchRecord

load_dotenv()
console = Console()

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
APPS_PATH = DATA_DIR / "apps.json"
OUT_PATH = DATA_DIR / "pass1.json"

SYSTEM_PROMPT = """You are a Senior AI Product Operations Researcher at Composio.
Given an app name, category, hint URL, and retrieved documentation snippets, classify how this app can be built as a Composio toolkit or MCP server.

WATCH FOR THESE KNOWN TRAPS:
1. CLI-only tools (e.g., Sherlock, Mermaid CLI) -> 'No Public API / CLI-Only', 'CLI-Only', 'Skill / CLI Wrapper'.
2. Do NOT assume a '/cli' hint means no REST API — check whether a public REST/GraphQL API also exists (e.g., Higgsfield).
3. Sandbox-free but Production-gated apps (Plaid, Meta Ads, Google Ads, LinkedIn Ads, WhatsApp Business, Amazon SP-API, QuickBooks) -> 'Sandbox Free, Prod Gated', NOT 'Self-Serve (Free / Trial)'.
4. Enterprise / Partner walls (DealCloud, PitchBook, Gladly, SFCC, Waterfall.io, NotebookLM Enterprise) -> 'Partner / Sales-Gated' and 'Blocked (Outreach Needed)'.
5. Check carefully for 2025-2026 official vendor MCP servers and API v1 deprecations (e.g., GoHighLevel v1 EOL).
Always ground every answer in the retrieved doc evidence and cite 1-3 direct official doc URLs.
"""


def init_composio_session() -> Any | None:
    """Initialize a Composio SDK v2 session with search/crawl toolkits if COMPOSIO_API_KEY is set."""
    api_key = os.getenv("COMPOSIO_API_KEY")
    if not api_key:
        return None
    try:
        from composio import Composio

        client = Composio(api_key=api_key)
        session = client.sessions.create(
            user_id="composio_product_ops_researcher",
            toolkits=["tavily", "firecrawl", "exa"],
        )
        return session
    except Exception as exc:
        console.print(f"[yellow]Composio session unavailable ({exc}); falling back to direct httpx crawl.[/yellow]")
        return None


async def fetch_doc_context(app: dict, http_client: httpx.AsyncClient, composio_session: Any | None) -> str:
    """Gather documentation text via Composio session tools or direct httpx fetch fallback."""
    snippets: list[str] = []

    if composio_session is not None:
        try:
            query = f"{app['name']} official API documentation authentication OAuth API key MCP server"
            res = composio_session.execute(
                "TAVILY_SEARCH",
                {"query": query, "max_results": 4, "include_raw_content": False},
            )
            snippets.append(f"[Composio Tavily Search]\n{json.dumps(res)[:6000]}")
        except Exception:
            pass

    hint = app["hint_url"]
    url = hint if hint.startswith("http") else f"https://{hint.split()[0]}"
    try:
        r = await http_client.get(url, follow_redirects=True, timeout=12.0)
        if r.status_code < 400:
            snippets.append(f"[Direct Fetch {r.url} status={r.status_code}]\n{r.text[:4500]}")
    except Exception as exc:
        snippets.append(f"[Direct Fetch Failed for {url}: {exc}]")

    return "\n\n".join(snippets) or "No live page text retrieved; rely on verifiable official docs only and lower confidence."


async def research_one(
    app: dict,
    llm: AsyncOpenAI,
    http_client: httpx.AsyncClient,
    composio_session: Any | None,
    sem: asyncio.Semaphore,
    model: str,
) -> dict:
    async with sem:
        context = await fetch_doc_context(app, http_client, composio_session)
        user_msg = (
            f"App #{app['id']}: {app['name']}\n"
            f"Category: {app['category']}\n"
            f"Hint URL: {app['hint_url']}\n\n"
            f"Retrieved Evidence:\n{context}"
        )
        completion = await llm.beta.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            response_format=AppResearchRecord,
            temperature=0.1,
        )
        record = completion.choices[0].message.parsed
        record.id = app["id"]
        record.name = app["name"]
        record.category = app["category"]
        record.hint_url = app["hint_url"]
        return record.model_dump()


async def main(limit: int | None, force: bool) -> None:
    apps = json.loads(APPS_PATH.read_text())
    if limit:
        apps = apps[:limit]

    existing: dict[int, dict] = {}
    if OUT_PATH.exists() and not force:
        existing = {r["id"]: r for r in json.loads(OUT_PATH.read_text())}

    todo = [a for a in apps if a["id"] not in existing]
    console.print(f"[bold]Pass 1 Discovery:[/bold] {len(existing)} cached, {len(todo)} to research.")
    if not todo:
        return

    llm = AsyncOpenAI()
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    sem = asyncio.Semaphore(int(os.getenv("MAX_CONCURRENCY", "5")))
    composio_session = init_composio_session()

    async with httpx.AsyncClient(headers={"User-Agent": "ComposioProductOpsBot/1.0"}) as http_client:
        with Progress() as progress:
            task = progress.add_task("Researching apps...", total=len(todo))
            coros = [research_one(a, llm, http_client, composio_session, sem, model) for a in todo]
            for fut in asyncio.as_completed(coros):
                rec = await fut
                existing[rec["id"]] = rec
                ordered = [existing[k] for k in sorted(existing)]
                OUT_PATH.write_text(json.dumps(ordered, indent=2))
                progress.advance(task)

    console.print(f"[green]Saved {len(existing)} records to {OUT_PATH}[/green]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pass 1: Composio 100-app discovery agent")
    parser.add_argument("--limit", type=int, default=None, help="Limit to first N apps for smoke testing")
    parser.add_argument("--force", action="store_true", help="Ignore cache and re-run")
    args = parser.parse_args()
    asyncio.run(main(args.limit, args.force))
