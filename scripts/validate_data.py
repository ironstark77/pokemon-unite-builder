#!/usr/bin/env python3
"""
validate_data.py — Verify the integrity of the 3 data JSONs and the index.html.

Checks:
  1. All 3 JSONs parse
  2. Pokemon JSON: 90+ entries, all have required fields
  3. Items JSON: held_items and battle_items present
  4. Emblems JSON: 90+ pokemon sets, each with 10 emblems
  5. Pokemon referenced in emblems exist in pokemon.json
  6. Emblem icon URLs return HTTP 200 (sampled)
  7. Index.html has the 3 var blocks and they parse

Exits non-zero if any check fails.
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path
from urllib import request, error

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
HTML = ROOT / "index.html"
POKEMON_API = "https://pokeapi.co/api/v2/pokemon/{id}"

errors: list[str] = []
warnings: list[str] = []


def check_json_parses(path: Path) -> dict | None:
    if not path.exists():
        errors.append(f"{path.name}: file not found")
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as e:
        errors.append(f"{path.name}: JSON parse error: {e}")
        return None


def check_pokemon(data: dict) -> list[str]:
    ids = []
    required = ["id", "name_en", "name_es", "role", "style", "attack_type", "builds"]
    for pk in data.get("pokemon", []):
        missing = [f for f in required if f not in pk]
        if missing:
            errors.append(f"pokemon {pk.get('id', '?')}: missing fields {missing}")
        if not pk.get("builds"):
            warnings.append(f"pokemon {pk.get('id', '?')}: no builds")
        ids.append(pk["id"])
    if len(ids) < 90:
        warnings.append(f"pokemon count is {len(ids)}, expected 90+")
    return ids


def check_emblems(data: dict) -> list[str]:
    emblems_dict = data.get("emblems", data)
    keys = []
    for poke_id, em_set in emblems_dict.items():
        if not isinstance(em_set, dict):
            continue
        keys.append(poke_id)
        ems = em_set.get("emblems", [])
        if len(ems) != 10:
            warnings.append(f"emblems[{poke_id}]: has {len(ems)} emblems, expected 10")
        for em in ems:
            if "icon_url" not in em:
                errors.append(f"emblems[{poke_id}]: emblem missing icon_url")
    if len(keys) < 90:
        warnings.append(f"emblems: {len(keys)} pokemon sets, expected 90+")
    return keys


def check_items(data: dict) -> None:
    if "held_items" not in data:
        errors.append("items: missing held_items")
    if "battle_items" not in data:
        errors.append("items: missing battle_items")
    if len(data.get("held_items", {})) < 5:
        warnings.append(f"items: only {len(data.get('held_items', {}))} held items")


def check_icon_url(url: str) -> bool:
    try:
        req = request.Request(url, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
        with request.urlopen(req, timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


def main() -> int:
    print(f"=== Validating {ROOT.name} ===\n")

    # 1) JSONs parse
    p_data = check_json_parses(DATA / "pokemon.json")
    i_data = check_json_parses(DATA / "items.json")
    e_data = check_json_parses(DATA / "emblems.json")
    if p_data:
        print(f"✅ pokemon.json parses (version {p_data.get('version')})")
    if i_data:
        print(f"✅ items.json parses (version {i_data.get('version')})")
    if e_data:
        print(f"✅ emblems.json parses (version {e_data.get('version')})")

    if not all([p_data, i_data, e_data]):
        print("\n❌ JSON parse failures - aborting further checks")
        for e in errors:
            print(f"  {e}")
        return 1

    # 2) Field checks
    poke_ids = check_pokemon(p_data) if p_data else []
    em_poke_ids = check_emblems(e_data) if e_data else []
    check_items(i_data) if i_data else None

    print(f"\n✅ pokemon: {len(poke_ids)} entries")
    print(f"✅ emblems: {len(em_poke_ids)} pokemon sets")

    # 3) Cross-reference: emblems for pokemon not in pokemon list
    if poke_ids and em_poke_ids:
        missing_in_poke = set(em_poke_ids) - set(poke_ids)
        missing_in_emblems = set(poke_ids) - set(em_poke_ids)
        if missing_in_poke:
            warnings.append(
                f"emblems for {len(missing_in_poke)} pokemon not in pokemon.json: {sorted(missing_in_poke)[:5]}"
            )
        if missing_in_emblems:
            warnings.append(
                f"pokemon without emblems: {len(missing_in_emblems)}: {sorted(missing_in_emblems)[:5]}"
            )
        if not missing_in_poke and not missing_in_emblems:
            print("✅ emblems <-> pokemon cross-reference OK")

    # 4) Sample icon URLs (5 emblem icons)
    if e_data:
        emblems_dict = e_data.get("emblems", e_data)
        sample_count = 0
        ok_count = 0
        for poke_id, em_set in list(emblems_dict.items())[:3]:
            for em in em_set.get("emblems", [])[:2]:
                url = em.get("icon_url")
                if not url:
                    continue
                sample_count += 1
                if check_icon_url(url):
                    ok_count += 1
                else:
                    warnings.append(f"icon 404: {url}")
        print(f"✅ icons sampled: {ok_count}/{sample_count} returned 200")

    # 5) index.html has blocks
    if HTML.exists():
        html = HTML.read_text()
        for var in ["POKEMON_DATA_RAW", "ITEMS_DATA_RAW", "EMBLEMS_PER_POKEMON"]:
            if not re.search(rf"var {var}\s*=\s*\{{", html):
                errors.append(f"index.html: missing var {var} block")
            else:
                # Try to parse the block
                m = re.search(rf"var {var}\s*=\s*(\{{[\s\S]+?\}});", html)
                if m:
                    try:
                        json.loads(m.group(1))
                        print(f"✅ index.html: {var} block parses")
                    except json.JSONDecodeError as e:
                        errors.append(f"index.html: {var} block invalid JSON: {e}")
    else:
        errors.append("index.html not found")

    # Summary
    print(f"\n=== Summary ===")
    if errors:
        print(f"\n❌ {len(errors)} errors:")
        for e in errors:
            print(f"  - {e}")
    if warnings:
        print(f"\n⚠️  {len(warnings)} warnings:")
        for w in warnings:
            print(f"  - {w}")
    if not errors and not warnings:
        print("✅ All checks passed.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
