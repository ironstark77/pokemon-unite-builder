#!/usr/bin/env python3
"""
check_patches.py — Detect new Pokemon UNITE patches from game8.co.

Reads the latest patch info from game8.co and compares against the
known-state stored in data/patch_index.json. If a new patch is found,
emits a JSON line with details. The cron prompt reads this output and
forwards to Telegram.

Exit codes:
  0 — no new patch (silent)
  1 — new patch detected (prints JSON to stdout)
  2 — error (network, parse)
"""
from __future__ import annotations
import json
import re
import sys
from html import unescape
from pathlib import Path
from urllib import request

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "data" / "patch_index.json"
NEWS_URL = "https://game8.co/games/Pokemon-UNITE/archives/335393"


def strip_html(html: str) -> str:
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def fetch(url: str) -> str:
    req = request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", errors="replace")


def main() -> int:
    if not INDEX.exists():
        print(f"ERROR: {INDEX} not found", file=sys.stderr)
        return 2
    known = json.loads(INDEX.read_text())
    known_versions = {p["version"] for p in known.get("2026_patches", [])}

    try:
        raw = fetch(NEWS_URL)
    except Exception as e:
        print(f"ERROR: network: {e}", file=sys.stderr)
        return 2
    text = strip_html(raw)

    # Extract latest patch from "Latest Patch: Version X.Y.Z.W"
    m = re.search(r"Latest Patch:\s*Version\s+(\d+\.\d+\.\d+\.\d+)", text)
    if not m:
        print("ERROR: could not find latest patch version in page", file=sys.stderr)
        return 2
    latest = m.group(1)
    if latest in known_versions:
        return 0  # no new patch

    # Find the release date of the new patch
    m_date = re.search(
        rf"Version\s+{re.escape(latest)}\s*released on\s+([A-Z][a-z]+\s+\d+,\s+\d+)",
        text,
    )
    if not m_date:
        m_date = re.search(
            rf"Version\s+{re.escape(latest)}\s+Patch\s+Note\s+Updates?[^a-zA-Z0-9]+([A-Z][a-z]+\s+\d+,\s+\d+)",
            text,
        )
    release_date = m_date.group(1) if m_date else "unknown"

    # Look for new pokemon names in the surrounding text
    new_pokemon_pattern = re.compile(
        r"(\w[\w' \-]+?)\s+has joined the Pokemon UNITE roster on\s+"
        r"([A-Z][a-z]+\s+\d+,\s+\d{4})"
    )
    new_pokes = [m.group(0) for m in new_pokemon_pattern.finditer(text)]

    result = {
        "new_patch": True,
        "version": latest,
        "release_date": release_date,
        "source": NEWS_URL,
        "recent_roster_additions": new_pokes[:6],
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1


if __name__ == "__main__":
    sys.exit(main())
