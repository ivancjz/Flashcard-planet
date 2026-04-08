from __future__ import annotations

import sys
import unittest
from pathlib import Path


def _parse_args(argv: list[str]) -> tuple[list[str], int]:
    targets: list[str] = []
    verbosity = 1
    for arg in argv:
        if arg == "-v":
            verbosity = 2
            continue
        if arg.startswith("--tb="):
            continue
        if arg.startswith("-"):
            continue
        targets.append(arg)
    return targets or ["tests"], verbosity


def _suite_for_target(target: str) -> unittest.TestSuite:
    path = Path(target)
    if path.is_dir():
        return unittest.defaultTestLoader.discover(str(path), pattern="test*.py")
    if path.is_file():
        return unittest.defaultTestLoader.discover(
            str(path.parent or Path(".")),
            pattern=path.name,
        )
    return unittest.defaultTestLoader.discover("tests", pattern="test*.py")


def main(argv: list[str] | None = None) -> int:
    targets, verbosity = _parse_args(list(sys.argv[1:] if argv is None else argv))
    suite = unittest.TestSuite(_suite_for_target(target) for target in targets)
    result = unittest.TextTestRunner(verbosity=verbosity).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
