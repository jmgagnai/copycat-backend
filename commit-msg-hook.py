#!/usr/bin/env python
"""
Commit message must start with NBK-[0-9]+ unless it's a merge commit.
"""

import re
import sys


def validate_commit_message(message):
    if message.strip().startswith("Merge ") or message.strip().startswith("merge "):
        return True
    pattern = r"^NBK-\d+"
    return bool(re.match(pattern, message.strip()))


def main():
    file_path = sys.argv[1]
    try:
        with open(file_path, "r") as f:
            msg = f.read()
    except Exception as e:  # noqa: BLE001
        print(f"Cannot read message file: {e}", file=sys.stderr)
        sys.exit(1)

    if not validate_commit_message(msg):
        print("[ERROR] Bad message", file=sys.stderr)
        print(
            "\nMessage should start with 'NBK-[0-9]+' (e.g., NBK-117)", file=sys.stderr
        )
        print(f"\nFaulty message: {msg.strip()}", file=sys.stderr)
        print(
            "\nAlternatively there should be no check if it is a merge commit.",
            file=sys.stderr,
        )
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
