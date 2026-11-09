"""Command Line Interface for MamakScore Evaluation Pipeline with Full Audit Ledger."""

import argparse
import itertools
import os
import re
import sys
import threading
import time
import traceback
from decimal import Decimal
from pathlib import Path

from mamakscore.cache import SQLiteReplayCache
from mamakscore.confidence import SEVERITY_PENALTIES
from mamakscore.extraction import OpenAIVisionExtractor
from mamakscore.pipeline import EvaluationPipeline
from mamakscore.provider import OfflineProvider, OpenAICompatibleProvider
from mamakscore.report import render_report_html
from mamakscore.rubric import load_default_rubric
from mamakscore.scoring import classify_score


class ProgressTimer:
    """Non-blocking terminal status indicator tracking elapsed time."""

    def __init__(self, message: str = "Evaluating pitch deck"):
        self.message = message
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._start_time: float = 0.0

    def start(self) -> None:
        self._start_time = time.time()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._animate, daemon=True)
        self._thread.start()

    def _animate(self) -> None:
        spinner = itertools.cycle(["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"])
        while not self._stop_event.is_set():
            elapsed = time.time() - self._start_time
            sys.stdout.write(f"\r  {next(spinner)} {self.message}... ({elapsed:.1f}s elapsed)")
            sys.stdout.flush()
            time.sleep(0.1)

    def stop(self) -> float:
        self._stop_event.set()
        if self._thread:
            self._thread.join()
        total_time = time.time() - self._start_time
        sys.stdout.write(f"\r  ✓ {self.message} finished in {total_time:.2f}s\n")
        sys.stdout.flush()
        return total_time


def print_detailed_audit_ledger(result, rubric) -> None:
    """Prints step-by-step scoring breakdown and penalty telemetry to stdout."""
    weight_map = {c.id: Decimal(str(c.weight)) for c in rubric.criteria}

    print("\n" + "=" * 80)
    print("           MAMAKSCORE DETERMINISTIC CALCULATION LEDGER (v2.0)")
    print("=" * 80)
    print(f"{'CRITERION':<16} | {'SCORE':<7} | {'WEIGHT':<8} | {'CONTRIBUTION':<14} | EVIDENCE STATUS")
    print("-" * 80)

    computed_sum = Decimal("0.0")
    for cs in result.criterion_scores:
        w = weight_map.get(cs.criterion_id, Decimal("10.0"))
        contrib = (Decimal(str(cs.score)) / Decimal("10.0")) * w
        computed_sum += contrib
        has_quote = "✓ Cited" if (cs.evidence_quote or "").strip() else "✗ Missing Quote (0/10)"
        print(f"{cs.criterion_id:<16} | {cs.score:>2}/10  | {w:>5.1f}%  | {contrib:>6.2f} pts      | {has_quote}")

    print("-" * 80)
    print(f"{'UNCAPPED WEIGHTED SCORE:':<35} {computed_sum:.1f} / 100.0")

    # Critical Red Flag Dual-Gate Enforcement
    has_critical = any(
        (getattr(rf, "severity", "") or (rf.get("severity") if isinstance(rf, dict) else "")).lower() == "critical"
        for rf in result.red_flags
    )
    if has_critical:
        print(f"{'CRITICAL FLAW DUAL-GATE:':<35} ACTIVATED (Score capped to max 39.9)")
        final_score = min(result.mamak_score, Decimal("39.9"))
        result.mamak_score = final_score
        result.band = classify_score(final_score)

    print(f"{'FINAL COMPOSITE MAMAKSCORE:':<35} {result.mamak_score} / 100.0  (Exact Decimal)")
    print(f"{'ASSIGNED DUE DILIGENCE BAND:':<35} {result.band.band_name.upper()}")
    print("=" * 80)

    print("\n" + "=" * 80)
    print("           CONFIDENCE CALIBRATION & RISK PENALTY TELEMETRY")
    print("=" * 80)

    # 1. Base factors
    verified_quotes = len([s for s in result.criterion_scores if (s.evidence_quote or "").strip()])
    has_model = bool(result.financials and getattr(result.financials, "provided", False))
    cat_ratio = Decimal(min(verified_quotes, 9)) / Decimal("9")
    quote_depth = Decimal(min(verified_quotes, 18)) / Decimal("18")
    g_score = (Decimal("0.75") * cat_ratio) + (Decimal("0.25") * quote_depth)
    f_score = Decimal("0.0") if not has_model else Decimal("1.0")

    w_g = Decimal("0.40") / Decimal("0.75")
    w_f = Decimal("0.35") / Decimal("0.75")
    base_conf = ((w_g * g_score) + (w_f * f_score)) * Decimal("100.0")

    print("1. BASE EVIDENCE & COMPLETENESS (NO MORAL HAZARD MARKS):")
    print(f"   - Quote Breadth & Depth (G) : {verified_quotes}/9 criteria grounded  --> {float(g_score)*100:.1f}%")
    print(f"   - Financial Completeness (F): {'Model Submitted' if has_model else 'NO MODEL SUBMITTED (Strict 0.0%)'} --> {float(f_score)*100:.1f}%")
    print(f"   - Consistency Checks (C)    : INACTIVE (<3 comparisons)   --> Weight redistributed to G & F")
    print(f"   - Dynamic Redistribution    : w_g = {float(w_g):.4f}, w_f = {float(w_f):.4f}, w_c = 0.0000")
    print(f"   -------------------------------------------------------------------")
    print(f"   - UNPENALIZED BASE CONFIDENCE: {float(base_conf):.1f}%")

    # 2. Risk Penalties
    print("\n2. CATEGORIZED RED FLAG MULTIPLIERS (PHI):")
    phi = Decimal("1.0")
    if not result.red_flags:
        print("   ✓ None detected (Multiplier = 1.00)")
    else:
        for idx, rf in enumerate(result.red_flags, 1):
            sev = (getattr(rf, "severity", "medium") or "medium").lower()
            p_k = SEVERITY_PENALTIES.get(sev, Decimal("0.12"))
            phi *= (Decimal("1.0") - p_k)
            summary = getattr(rf, "summary", str(rf))
            trigger = getattr(rf, "trigger_mechanism", "Direct violation")
            label = f"{sev.upper()} (-{int(p_k*100)}%)"
            print(f"   [{idx}] {label}")
            print(f"       Flag    : {summary}")
            print(f"       Trigger : {trigger}")
            print(f"       Impact  : phi_penalty *= {float(Decimal('1.0') - p_k):.2f}")

    phi = max(Decimal("0.02"), phi)
    final_conf = round(float(base_conf * phi), 1)
    print(f"   -------------------------------------------------------------------")
    print(f"   - AGGREGATE RISK MULTIPLIER (PHI) : {float(phi):.4f}")
    print(f"   - CALIBRATED INSTITUTIONAL CONFIDENCE: {final_conf:.1f}%")
    print("=" * 80 + "\n")

    # Synchronize calibrated metrics into the result container
    if hasattr(result, "mamak_confidence") and result.mamak_confidence:
        result.mamak_confidence.score = final_conf
        result.mamak_confidence.mamak_confidence = final_conf
    result.provisional_confidence = final_conf


def run_evaluate(args: argparse.Namespace) -> None:
    try:
        deck_path = Path(args.deck)
        if not deck_path.exists():
            print(f"Error: Pitch deck file not found at '{deck_path}'", file=sys.stderr)
            sys.exit(1)

        model_path = Path(args.model) if args.model else None
        rubric = load_default_rubric()

        # Derive dynamic application_id
        if args.app_id:
            application_id = args.app_id
        else:
            cleaned_stem = re.sub(r"[^a-zA-Z0-9]+", "_", deck_path.stem).strip("_").lower()
            application_id = f"eval_{cleaned_stem}"

        # 1. Setup Provider & Vision
        if args.mode == "live":
            api_key = os.getenv("OPENAI_API_KEY")
            base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
            model_name = os.getenv("OPENAI_MODEL", "gpt-4o")

            if not api_key:
                print("Error: OPENAI_API_KEY is not set in environment or .env file", file=sys.stderr)
                sys.exit(1)

            print(f"[1/4] Initializing live AI provider ({model_name})...")
            try:
                provider = OpenAICompatibleProvider(base_url, api_key, model_name)
            except TypeError:
                provider = OpenAICompatibleProvider(
                    base_url=base_url,
                    api_key=api_key,
                    model=model_name,
                )

            vision = OpenAIVisionExtractor(
                api_key=api_key,
                base_url=base_url,
                model_name=model_name,
            )
        else:
            print("[1/4] Running with offline fixture provider...")
            provider = OfflineProvider(rubric=rubric, deck_filename=deck_path.name)
            vision = None

        # 2. Replay Cache Setup
        cache = None if args.no_cache else SQLiteReplayCache()

        # 3. Instantiate Pipeline
        print(f"[2/4] Parsing '{deck_path.name}' ({application_id}) and executing pipeline...")
        pipeline = EvaluationPipeline(
            rubric=rubric,
            provider=provider,
            vision=vision,
            cache=cache,
            expose_confidence=True,
        )

        with open(deck_path, "rb") as f:
            deck_bytes = f.read()

        model_bytes = None
        model_filename = None
        if model_path and model_path.exists():
            with open(model_path, "rb") as f:
                model_bytes = f.read()
            model_filename = model_path.name

        timer = ProgressTimer(message=f"Extracting slides and running {args.mode.upper()} assessment")
        timer.start()
        try:
            result = pipeline.evaluate(
                application_id=application_id,
                pitch_deck_bytes=deck_bytes,
                pitch_deck_filename=deck_path.name,
                financial_model_bytes=model_bytes,
                financial_model_filename=model_filename,
                use_cache=not args.no_cache,
            )
        finally:
            timer.stop()

        # 4. Detailed Terminal Output
        print(f"[3/4] Evaluation complete.")
        print_detailed_audit_ledger(result, rubric)

        # 5. Save Output File
        if args.output:
            out_path = Path(args.output)
            print(f"[4/4] Writing assessment report to '{out_path}'...")
            if out_path.suffix.lower() == ".html":
                html_content = render_report_html(result)
                out_path.write_text(html_content, encoding="utf-8")
            else:
                out_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
            print(f"Successfully saved evaluation report to: {out_path.resolve()}")
        else:
            print(result.model_dump_json(indent=2))

    except Exception as e:
        print(f"\nExecution failed with error: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="MamakScore Institutional Due Diligence CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    eval_parser = subparsers.add_parser("evaluate", help="Evaluate a pitch deck and optional financial model")
    eval_parser.add_argument("--deck", required=True, help="Path to pitch deck PDF")
    eval_parser.add_argument("--model", required=False, default=None, help="Path to financial spreadsheet (.xlsx)")
    eval_parser.add_argument("--mode", choices=["offline", "live"], default="offline", help="Evaluation mode (offline or live)")
    eval_parser.add_argument("--app-id", required=False, default=None, help="Custom application ID (default: auto-derived from filename)")
    eval_parser.add_argument("--no-cache", action="store_true", help="Bypass reading or writing to SQLite replay cache")
    eval_parser.add_argument("--output", "-o", default=None, help="Path to save report output (.html or .json)")

    args = parser.parse_args()

    if args.command == "evaluate":
        run_evaluate(args)


if __name__ == "__main__":
    main()