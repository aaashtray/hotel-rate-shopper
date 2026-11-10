import argparse
import json
from pathlib import Path

from rate_shopper.batch import write_batch


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Replay observed browser captures into HTML/CSV/JSON"
    )
    parser.add_argument("--captures", type=Path, default=Path("data/browser"))
    parser.add_argument("--hotels", type=Path, default=Path("config/hotels.json"))
    parser.add_argument("--scenario", type=Path, default=Path("config/scenario.json"))
    parser.add_argument("--output", type=Path, default=Path("reports/current"))
    args = parser.parse_args(argv)
    report = write_batch(args.captures, args.hotels, args.scenario, args.output)
    print(
        json.dumps(
            {
                "status": report["status"],
                "metrics": report["metrics"],
                "html": str(args.output / "index.html"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 2 if report["status"] == "FAILED" else 1 if report["status"] == "PARTIAL_SUCCESS" else 0
