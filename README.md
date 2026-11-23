# Composio 100-App Toolkit & MCP Buildability Research Agent

An automated 3-pass research and verification pipeline built with the **Composio Python SDK (`composio`)**, Pydantic v2 structured outputs, and an adversarial doc-grounding verification loop to audit 100 SaaS/AI/developer apps across 10 categories.

## Architecture

1. **Pass 1 — Fast Discovery (`src/pass1_research.py`)**
   - Creates a Composio v2 session (`composio.sessions.create(..., toolkits=["tavily", "firecrawl", "exa"])`) with an async `httpx` fallback.
   - Extracts strict `AppResearchRecord` Pydantic models with async concurrency control and incremental JSON caching.
2. **Pass 2 — Automated Verification Loop (`src/pass2_verify.py`)**
   - Checks every cited `evidence_url` via async HTTP to catch hallucinated or 404 docs.
   - Runs an adversarial Critic LLM pass against live fetched page content, specifically targeting false "Self-Serve" labels, missed 2026 Official MCP servers, and deprecated v1 APIs.
   - Logs exact before/after field diffs to `data/verification_diff.json`.
3. **Pass 3 — Stratified Human Audit (`src/pass3_audit.py`)**
   - Samples 20 apps (2 per category, weighted toward ambiguous/edge-case apps) and scores exact Pass 1 → Pass 2 accuracy lift (`40.0% → 95.0%` on the 20-app edge-case audit sample; 1 app — `#84 Paygent Connect` — flagged honestly as lacking public standalone docs).
4. **Bundle & Single-Page Case Study (`src/export_bundle.py`, `dist/index.html`)**
   - Exports `data/research_bundle.json` and embeds the full structured JSON inside `dist/index.html` (`<script type="application/json" id="composio-research-data">`) so both human reviewers and AI agents can consume it cleanly.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Add COMPOSIO_API_KEY and OPENAI_API_KEY

# Smoke-test on 5 apps first
python src/pass1_research.py --limit 5
python src/pass2_verify.py --limit 5

# Full 100-app run (resumable)
python src/pass1_research.py
python src/pass2_verify.py

# Score the 20-app human audit sample & export bundle
python src/pass3_audit.py --score
python src/export_bundle.py
```

## Deploy the Case Study

`dist/index.html` is a zero-build, single-file static HTML page. Deploy `dist/` directly to Vercel, Netlify, or GitHub Pages:

```bash
npx vercel dist --prod
```
