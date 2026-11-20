#!/usr/bin/env python3
"""SEO Cockpit: a local dashboard over claude-seo's audit output.

    python3 cockpit.py build            # collect audits (+ vitals / Search Console when available) into data/
    python3 cockpit.py serve --port 8791  # build, then serve the dashboard at http://localhost:8791

Sources, all local:
  * audits/<domain>-audit/audit-data.json and its reports  (written by an audit run, see docs/AUDIT-PROMPT.md)
  * claude-seo's own scripts for PageSpeed/CrUX and Search Console (they use claude-seo's Google setup)
Nothing here talks to a paid API. Settings live in data/sites.json (copy data/sites.example.json).
The audits folder defaults to ./audits; change "audits_dir" in data/sites.json to keep audits elsewhere.
claude-seo is looked for in ~/.claude/skills/seo; set CLAUDE_SEO_HOME if it lives somewhere else.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
SITES_FILE = DATA / "sites.json"
CLAUDE_SEO = Path(os.environ.get("CLAUDE_SEO_HOME") or Path.home() / ".claude" / "skills" / "seo").expanduser() / "scripts" / "claude-seo"
DEFAULT_AUDITS = HERE / "audits"


def load_sites() -> dict:
    if SITES_FILE.exists():
        return json.loads(SITES_FILE.read_text())
    return {"audits_dir": str(DEFAULT_AUDITS), "sites": []}


def host_of(value: str) -> str:
    text = re.sub(r"^sc-domain:", "", value.strip())
    text = re.sub(r"^https?://", "", text).split("/")[0].lower()
    return re.sub(r"^www\.", "", text)


def run_script(script: str, args: list[str], timeout: int = 240) -> tuple[dict | list | None, str | None]:
    """Runs a claude-seo script with --json and returns (parsed, error)."""
    if not CLAUDE_SEO.exists():
        return None, "claude-seo is not installed (expected ~/.claude/skills/seo, or set CLAUDE_SEO_HOME)"
    try:
        proc = subprocess.run([str(CLAUDE_SEO), "run", script, *args, "--json"], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, f"{script} timed out after {timeout}s"
    out = proc.stdout.strip()
    try:
        return json.loads(out[out.index("{") :]) if "{" in out else None, None if proc.returncode == 0 else (proc.stderr.strip().splitlines() or ["failed"])[-1][:200]
    except (ValueError, json.JSONDecodeError):
        return None, (proc.stderr.strip().splitlines() or [out[:200] or "no output"])[-1][:200]


def collect_audit(site_dir: Path, audits_dir: Path, domain: str) -> dict | None:
    folder = audits_dir / f"{domain}-audit"
    data_file = folder / "audit-data.json"
    if not data_file.exists():
        return None
    try:
        audit = json.loads(data_file.read_text())
    except json.JSONDecodeError as e:
        return {"error": f"audit-data.json is not valid JSON: {e}"}
    reports = site_dir / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    copied = []
    for name in ["FULL-AUDIT-REPORT.md", "ACTION-PLAN.md"]:
        if (folder / name).exists():
            shutil.copy(folder / name, reports / name)
            copied.append(name)
    if (folder / "findings").is_dir():
        (reports / "findings").mkdir(exist_ok=True)
        for f in sorted((folder / "findings").glob("*.md")):
            shutil.copy(f, reports / "findings" / f.name)
            copied.append(f"findings/{f.name}")
    for report in sorted(list(folder.glob("*.pdf")) + list(folder.glob("Google-SEO-Report-*.html"))):
        shutil.copy(report, reports / report.name)
        copied.append(report.name)
    shots = folder / "screenshots"
    if shots.is_dir():
        (reports / "screenshots").mkdir(exist_ok=True)
        for f in sorted(shots.glob("*.png"))[:6]:
            shutil.copy(f, reports / "screenshots" / f.name)
            copied.append(f"screenshots/{f.name}")
    audit["_meta"] = {"folder": str(folder), "written_at": datetime.fromtimestamp(data_file.stat().st_mtime, tz=timezone.utc).isoformat(), "files": copied}
    (site_dir / "audit.json").write_text(json.dumps(audit, indent=1))
    return audit


def collect_vitals(site_dir: Path, url: str, api_key: str | None, refresh: bool) -> dict | None:
    target = site_dir / "vitals.json"
    if target.exists() and not refresh and time.time() - target.stat().st_mtime < 6 * 3600:
        return json.loads(target.read_text())
    args = [url, "--strategy", "both"] + (["--api-key", api_key] if api_key else [])
    data, err = run_script("pagespeed_check.py", args, timeout=300)
    if data is None:
        data = {"error": err or "no data"}
    elif err and not data.get("error"):
        data["error"] = err
    data["_meta"] = {"fetched_at": datetime.now(timezone.utc).isoformat()}
    target.write_text(json.dumps(data, indent=1))
    return data


def collect_gsc(site_dir: Path, prop: str, refresh: bool) -> dict | None:
    target = site_dir / "gsc.json"
    if target.exists() and not refresh and time.time() - target.stat().st_mtime < 6 * 3600:
        return json.loads(target.read_text())
    out: dict = {"property": prop, "_meta": {"fetched_at": datetime.now(timezone.utc).isoformat()}}
    for key, dims in [("by_day", "date"), ("by_query", "query"), ("by_page", "page")]:
        data, err = run_script("gsc_query.py", ["query", "--property", prop, "--days", "28", "--dimensions", dims, "--limit", "200"], timeout=120)
        if data is None:
            out["error"] = err or "no data"
            break
        out[key] = data
    target.write_text(json.dumps(out, indent=1))
    return out


def summarize(domain: str, audit: dict | None, vitals: dict | None, gsc: dict | None) -> dict:
    s: dict = {"domain": domain}
    if audit and not audit.get("error"):
        cats = [c for c in audit.get("categories", []) if isinstance(c, dict) and isinstance(c.get("score"), (int, float))]
        weakest = min(cats, key=lambda c: c["score"]) if cats else None
        findings = [f for c in audit.get("categories", []) for f in (c.get("findings") or []) if isinstance(f, dict)]
        s["audit"] = {
            "score": (audit.get("summary") or {}).get("health_score"),
            "weakest": {"name": weakest["name"], "score": weakest["score"]} if weakest else None,
            "findings": len(findings),
            "critical": sum(1 for f in findings if str(f.get("severity", "")).lower() == "critical"),
            "written_at": audit.get("_meta", {}).get("written_at"),
        }
    elif audit:
        s["audit"] = {"error": audit["error"]}
    if vitals:
        s["vitals"] = {"error": vitals.get("error"), "fetched_at": vitals.get("_meta", {}).get("fetched_at"), "mobile_perf": ((vitals.get("psi") or {}).get("mobile") or {}).get("lighthouse_scores", {}).get("performance")}
    if gsc:
        s["gsc"] = {"error": gsc.get("error"), "fetched_at": gsc.get("_meta", {}).get("fetched_at")}
    return s


def build(refresh: bool = False, vitals: bool = True, gsc: bool = True) -> dict:
    cfg = load_sites()
    audits_dir = Path(os.path.expanduser(cfg.get("audits_dir") or str(DEFAULT_AUDITS)))
    if not audits_dir.is_absolute():
        audits_dir = HERE / audits_dir   # "./audits" in sites.json means next to this file
    api_key = os.environ.get("GOOGLE_API_KEY") or cfg.get("google_api_key") or None
    sites = {host_of(s["url"] if isinstance(s, dict) else s): (s if isinstance(s, dict) else {"url": s}) for s in cfg.get("sites", [])}
    # Every audit folder counts as a site, even one not in sites.json.
    if audits_dir.is_dir():
        for folder in sorted(audits_dir.glob("*-audit")):
            d = host_of(folder.name[: -len("-audit")])
            sites.setdefault(d, {"url": f"https://{d}"})
    index = {"generated_at": datetime.now(timezone.utc).isoformat(), "audits_dir": str(audits_dir), "claude_seo": CLAUDE_SEO.exists(), "sites": []}
    for domain, meta in sites.items():
        site_dir = DATA / domain
        site_dir.mkdir(parents=True, exist_ok=True)
        audit = collect_audit(site_dir, audits_dir, domain)
        v = collect_vitals(site_dir, meta.get("url", f"https://{domain}"), api_key, refresh) if vitals and (audit or meta.get("vitals", True)) and meta.get("vitals", True) else None
        g = collect_gsc(site_dir, meta.get("gsc") or f"sc-domain:{domain}", refresh) if gsc and meta.get("gsc") else None
        entry = summarize(domain, audit, v, g)
        entry.update({"url": meta.get("url", f"https://{domain}"), "label": meta.get("label", domain), "gsc_property": meta.get("gsc")})
        index["sites"].append(entry)
    (DATA / "index.json").write_text(json.dumps(index, indent=1))
    return index


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(HERE), **kw)

    def do_GET(self):  # noqa: N802
        if self.path.startswith("/api/rebuild"):
            refresh = "refresh=1" in self.path
            try:
                index = build(refresh=refresh)
                body = json.dumps({"ok": True, "sites": len(index["sites"])}).encode()
            except Exception as e:  # noqa: BLE001
                body = json.dumps({"ok": False, "error": str(e)[:300]}).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return super().do_GET()

    def end_headers(self):
        self.send_header("cache-control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):  # quieter log
        if "/api/" in str(args[0]) or " 404 " in fmt % args:
            sys.stderr.write("%s\n" % (fmt % args))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["build", "serve"])
    ap.add_argument("--port", type=int, default=8791)
    ap.add_argument("--refresh", action="store_true", help="refetch vitals and Search Console even if cached")
    ap.add_argument("--no-vitals", action="store_true")
    ap.add_argument("--no-gsc", action="store_true")
    a = ap.parse_args()
    DATA.mkdir(exist_ok=True)
    index = build(refresh=a.refresh, vitals=not a.no_vitals, gsc=not a.no_gsc)
    print(f"built data for {len(index['sites'])} site(s) from {index['audits_dir']}")
    if a.command == "serve":
        srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
        print(f"SEO Cockpit at http://localhost:{a.port}")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
