"""Pass 3: Stratified 20-app human audit sampler & accuracy scorer."""
import argparse
import json
from collections import defaultdict
from pathlib import Path
from rich.console import Console
from rich.table import Table

console = Console()
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PASS2_PATH = DATA_DIR / "pass2.json"
AUDIT_PATH = DATA_DIR / "human_audit.json"


def generate_sample() -> None:
    records = json.loads(PASS2_PATH.read_text())
    by_cat = defaultdict(list)
    for r in records:
        by_cat[r["category"]].append(r)

    sample = []
    for cat, items in by_cat.items():
        # Pick 2 per category, prioritizing lowest confidence / edge cases
        picked = sorted(items, key=lambda x: (x["confidence"], x["buildability_verdict"] != "Ship Today"))[:2]
        for p in picked:
            sample.append({
                "app_id": p["id"],
                "name": p["name"],
                "category": cat,
                "pass1_correct": True,
                "pass2_correct": True,
                "status": "Pending human review",
                "error_notes": "",
            })
    AUDIT_PATH.write_text(json.dumps(sample, indent=2))
    console.print(f"[green]Generated 20-app stratified audit template at {AUDIT_PATH}[/green]")


def score_audit() -> None:
    audit = json.loads(AUDIT_PATH.read_text())
    total = len(audit)
    p1 = sum(1 for x in audit if x["pass1_correct"])
    p2 = sum(1 for x in audit if x["pass2_correct"])

    table = Table(title="Verification Accuracy Report (Stratified Sample)")
    table.add_column("Stage")
    table.add_column("Correct / Total")
    table.add_column("Accuracy %")
    table.add_row("Pass 1 (Initial Discovery)", f"{p1} / {total}", f"{100 * p1 / total:.1f}%")
    table.add_row("Pass 2 (Post-Verification Loop)", f"{p2} / {total}", f"{100 * p2 / total:.1f}%")
    table.add_row("Accuracy Lift", f"+{p2 - p1} apps", f"+{100 * (p2 - p1) / total:.1f} pp")
    console.print(table)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pass 3: Human audit sample & scorer")
    parser.add_argument("--sample", action="store_true", help="Generate stratified 20-app template")
    parser.add_argument("--score", action="store_true", help="Score completed human_audit.json")
    args = parser.parse_args()
    if args.sample:
        generate_sample()
    else:
        score_audit()
