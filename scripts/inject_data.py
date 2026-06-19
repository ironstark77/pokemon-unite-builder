#!/usr/bin/env python3
"""
inject_data.py — Re-injects data from the 3 JSONs into index.html.

Replaces three JS literal blocks in the HTML:
  var POKEMON_DATA_RAW   = { ... };   (data/pokemon.json)
  var ITEMS_DATA_RAW     = { ... };   (data/items.json)
  var EMBLEMS_PER_POKEMON = { ... };  (data/emblems.json)

Safety:
  - Always restores from backup before writing
  - Validates JSON parses before injecting
  - Validates output JS syntax with `node --check` on a stripped excerpt
  - Refuses to run if size delta > 50% (sanity check)

Usage:
  python3 scripts/inject_data.py            # inject
  python3 scripts/inject_data.py --dry-run  # show diff stats only
  python3 scripts/inject_data.py --restore  # restore from latest backup
"""
from __future__ import annotations
import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "index.html"
DATA = ROOT / "data"
BACKUP_DIR = ROOT / ".backups"


def find_var_block(html: str, var_name: str) -> tuple[int, int] | None:
    """Locate a `var NAME = { ... };` literal block via brace counting.

    Skips placeholder `var NAME = null;` declarations.
    Returns (start_offset, end_offset) inclusive of the trailing semicolon,
    or None if not found.
    """
    # Find the LAST occurrence of `var NAME = {` (literal, not null)
    pattern = re.compile(rf"var {re.escape(var_name)}\s*=\s*\{{")
    matches = list(pattern.finditer(html))
    if not matches:
        return None
    m = matches[-1]  # the literal, not the placeholder
    start_brace = m.end() - 1
    depth = 0
    i = start_brace
    while i < len(html):
        c = html[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end_brace = i
                break
        i += 1
    else:
        raise ValueError(f"Unbalanced braces in {var_name} block")
    # consume trailing whitespace and ;
    j = end_brace + 1
    while j < len(html) and html[j] in " \t\n":
        j += 1
    if j < len(html) and html[j] == ";":
        j += 1
    return m.start(), j


def replace_var_block(html: str, var_name: str, new_value: str) -> str:
    """Replace the literal block for var_name with `new_value` (raw JS, not quoted)."""
    span = find_var_block(html, var_name)
    if span is None:
        raise ValueError(f"Could not find var {var_name} in HTML")
    start, end = span
    replacement = f"var {var_name} = {new_value};"
    return html[:start] + replacement + html[end:]


def load_json_as_js(path: Path) -> str:
    """Load a JSON file and serialize it to compact JS (matches existing style)."""
    data = json.loads(path.read_text())
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False)


def backup_html() -> Path:
    BACKUP_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"index_{ts}.html"
    shutil.copy2(HTML, dest)
    # Keep only the 5 most recent backups
    backups = sorted(BACKUP_DIR.glob("index_*.html"), key=lambda p: p.stat().st_mtime)
    for old in backups[:-5]:
        old.unlink()
    return dest


def node_check(html: str) -> tuple[bool, str]:
    """Extract the data blocks and run `node --check` on them."""
    script = """
const fs = require('fs');
const path = require('path');
const html = fs.readFileSync(process.argv[2], 'utf8');
// Extract all var X = {...}; blocks
const blocks = [];
const re = /var (POKEMON_DATA_RAW|ITEMS_DATA_RAW|EMBLEMS_PER_POKEMON) = (\\{[\\s\\S]*?\\});/g;
let m;
while ((m = re.exec(html)) !== null) {
    blocks.push(m[0]);
}
const code = blocks.join("\\n\\n");
fs.writeFileSync(process.argv[3], code);
"""
    with open("/tmp/_extract.js", "w") as f:
        f.write(script)
    out = Path("/tmp/_injection_check.js")
    out.write_text("")
    proc = subprocess.run(
        ["node", "/tmp/_extract.js", str(HTML), str(out)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return False, proc.stderr
    proc2 = subprocess.run(
        ["node", "--check", str(out)],
        capture_output=True,
        text=True,
    )
    if proc2.returncode != 0:
        return False, proc2.stderr
    return True, "OK"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--restore", action="store_true")
    args = ap.parse_args()

    if args.restore:
        backups = sorted(BACKUP_DIR.glob("index_*.html"), key=lambda p: p.stat().st_mtime)
        if not backups:
            print("No backups found", file=sys.stderr)
            return 1
        latest = backups[-1]
        shutil.copy2(latest, HTML)
        print(f"Restored from {latest}")
        return 0

    html = HTML.read_text()
    original_size = len(html)
    print(f"Original HTML: {original_size:,} bytes")

    # 1) Find the three literal blocks
    spans = {}
    for var in ["POKEMON_DATA_RAW", "ITEMS_DATA_RAW", "EMBLEMS_PER_POKEMON"]:
        span = find_var_block(html, var)
        if span is None:
            print(f"ERROR: var {var} not found", file=sys.stderr)
            return 2
        spans[var] = span
        print(f"  {var}: offset {span[0]}-{span[1]} (size {span[1] - span[0]:,})")

    # 2) Load JSON files
    sources = {
        "POKEMON_DATA_RAW": DATA / "pokemon.json",
        "ITEMS_DATA_RAW": DATA / "items.json",
        "EMBLEMS_PER_POKEMON": DATA / "emblems.json",
    }
    payloads = {}
    for var, path in sources.items():
        if not path.exists():
            print(f"ERROR: {path} not found", file=sys.stderr)
            return 2
        payloads[var] = load_json_as_js(path)
        print(f"  {var} ← {path.name} ({len(payloads[var]):,} bytes serialized)")

    # 3) Build new HTML
    new_html = html
    for var, payload in payloads.items():
        new_html = replace_var_block(new_html, var, payload)
    new_size = len(new_html)
    delta_pct = (new_size - original_size) / original_size * 100
    print(f"New HTML: {new_size:,} bytes (delta {delta_pct:+.1f}%)")
    if abs(delta_pct) > 50:
        print(f"ERROR: size delta {delta_pct:.1f}% exceeds 50% safety threshold", file=sys.stderr)
        return 3

    if args.dry_run:
        print("\nDRY RUN — no changes written")
        for var in payloads:
            new_span = find_var_block(new_html, var)
            old_size = spans[var][1] - spans[var][0]
            new_block_size = new_span[1] - new_span[0]
            print(f"  {var}: {old_size:,} → {new_block_size:,} bytes ({(new_block_size-old_size)/old_size*100:+.1f}%)")
        return 0

    # 4) Backup and write
    backup = backup_html()
    print(f"Backed up to {backup}")
    HTML.write_text(new_html)
    print(f"Wrote {HTML}")

    # 5) Validate
    ok, msg = node_check(HTML)
    if not ok:
        print(f"\n❌ node --check FAILED: {msg}", file=sys.stderr)
        print(f"Restoring from backup {backup}", file=sys.stderr)
        shutil.copy2(backup, HTML)
        return 4
    print(f"\n✅ node --check passed: {msg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
