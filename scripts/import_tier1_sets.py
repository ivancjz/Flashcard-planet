"""Import all Tier 1 Pokemon TCG sets into the assets table.

Runs import_pokemon_cards.py once per set with a 30-second pause between
sets to be friendly to the Pokemon TCG API rate limits.

Usage:
    python scripts/import_tier1_sets.py
    python scripts/import_tier1_sets.py --dry-run
    python scripts/import_tier1_sets.py --start-from swsh11
    python scripts/import_tier1_sets.py --api-key YOUR_KEY

Set order (smallest first to verify setup quickly):
    sm115   Hidden Fates      ~69 cards
    swsh45  Shining Fates     ~73 cards
    swsh12pt5 Crown Zenith   ~160 cards
    swsh9   Brilliant Stars   ~186 cards
    swsh10  Astral Radiance   ~216 cards
    swsh11  Lost Origin       ~217 cards
    swsh12  Silver Tempest    ~215 cards
    swsh7   Evolving Skies    ~237 cards
    sv3     Obsidian Flames   ~230 cards
    sv2     Paldea Evolved    ~279 cards

Estimated total: ~1,882 cards, ~30-45 minutes at default rate limits.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

# Ordered smallest-first so issues surface fast.
TIER1_SETS: list[tuple[str, str]] = [
    ("sm115",     "Hidden Fates"),
    ("swsh45",    "Shining Fates"),
    ("swsh12pt5", "Crown Zenith"),
    ("swsh9",     "Brilliant Stars"),
    ("swsh10",    "Astral Radiance"),
    ("swsh11",    "Lost Origin"),
    ("swsh12",    "Silver Tempest"),
    ("swsh7",     "Evolving Skies"),
    ("sv3",       "Obsidian Flames"),
    ("sv2",       "Paldea Evolved"),
]

SLEEP_BETWEEN_SETS = 30  # seconds


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import all Tier 1 Pokemon TCG sets."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Pass --dry-run to each import call; no DB writes.",
    )
    parser.add_argument(
        "--start-from",
        type=str,
        default=None,
        metavar="SET_ID",
        help="Skip all sets before this set ID (resume after interruption).",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="Optional Pokemon TCG API key.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_root = Path(__file__).resolve().parents[1]
    import_script = project_root / "scripts" / "import_pokemon_cards.py"

    sets_to_run = TIER1_SETS
    if args.start_from:
        ids = [s[0] for s in TIER1_SETS]
        if args.start_from not in ids:
            print(f"ERROR: --start-from {args.start_from!r} not found in Tier 1 set list.")
            print(f"Valid IDs: {', '.join(ids)}")
            sys.exit(1)
        start_idx = ids.index(args.start_from)
        sets_to_run = TIER1_SETS[start_idx:]
        print(f"Resuming from {args.start_from} ({len(sets_to_run)} sets remaining).")

    total = len(sets_to_run)
    print(f"Importing {total} Tier 1 sets {'(DRY RUN)' if args.dry_run else ''}.")
    print()

    failed: list[str] = []
    for i, (set_id, set_name) in enumerate(sets_to_run, start=1):
        print(f"[{i}/{total}] {set_name} ({set_id})")
        cmd = [sys.executable, str(import_script), "--set-id", set_id]
        if args.dry_run:
            cmd.append("--dry-run")
        if args.api_key:
            cmd.extend(["--api-key", args.api_key])

        result = subprocess.run(cmd, check=False)
        if result.returncode != 0:
            print(f"  ERROR: import for {set_id} exited with code {result.returncode}.")
            failed.append(set_id)
        else:
            print(f"  OK: {set_name} import completed.")

        if i < total:
            print(f"  Sleeping {SLEEP_BETWEEN_SETS}s before next set...")
            time.sleep(SLEEP_BETWEEN_SETS)

    print()
    if failed:
        print(f"Completed with errors. Failed sets: {', '.join(failed)}")
        print(f"Re-run with --start-from {failed[0]} to retry from the first failure.")
        sys.exit(1)
    else:
        print(f"All {total} sets imported successfully.")


if __name__ == "__main__":
    main()
