from __future__ import annotations

import sys

from .command import history
from .config import Config


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] != "history":
        sys.stderr.write("Usage: python -m alembic history\n")
        return 1

    cfg = Config("alembic.ini")
    for line in history(cfg):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
