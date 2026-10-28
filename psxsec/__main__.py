"""Command line: python -m psxsec {ingest|verify|build|analyze|report|notebook|all}"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="psxsec", description=__doc__)
    parser.add_argument("command", choices=["ingest", "verify", "build", "analyze", "report", "notebook", "all"])
    parser.add_argument("--refresh", action="store_true", help="download the raw files again")
    args = parser.parse_args(argv)

    if args.command == "ingest":
        from . import ingest
        ingest.run(refresh=args.refresh)
    elif args.command == "verify":
        from . import ingest
        problems = ingest.verify()
        print("\n".join(problems) if problems else "the raw files that are present match the manifest")
        return 1 if problems else 0
    elif args.command in ("build", "all"):
        from . import build
        build.run()
    if args.command in ("analyze", "all"):
        from . import analysis
        analysis.run()
    if args.command in ("report", "all"):
        from . import report
        report.run()
    if args.command == "notebook":
        from . import notebook
        notebook.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
