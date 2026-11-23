"""Aggregate pass2.json, verification_diff.json, and human_audit.json into data/research_bundle.json."""
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def main() -> None:
    records = json.loads((DATA_DIR / "pass2.json").read_text())
    diffs = json.loads((DATA_DIR / "verification_diff.json").read_text())
    audit = json.loads((DATA_DIR / "human_audit.json").read_text())

    verdict_counts = Counter(r["buildability_verdict"] for r in records)
    access_counts = Counter(r["access_tier"] for r in records)
    mcp_counts = Counter(r["existing_mcp"] for r in records)
    surface_counts = Counter(r["api_surface"] for r in records)
    auth_counts = Counter(a for r in records for a in r["auth_methods"])

    categories = list(dict.fromkeys(r["category"] for r in records))
    by_category = []
    for cat in categories:
        sub = [r for r in records if r["category"] == cat]
        vc = Counter(r["buildability_verdict"] for r in sub)
        mc = Counter(r["existing_mcp"] for r in sub)
        ac = Counter(r["access_tier"] for r in sub)
        by_category.append({
            "category": cat,
            "total": len(sub),
            "ship_today": vc["Ship Today"],
            "ship_with_caveats": vc["Ship with Caveats"],
            "skill_cli": vc["Skill / CLI Wrapper"],
            "blocked": vc["Blocked (Outreach Needed)"],
            "official_mcp": mc["Official MCP"],
            "sandbox_prod_gated": ac["Sandbox Free, Prod Gated"],
            "paid_required": ac["Self-Serve (Paid Plan Required)"],
            "partner_gated": ac["Partner / Sales-Gated"],
        })

    p1_acc = round(100 * sum(1 for x in audit if x["pass1_correct"]) / len(audit), 1)
    p2_acc = round(100 * sum(1 for x in audit if x["pass2_correct"]) / len(audit), 1)

    bundle = {
        "meta": {
            "title": "100-App Agent Toolkit & MCP Buildability Audit",
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "total_apps": len(records),
            "categories_count": len(categories),
            "pipeline_summary": "3-pass research & verification pipeline (Pass 1 Discovery -> Pass 2 Live Doc Grounding & Critic -> Pass 3 Stratified Human Audit)",
        },
        "kpis": {
            "ship_today_count": verdict_counts["Ship Today"],
            "ship_today_pct": round(100 * verdict_counts["Ship Today"] / len(records), 1),
            "ship_with_caveats_count": verdict_counts["Ship with Caveats"],
            "skill_cli_count": verdict_counts["Skill / CLI Wrapper"],
            "blocked_count": verdict_counts["Blocked (Outreach Needed)"],
            "buildable_without_sales_pct": round(
                100 * (verdict_counts["Ship Today"] + verdict_counts["Ship with Caveats"] + verdict_counts["Skill / CLI Wrapper"]) / len(records), 1
            ),
            "dominant_auth": auth_counts.most_common(1)[0][0],
            "dominant_auth_count": auth_counts.most_common(1)[0][1],
            "official_mcp_count": mcp_counts["Official MCP"],
            "community_mcp_count": mcp_counts["Community MCP"],
            "sandbox_prod_gated_count": access_counts["Sandbox Free, Prod Gated"],
            "paid_required_count": access_counts["Self-Serve (Paid Plan Required)"],
        },
        "clusters": {
            "by_category": by_category,
            "by_auth": dict(auth_counts.most_common()),
            "by_access_tier": dict(access_counts),
            "by_api_surface": dict(surface_counts),
            "by_existing_mcp": dict(mcp_counts),
        },
        "verification": {
            "sample_size": len(audit),
            "pass1_accuracy_pct": p1_acc,
            "pass2_accuracy_pct": p2_acc,
            "accuracy_lift_pp": round(p2_acc - p1_acc, 1),
            "total_corrections_logged": len(diffs),
            "diffs": diffs,
            "human_audit_sample": audit,
        },
        "apps": records,
    }
    out = DATA_DIR / "research_bundle.json"
    out.write_text(json.dumps(bundle, indent=2))
    print(f"Exported {out} ({len(records)} apps, Pass 1 {p1_acc}% -> Pass 2 {p2_acc}%)")


if __name__ == "__main__":
    main()
