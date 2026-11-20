#!/usr/bin/env python3
"""Merge claude-seo specialist findings into the audit envelope and the two Markdown reports.

    python3 aggregate.py <audits_dir>/<domain>-audit

Each findings/*.md ends with a fenced ```json block of the shape
{"categories":[{"name","score","what_works":[],"findings":[{"title","severity","description","recommendation"}]}]}.
The health score follows skills/seo-audit/SKILL.md weights; other categories are reported but carry no weight.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

WEIGHTS = {"Technical SEO": 22, "Content Quality": 23, "On-Page SEO": 20, "Schema / Structured Data": 10, "Performance (CWV)": 10, "AI Search Readiness": 10, "Images": 5}
ORDER = ["Technical SEO", "On-Page SEO", "Content Quality", "Schema / Structured Data", "Performance (CWV)", "Images", "AI Search Readiness", "Agent Readiness", "Sitemap", "Visual / Mobile UX", "Search Experience (SXO)", "Backlinks / Authority", "Topic Clusters / Internal Linking"]
SEV = ["Critical", "High", "Medium", "Low", "Info"]


def json_block(text: str) -> dict | None:
    blocks = re.findall(r"```json\s*(\{.*?\})\s*```", text, re.S)
    for raw in reversed(blocks):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            continue
    return None


def norm_sev(s: str) -> str:
    s = (s or "Info").strip().capitalize()
    return s if s in SEV else "Info"


def main(folder: Path) -> None:
    findings_dir = folder / "findings"
    cats: dict[str, dict] = {}
    sources: dict[str, str] = {}
    for f in sorted(findings_dir.glob("*.md")):
        data = json_block(f.read_text())
        if not data:
            print(f"! {f.name}: no JSON block", file=sys.stderr)
            continue
        for c in data.get("categories", []):
            name = str(c.get("name", f.stem)).strip()
            score = c.get("score")
            entry = cats.setdefault(name, {"name": name, "score": None, "what_works": [], "findings": []})
            if isinstance(score, (int, float)):
                entry["score"] = round(float(score)) if entry["score"] is None else round((entry["score"] + float(score)) / 2)
            entry["what_works"] += [str(w) for w in c.get("what_works", []) if w]
            for x in c.get("findings", []):
                if not isinstance(x, dict) or not x.get("title"):
                    continue
                entry["findings"].append({"title": str(x["title"]).strip(), "severity": norm_sev(str(x.get("severity", ""))), "description": str(x.get("description", "")).strip(), "recommendation": str(x.get("recommendation", "")).strip(), "category": name})
            sources[name] = f"findings/{f.name}"
    ordered = [cats[n] for n in ORDER if n in cats] + [c for n, c in cats.items() if n not in ORDER]
    weighted = [(c["score"], WEIGHTS[c["name"]]) for c in ordered if c["name"] in WEIGHTS and c["score"] is not None]
    total_w = sum(w for _, w in weighted) or 1
    health = round(sum(s * w for s, w in weighted) / total_w) if weighted else 0
    allf = [f for c in ordered for f in c["findings"]]
    allf.sort(key=lambda f: SEV.index(f["severity"]))
    top = [f"{f['title']} ({f['category']})" for f in allf if f["severity"] in ("Critical", "High")][:5]
    wins = [f"{f['title']} ({f['category']})" for f in allf if f["severity"] in ("Medium", "Low") and len(f["recommendation"]) < 220][:5]
    phases = [
        {"name": "Phase 1: Critical Fixes", "timeframe": "Week 1", "items": [f"{f['title']}: {f['recommendation']}" for f in allf if f["severity"] == "Critical"]},
        {"name": "Phase 2: High-Impact Improvements", "timeframe": "Weeks 2-3", "items": [f"{f['title']}: {f['recommendation']}" for f in allf if f["severity"] == "High"]},
        {"name": "Phase 3: Content & Authority", "timeframe": "Month 2", "items": [f"{f['title']}: {f['recommendation']}" for f in allf if f["severity"] == "Medium"]},
        {"name": "Phase 4: Monitoring & Iteration", "timeframe": "Ongoing", "items": [f"{f['title']}: {f['recommendation']}" for f in allf if f["severity"] in ("Low", "Info")][:12] + ["Re-run /seo audit monthly and compare scores in the SEO Cockpit", "Request indexing for new posts and watch Search Console coverage"]},
    ]
    domain = folder.name[: -len("-audit")]
    existing = {}
    if (folder / "audit-data.json").exists():
        try:
            existing = json.loads((folder / "audit-data.json").read_text())
        except json.JSONDecodeError:
            existing = {}
    env = {
        "meta": {"site": f"https://{domain}", "domain": domain, "generated_at": datetime.now(timezone.utc).isoformat(), "tool": "claude-seo 2.5.0 via SEO Cockpit aggregate.py", "sources": sources},
        "summary": {"health_score": health, "business_type": (existing.get("summary") or {}).get("business_type") or "SaaS", "top_findings": top, "quick_wins": wins, "counts": {s: sum(1 for f in allf if f["severity"] == s) for s in SEV}},
        "categories": [{"name": c["name"], "score": c["score"], "weight": WEIGHTS.get(c["name"], 0), "what_works": c["what_works"][:8], "findings": [{k: v for k, v in f.items() if k != "category"} for f in c["findings"]]} for c in ordered],
        "action_plan": {"phases": phases},
        "artifacts": {"findings_dir": "findings/", "screenshots_dir": "screenshots/"},
    }
    (folder / "audit-data.json").write_text(json.dumps(env, indent=1))

    # FULL-AUDIT-REPORT.md: executive summary, then every specialist file in order.
    lines = [f"# SEO Audit: {domain}", "", f"Generated {env['meta']['generated_at'][:16].replace('T', ' ')} UTC with claude-seo 2.5.0 (free data sources only; Core Web Vitals field data needs a Google API key).", "", "## Executive summary", "", f"**SEO Health Score: {health}/100** ({env['summary']['business_type']})", "", "| Category | Score | Weight | Findings |", "|---|---|---|---|"]
    for c in env["categories"]:
        lines.append(f"| {c['name']} | {c['score'] if c['score'] is not None else 'n/a'} | {c['weight'] or '-'}% | {len(c['findings'])} |")
    lines += ["", "**Top findings**", ""] + [f"- {t}" for t in top] + ["", "**Quick wins**", ""] + [f"- {t}" for t in wins] + ["", "Severity counts: " + ", ".join(f"{k} {v}" for k, v in env["summary"]["counts"].items()), ""]
    for c in env["categories"]:
        src = sources.get(c["name"])
        if src and (folder / src).exists():
            body = re.sub(r"```json\s*\{.*?\}\s*```", "", (folder / src).read_text(), flags=re.S).strip()
            body = re.sub(r"^#\s", "### ", body, flags=re.M)  # demote headings under the category
            body = re.sub(r"^##\s", "#### ", body, flags=re.M)
            lines += ["", f"## {c['name']}: {c['score'] if c['score'] is not None else 'n/a'}/100", "", f"_Source: {src}_", "", body, ""]
    (folder / "FULL-AUDIT-REPORT.md").write_text("\n".join(lines))

    plan = [f"# Action plan: {domain}", "", f"Health score {health}/100. Work the phases in order; each item names the fix the specialist recommended.", ""]
    for p in phases:
        plan += [f"## {p['name']} ({p['timeframe']})", ""] + ([f"{i + 1}. {it}" for i, it in enumerate(p["items"])] or ["- nothing in this phase"]) + [""]
    (folder / "ACTION-PLAN.md").write_text("\n".join(plan))
    print(f"health {health}/100, {len(ordered)} categories, {len(allf)} findings -> {folder}")


if __name__ == "__main__":
    main(Path(sys.argv[1]).expanduser().resolve())
