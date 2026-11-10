import argparse
import csv
import json
import sys
from pathlib import Path
from time import perf_counter

from pydantic import ValidationError

from rate_shopper.pipeline import run


def main() -> int:
    if sys.argv[1:2] == ["collect"]:
        from rate_shopper.connectors.browser import main as collect_main

        return collect_main(sys.argv[2:])
    if sys.argv[1:2] == ["report-batch"]:
        from rate_shopper.cli.batch import main as batch_main

        return batch_main(sys.argv[2:])
    if any(a in {"--capture-yandex", "--replay-capture"} for a in sys.argv[1:]):
        from rate_shopper.cli.observed import main as observed_main

        return observed_main(sys.argv[1:])
    parser = argparse.ArgumentParser(description="Synthetic offline Hotel Rate Shopper")
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--output", type=Path, default=Path("reports"))
    args = parser.parse_args()
    started = perf_counter()
    try:
        report = run(args.fixture, args.output)
    except (OSError, ValueError, ValidationError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 2
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with (args.output / "report.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["hotel", "competitor", "quality", "absolute_gap", "percent_gap", "review"])
        print(f"{report['status']} | SYNTHETIC domain fixtures | {report['run_id'][:24]}")
        print(f"{'HOTEL':15} {'COMPETITOR':15} {'QUALITY':10} {'GAP RUB':>10} {'GAP %':>8} REVIEW")
        for match in report["matches"]:
            row = [
                match["hotel_canonical_id"],
                match["competitor_offer_id"],
                match["match_quality"],
                match["absolute_gap"],
                match["percent_gap"],
                match["manual_review_required"],
            ]
            writer.writerow(row)
            print(
                f"{str(row[0]):15} {str(row[1]):15} {row[2]:10} "
                f"{row[3] or '—':>10} {row[4] or '—':>8} {row[5]}"
            )
        print(
            "Availability:",
            ", ".join(
                f"{o['id']}={o['availability_status']}"
                for o in report["offers"]
                if o["availability_status"] != "AVAILABLE"
            ),
        )
    duration = perf_counter() - started
    # Attempt timing is separate from the deterministic, replayable report.
    with (args.output / "attempts.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"run_id": report["run_id"], "duration_seconds": duration}) + "\n")
    print(f"JSON: {args.output / 'report.json'} | duration: {duration:.3f}s")
    return 2 if report["status"] == "FAILED" else 1 if report["status"] == "PARTIAL_SUCCESS" else 0


if __name__ == "__main__":
    sys.exit(main())
