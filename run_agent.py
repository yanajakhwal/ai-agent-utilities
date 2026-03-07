#!/usr/bin/env python3
"""
CLI to run the regulatory document agent.

Usage:
  python run_agent.py "Hi Agent, can you give me Other Documents from M12205?"
  python run_agent.py --headed "..."   # show browser window (for debugging)

Without SMTP env vars set, the agent will still parse, scrape, and create the ZIP;
it just won't send an email. Set SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
and optionally TO_ADDRESS to send the result by email.
"""

import argparse
import os
import sys
from pathlib import Path

# Run from repo root so "agent" package is on the path
_repo_root = Path(__file__).resolve().parent
sys.path.insert(0, str(_repo_root))

# Load .env from the ai-agent-utilities directory (so email config works)
try:
    from dotenv import load_dotenv
    load_dotenv(_repo_root / ".env")
except ImportError:
    pass

from agent.orchestrator import run_agent

def main() -> None:
    parser = argparse.ArgumentParser(description="Run the regulatory document agent.")
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Show the browser window (useful for debugging when the site times out).",
    )
    parser.add_argument(
        "message",
        nargs="+",
        help="Email-style message, e.g. 'Give me Other Documents from M12205'.",
    )
    args = parser.parse_args()

    message = " ".join(args.message)
    download_root = Path("./downloads").resolve()

    smtp_config = None
    to_address = os.environ.get("EMAIL_TO") or os.environ.get("TO_ADDRESS", "requester@example.com")
    if os.environ.get("SMTP_HOST") and os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASSWORD"):
        smtp_config = {
            "host": os.environ["SMTP_HOST"],
            "port": int(os.environ.get("SMTP_PORT", "465")),
            "user": os.environ["SMTP_USER"],
            "password": os.environ["SMTP_PASSWORD"],
        }

    print("Running agent...")
    print(f"  Message: {message}")
    print(f"  Download root: {download_root}")
    print(f"  Headed (visible browser): {args.headed}")
    print(f"  Email: {'yes' if smtp_config else 'no (set SMTP_* env vars to send)'}")
    print()

    result = run_agent(
        email_text=message,
        download_root=download_root,
        smtp_config=smtp_config,
        to_address=to_address if smtp_config else None,
        headless=not args.headed,
    )

    print("Done.")
    print(f"  ZIP: {result['zip_path']}")
    print(f"  Files downloaded: {result['file_count']}")
    print(f"  Email sent: {'yes' if result.get('email_sent') else 'no'}")
    print(f"  Email draft: {result.get('email_draft', 'n/a')}")
    print()
    print("--- Email body ---")
    print(result.get("email_body", "(none)"))


if __name__ == "__main__":
    main()
