# Local command-line surface.
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .api import build_pipeline, create_app
from .comparison import compare_assessments
from .config import Settings
from .contracts import ComparisonRequest
from .errors import ServiceError


def _settings(args: argparse.Namespace) -> Settings:
    rubric = Path(args.rubric) if getattr(args, "rubric", None) else None
    hosted = bool(getattr(args, "hosted", False))
    if rubric is not None:
        return Settings(mode="hosted" if hosted else "offline", rubric_path=rubric)
    return Settings(mode="hosted" if hosted else "offline")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mamakscore")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check-config")
    check.add_argument("--rubric")
    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("pitch_deck")
    evaluate.add_argument("--financial-model")
    evaluate.add_argument("--application-id", default="local-demo")
    evaluate.add_argument("--rubric")
    evaluate.add_argument("--html", action="store_true")
    compare = sub.add_parser("compare")
    compare.add_argument("previous")
    compare.add_argument("current")
    compare.add_argument("--rubric")
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--rubric")
    serve.add_argument("--hosted", action="store_true")
    args = parser.parse_args(argv)
    try:
        settings = _settings(args)
        if args.command == "check-config":
            pipe = build_pipeline(settings)
            print(
                json.dumps(
                    {"status": "ok", "mode": settings.mode, "rubric_version": pipe.rubric.version}
                )
            )
            return 0
        if args.command == "evaluate":
            deck_path = Path(args.pitch_deck)
            finance_path = Path(args.financial_model) if args.financial_model else None
            result = build_pipeline(settings).evaluate(
                args.application_id,
                deck_path.read_bytes(),
                deck_path.name,
                finance_path.read_bytes() if finance_path else None,
                finance_path.name if finance_path else None,
            )
            print(result.report_html if args.html else result.model_dump_json(indent=2))
            return 0
        if args.command == "compare":
            old = json.loads(Path(args.previous).read_text())
            new = json.loads(Path(args.current).read_text())
            print(
                compare_assessments(ComparisonRequest(previous=old, current=new)).model_dump_json(
                    indent=2
                )
            )
            return 0
        import uvicorn

        uvicorn.run(create_app(settings), host=args.host, port=args.port)
        return 0
    except (ServiceError, ValueError, OSError) as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}))
        return 1
