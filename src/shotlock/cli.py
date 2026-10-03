"""Command line entry point.

    python -m shotlock.cli inspect PATH
    python -m shotlock.cli validate-intent INTENT.json
    python -m shotlock.cli run --intent INTENT.json --source SRC --candidate CAND \\
        --store STORE_DIR [--out EXPORT_DIR] [--backend imported] [--budget 500]

The `run` command is the filmmaker flow in one shot: validate, check budget and
approval binding, ingest, run deterministic checks, record immutable evidence,
and export the review package.
"""
from __future__ import annotations

import argparse
import json
import sys

from .export import export_package
from .intent import validate_intent
from .media import FfprobeMissing, inspect_media
from .pipeline import DEFAULT_BUDGET_CAD, PipelineError, process_edit
from .store import EvidenceStore, sha256_file


def _cmd_inspect(args: argparse.Namespace) -> int:
    try:
        print(json.dumps(inspect_media(args.path), indent=2))
        return 0
    except (FfprobeMissing, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _cmd_validate_intent(args: argparse.Namespace) -> int:
    record = json.loads(open(args.intent).read())
    errors = validate_intent(record)
    if errors:
        print("intent record INVALID:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("intent record valid")
    return 0


def _cmd_digest(args: argparse.Namespace) -> int:
    print(sha256_file(args.path))
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    store = EvidenceStore(args.store)
    intent = json.loads(open(args.intent).read())
    try:
        result = process_edit(
            store,
            intent,
            args.source,
            args.candidate,
            backend_name=args.backend,
            budget_ceiling_cad=args.budget,
        )
    except (PipelineError, ValueError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1

    report = result["report"]
    summary = {
        "run_id": report["run_id"],
        "report_id": report["report_id"],
        "checks_run": report["checks_run"],
        "findings": len(report["findings"]),
        "hard_failures": sum(
            1 for f in report["findings"] if f["constraint"]["class"] == "hard"
        ),
        "missing_checks": [m["check"] for m in report["missing_checks"]],
    }
    if args.out:
        manifest = export_package(
            report, args.candidate, args.out, source_path=args.source, intent=intent
        )
        summary["export"] = {k: v for k, v in manifest["files"].items()}
        summary["viewer"] = manifest["viewer"]["status"]
        summary["otio_timeline"] = manifest["otio_timeline"]["status"]
    print(json.dumps(summary, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="shotlock", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("inspect", help="inspect media via ffprobe")
    p.add_argument("path")
    p.set_defaults(func=_cmd_inspect)

    p = sub.add_parser("validate-intent", help="validate an intent record")
    p.add_argument("intent")
    p.set_defaults(func=_cmd_validate_intent)

    p = sub.add_parser("digest", help="print the digest of a file")
    p.add_argument("path")
    p.set_defaults(func=_cmd_digest)

    p = sub.add_parser("run", help="process one candidate end to end")
    p.add_argument("--intent", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--candidate", required=True)
    p.add_argument("--store", required=True, help="evidence store directory")
    p.add_argument("--out", help="export package directory")
    p.add_argument("--backend", default="imported")
    p.add_argument("--budget", type=float, default=DEFAULT_BUDGET_CAD, help="compute budget ceiling in CAD")
    p.set_defaults(func=_cmd_run)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
