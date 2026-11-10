import argparse
import json
from pathlib import Path

from rate_shopper.connectors.yandex_travel.capture import YandexConnector
from rate_shopper.domain.models import HotelEntity, Scenario
from rate_shopper.observed_pipeline import replay


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="M2: public capture or offline observed replay")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--capture-yandex")
    mode.add_argument("--replay-capture", type=Path)
    parser.add_argument("--scenario", type=Path)
    parser.add_argument("--output", type=Path, default=Path("reports/observed"))
    args = parser.parse_args(argv)
    try:
        manifest = args.replay_capture
        if args.capture_yandex:
            if args.scenario is None:
                raise ValueError("--scenario is required for capture")
            data = json.loads(args.scenario.read_text())
            scenario = Scenario.model_validate(data.get("scenario", data))
            connector = YandexConnector(args.capture_yandex, args.output / "evidence")
            connector.capture(
                HotelEntity(canonical_id="unresolved", canonical_name="", city=""), scenario
            )
            manifest = connector.manifest_path
        report = replay(manifest, args.output)
        print(f"{report['status']} | OBSERVED | {report['observation_status']}")
        print(report["reason"])
        print(f"Extracted tariffs: 0 | JSON: {args.output / 'report.json'}")
        return 2
    except (OSError, ValueError) as exc:
        print(f"FAILED: {exc}")
        return 2
