#!/usr/bin/env python3
"""
Scrape Pokemon UNITE patch notes from game8.co and produce a structured JSON.

Sources (verified at runtime):
- game8.co/games/Pokemon-UNITE/archives/335393 (Latest News + Patch List)
- game8.co/games/Pokemon-UNITE/archives/<id> (per-patch detail)
- game8.co/games/Pokemon-UNITE/archives/335997 (Tier List, June 2026)
- game8.co/games/Pokemon-UNITE/archives/337932 (Upcoming & New Pokemon)
- unite-db.com/patch-notes (cross-check)

Only facts that are present in the source HTML are kept. Anything missing is
emitted as null or as an empty list so the caller can fill in manually.
"""
import json
import re
import sys
import time
from html import unescape
from pathlib import Path
from urllib import request, error

BASE = "https://game8.co/games/Pokemon-UNITE/archives/{aid}"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch(url: str) -> str:
    req = request.Request(url, headers=HEADERS)
    with request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", errors="replace")


def strip_html(html: str) -> str:
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def find_archives_near(raw_html: str, needle: str, max_dist: int = 600) -> list[str]:
    """Find archive IDs within `max_dist` chars of `needle` in the raw HTML."""
    out: list[str] = []
    for m in re.finditer(re.escape(needle), raw_html):
        start = max(0, m.start() - max_dist)
        end = min(len(raw_html), m.end() + max_dist)
        window = raw_html[start:end]
        for aid in re.findall(r"archives/(\d+)", window):
            if aid not in out:
                out.append(aid)
    return out


def parse_patch_page(archive_id: str) -> dict:
    raw = fetch(BASE.format(aid=archive_id))
    text = strip_html(raw)

    result: dict = {
        "archive_id": archive_id,
        "url": f"https://game8.co/games/Pokemon-UNITE/archives/{archive_id}",
        "title": None,
        "version": None,
        "release_date": None,
        "last_updated": None,
        "summary_changes": [],
        "buffed_pokemon": [],
        "nerfed_pokemon": [],
        "raw_excerpt": None,
    }

    # Title
    m = re.search(r"Version\s+(\d+\.\d+\.\d+\.\d+)\s+Patch Note Updates", text)
    if m:
        result["title"] = f"Version {m.group(1)} Patch Note Updates"
        result["version"] = m.group(1)

    # Last updated line: "Last updated on: <date>"
    m = re.search(r"Last updated on:\s*([^☆★]+?)\s*[☆★]", text)
    if m:
        result["last_updated"] = m.group(1).strip()

    # Release date: "released on <date>"
    m = re.search(r"released on\s+([A-Z][a-z]+\s+\d+,\s+\d{4})", text)
    if m:
        result["release_date"] = m.group(1)

    # Server update: "server update was made on <date>"
    if not result["release_date"]:
        m = re.search(
            r"server update was made on\s+([A-Z][a-z]+\s+\d+,\s+\d{4})", text
        )
        if m:
            result["release_date"] = m.group(1)

    # Buffed Pokemon list
    m = re.search(r"Buffed Pokemon\s+([A-Z][\w\s,'/\-]+?)\s+Nerfed Pokemon", text)
    if m:
        names = [n.strip() for n in m.group(1).split() if n.strip()]
        result["buffed_pokemon"] = names

    # Nerfed Pokemon list
    m = re.search(r"Nerfed Pokemon\s+([A-Z][\w\s,'/\-]+?)\s+Version", text)
    if m:
        names = [n.strip() for n in m.group(1).split() if n.strip()]
        result["nerfed_pokemon"] = names

    # Raw excerpt (first 500 chars after "Detailed Patch Notes")
    idx = text.find("Detailed Patch Notes")
    if idx > 0:
        result["raw_excerpt"] = text[idx : idx + 1500]

    return result


def main() -> int:
    # 1) Fetch the news page and find patch archive IDs for 2026 patches
    news = fetch(BASE.format(aid="335393"))
    text = strip_html(news)

    patches_index = []
    # Pattern: "Version X.Y.Z.W (Month D, YYYY)" near 2026 dates
    pattern = re.compile(
        r"Version\s+(\d+\.\d+\.\d+\.\d+)\s*\(([A-Z][a-z]+\s+\d+,\s+\d{4})\)"
    )
    for m in pattern.finditer(text):
        version = m.group(1)
        date = m.group(2)
        if "2026" in date or "2025" in date:
            patches_index.append({"version": version, "date": date})

    # 2) For each 2026 patch, find its archive ID
    detailed = []
    seen_aids: set[str] = set()
    for p in patches_index:
        # Find archive IDs near "Version X.Y.Z.W" in the news page
        cands = find_archives_near(news, f"Version {p['version']}", max_dist=400)
        for aid in cands:
            if aid in seen_aids or aid == "335393":
                continue
            seen_aids.add(aid)
            print(f"Fetching patch {p['version']} from archive {aid} ...", file=sys.stderr)
            try:
                detail = parse_patch_page(aid)
            except Exception as e:
                print(f"  ! error: {e}", file=sys.stderr)
                continue
            detailed.append(detail)
            time.sleep(0.5)

    out = {
        "source_news": "https://game8.co/games/Pokemon-UNITE/archives/335393",
        "patches_index_2026": patches_index,
        "detailed": detailed,
    }

    Path("data").mkdir(exist_ok=True)
    out_path = Path("data/patches_2026.json")
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"Wrote {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
