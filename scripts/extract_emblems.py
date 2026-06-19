#!/usr/bin/env python3
"""
extract_emblems.py — Extract the EMBLEMS_PER_POKEMON block from index.html
and write it to data/emblems.json as a flat object (id-keyed) with a
metadata header.

This brings the emblems JSON in sync with the live HTML so that
`inject_data.py` can round-trip without shrinking it.
"""
from __future__ import annotations
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "index.html"
EMBLEMS_JSON = ROOT / "data" / "emblems.json"


def main() -> int:
    html = HTML.read_text()
    # Find the LAST occurrence of `var EMBLEMS_PER_POKEMON = {...};` (the literal)
    pattern = re.compile(r"var EMBLEMS_PER_POKEMON\s*=\s*(\{[\s\S]+?\});", re.MULTILINE)
    matches = list(pattern.finditer(html))
    if not matches:
        print("ERROR: EMBLEMS_PER_POKEMON literal not found", file=sys.stderr)
        return 1
    m = matches[-1]
    raw = m.group(1)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: bad JSON in HTML block: {e}", file=sys.stderr)
        return 2

    n_keys = len(data)
    # Sample first entry to show structure
    first_key = next(iter(data))
    sample = data[first_key]
    print(f"Extracted {n_keys} pokemon emblems sets from HTML")
    print(f"Sample key: {first_key}")
    print(f"Sample fields: {list(sample.keys())[:8]}")
    print(f"Emblems per pokemon: {len(sample.get('emblems', []))}")

    # Wrap with metadata
    out = {
        "version": "1.23.1.1",  # will be updated by inject
        "extracted_at": datetime.now().isoformat(timespec="seconds"),
        "source": "index.html (var EMBLEMS_PER_POKEMON literal)",
        "n_pokemon": n_keys,
        "emblems": data,
    }
    EMBLEMS_JSON.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"Wrote {EMBLEMS_JSON} ({EMBLEMS_JSON.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
