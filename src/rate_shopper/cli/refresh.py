"""A fresh scenario and immutable capture directory for every monitoring run."""

import argparse
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rate_shopper.batch import write_batch
from rate_shopper.connectors.http_rates import collect_http
from rate_shopper.domain.capture import BatchConfig
from rate_shopper.reporting.html import write_html
from rate_shopper.scenarios.weekend import weekend_scenario
from rate_shopper.storage.history import save_run


def save_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Refresh next-weekend hotel prices")
    parser.add_argument("--hotels", type=Path, default=Path("config/hotels.json"))
    parser.add_argument("--settings", type=Path, default=Path("config/monitoring.json"))
    parser.add_argument("--data", type=Path, default=Path("data/monitoring"))
    parser.add_argument("--output", type=Path, default=Path("reports/monitoring"))
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--nights", type=int, choices=(2, 3), default=2)
    parser.add_argument("--replay", type=Path, help="Existing run containing captures and scenario")
    args = parser.parse_args(argv)
    args.data.mkdir(parents=True, exist_ok=True)
    lock = args.data / ".refresh.lock"
    try:
        with lock.open("x") as stream:
            stream.write(datetime.now(UTC).isoformat())
    except FileExistsError:
        print("FAILED: Another refresh is running; existing captures were not changed")
        return 2
    run_dir: Path | None = None
    try:
        settings = json.loads(args.settings.read_text())
        if args.replay:
            run_dir = args.replay
            run_id = run_dir.name
        else:
            now = datetime.now(UTC)
            run_id = f"{now:%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
            run_dir = args.data / run_id
            run_dir.mkdir()
            config = BatchConfig.model_validate_json(args.hotels.read_bytes())
            if args.pilot:
                ids = set(settings["pilot_hotel_ids"])
                config = config.model_copy(update={
                    "hotels": tuple(h for h in config.hotels if h.id in ids),
                })
                if len(config.hotels) != len(ids):
                    raise ValueError("Pilot contains unknown or duplicate hotels")
            scenario = weekend_scenario(now, nights=args.nights)
            (run_dir / "hotels.json").write_text(config.model_dump_json(indent=2))
            (run_dir / "scenario.json").write_text(scenario.model_dump_json(indent=2))
            save_json(run_dir / "manifest.json", {
                "status": "RUNNING", "run_id": run_id, "started_at": now.isoformat(),
            })
            collect_http(config, scenario, run_dir / "captures")
        destination = args.output / run_id
        report = write_batch(run_dir / "captures", run_dir / "hotels.json",
                             run_dir / "scenario.json", destination)
        report["monitoring"] = {
            "snapshot_id": run_id, "timezone": settings["timezone"],
            "interval_weeks": settings["interval_weeks"], "run_time": settings["run_time"],
            "stay": settings["stay"],
            "automatic_platforms": settings["automated_platforms"],
            "pending_platforms": [
                p for p in settings["manual_platforms"]
                if not any(o["platform"] == p and o.get("checked_at")
                           for o in report["observations"])
            ],
        }
        save_json(destination / "report.json", report)
        write_html(report, destination)
        summary = {
            "run_id": run_id, "status": report["collection_status"],
            "scenario": report["scenario"], "metrics": report["metrics"],
            "report_directory": str(destination.resolve()),
        }
        save_json(run_dir / "manifest.json", summary)
        save_run(args.data / "history.sqlite3", run_id, report)
        if report["collection_status"] != "FAILED":
            args.output.mkdir(parents=True, exist_ok=True)
            save_json(args.output / "latest.json", summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 2 if report["collection_status"] == "FAILED" else (
            1 if report["collection_status"] == "PARTIAL_SUCCESS" else 0
        )
    except (OSError, ValueError) as error:
        if run_dir is not None and run_dir.exists():
            save_json(run_dir / "manifest.json", {
                "status": "FAILED", "error": type(error).__name__,
                "finished_at": datetime.now(UTC).isoformat(),
            })
        print(f"FAILED: {error}")
        return 2
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv[1:]))
