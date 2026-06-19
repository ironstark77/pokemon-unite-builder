#!/usr/bin/env python3
"""
notify_telegram.py — Send a Telegram message via the bot API.

Reads:
  - TELEGRAM_BOT_TOKEN (env var)
  - TELEGRAM_CHAT_ID  (env var or default)

Usage:
  python3 scripts/notify_telegram.py "Hello world"
  python3 scripts/notify_telegram.py "Multi-line\nmessage" --silent
"""
from __future__ import annotations
import argparse
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_env():
    """Load .env file from project root if present."""
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("message", nargs="?")
    ap.add_argument("--silent", action="store_true",
                    help="Send without notification sound")
    ap.add_argument("--chat-id", help="Override chat_id")
    args = ap.parse_args()

    load_env()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = args.chat_id or os.environ.get("TELEGRAM_CHAT_ID")

    if not args.message:
        ap.error("message is required")
    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN env var not set", file=sys.stderr)
        return 2
    if not chat_id:
        print("ERROR: TELEGRAM_CHAT_ID env var not set (use --chat-id or env var)", file=sys.stderr)
        return 2

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": args.message,
        "disable_notification": args.silent,
        "parse_mode": "HTML",
    }
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            body = r.read().decode()
            if '"ok":true' in body:
                print("OK")
                return 0
            print(f"ERROR: {body}", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
