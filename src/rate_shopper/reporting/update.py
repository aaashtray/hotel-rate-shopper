"""Prepare a sanitized site update, retaining the previous published snapshot."""

import argparse
import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path

from rate_shopper.reporting.html import write_html
from rate_shopper.reporting.publication import public_report

FILES = (
    "index.html", "hotel-interface-otello.html", "hotel-statistics-otello.html",
    "hotel-map-otello.html", "report.json", "hotel-rates.xlsx", "парсер цен.html",
)


def prepare_update(source: Path, site: Path) -> None:
    report = json.loads((source / "report.json").read_text())
    if report["collection_status"] == "FAILED" or not report["offers"]:
        raise ValueError("Refusing to replace the published report with a failed run")
    if not (source / "hotel-rates.xlsx").is_file():
        raise ValueError("Export the matching Excel workbook before publication")
    manifest_path = source / "workbook-manifest.json"
    if not manifest_path.is_file():
        raise ValueError("Export the matching Excel workbook with its manifest")
    manifest = json.loads(manifest_path.read_text())
    for filename, key in (("report.json", "report_sha256"), ("hotel-rates.xlsx", "xlsx_sha256")):
        if hashlib.sha256((source / filename).read_bytes()).hexdigest() != manifest.get(key):
            raise ValueError("Excel workbook and report must belong to the same snapshot")
    projected = public_report(report, include_conditional=True)
    site.mkdir(parents=True, exist_ok=True)
    old = site / "report.json"
    if old.exists():
        previous = json.loads(old.read_text())
        old_id = previous.get("monitoring", {}).get("snapshot_id") or previous["checked_at"][:10]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", old_id):
            raise ValueError("Invalid archive identifier")
        current_id = projected.get("monitoring", {}).get("snapshot_id")
        if old_id != current_id:
            archive = site / "history" / old_id
            archive.mkdir(parents=True, exist_ok=True)
            for name in FILES:
                original, dest = site / name, archive / name
                if not original.exists():
                    continue
                content = original.read_bytes()
                if original.suffix == ".html":
                    content = content.replace(b'href="history/', b'href="../../history/')
                if dest.exists() and dest.read_bytes() != content:
                    raise ValueError(f"Immutable archive conflict: {name}")
                if not dest.exists():
                    dest.write_bytes(content)
            if (site / "assets").exists() and not (archive / "assets").exists():
                shutil.copytree(site / "assets", archive / "assets")
            projected.setdefault("monitoring", {})["previous_snapshot_url"] = (
                f"history/{old_id}/hotel-interface-otello.html"
            )
        elif previous.get("monitoring", {}).get("previous_snapshot_url"):
            projected["monitoring"]["previous_snapshot_url"] = previous["monitoring"][
                "previous_snapshot_url"
            ]
    # Fully render into staging before replacing current files. Git deployment is atomic.
    with tempfile.TemporaryDirectory(prefix="hotel-publication-") as temporary:
        staging = Path(temporary)
        write_html(projected, staging)
        (staging / "report.json").write_text(json.dumps(projected, ensure_ascii=False) + "\n")
        shutil.copy2(source / "hotel-rates.xlsx", staging / "hotel-rates.xlsx")
        for name in FILES:
            shutil.copy2(staging / name, site / name)
        shutil.copytree(staging / "assets", site / "assets", dirs_exist_ok=True)
        (site / ".nojekyll").touch()


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare an update of the existing dashboard")
    parser.add_argument("source", type=Path)
    parser.add_argument("site", type=Path)
    args = parser.parse_args()
    prepare_update(args.source, args.site)


if __name__ == "__main__":
    main()
