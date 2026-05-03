#!/usr/bin/env python3
"""new-session: viewfinder over sessions not yet processed by this filter.

Outputs session_ids that haven't been tagged with `_filter-new-session`.
The filter itself is just a selector — actually doing something with
each session (extracting cards, summarizing, etc.) is the user's job
between `filter run` and `filter mark`.
"""
import json
import subprocess
import sys


def main() -> int:
    proc = subprocess.run(
        ["memory-talk", "search", "",
         "--where", 'NOT (tag = "_filter-new-session")', "--json"],
        capture_output=True, text=True, check=True,
    )
    for s in json.loads(proc.stdout)["sessions"]["results"]:
        print(s["session_id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
