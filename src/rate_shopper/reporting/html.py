import base64
import json
import shutil
from pathlib import Path
from typing import Any


def write_html(report: dict[str, Any], output: Path) -> None:
    template = Path(__file__).with_name("dashboard.html").read_text()
    data = json.dumps(report, ensure_ascii=False).replace("<", "\\u003c")
    html = template.replace("__REPORT_DATA__", data)
    (output / "index.html").write_text(html)
    (output / "парсер цен.html").write_text(
        '<!doctype html><html lang="ru"><meta charset="utf-8">'
        '<meta http-equiv="refresh" content="0;url=index.html">'
        '<title>Hotel Rate Shopper — открыть отчёт</title>'
        '<a href="index.html">Открыть актуальный отчёт</a></html>'
    )
    assets = Path(__file__).with_name("assets")
    if assets.exists():
        shutil.copytree(assets, output / "assets", dirs_exist_ok=True)
        for font in assets.glob("*.ttf"):
            html = html.replace(
                f"assets/{font.name}",
                "data:font/ttf;base64," + base64.b64encode(font.read_bytes()).decode("ascii"),
            )
    (output / "hotel-interface-otello.html").write_text(html)
    statistics = Path(__file__).with_name("statistics.html").read_text().replace(
        "__REPORT_DATA__", data
    )
    for font in assets.glob("*.ttf"):
        statistics = statistics.replace(
            f"assets/{font.name}",
            "data:font/ttf;base64," + base64.b64encode(font.read_bytes()).decode("ascii"),
        )
    (output / "hotel-statistics-otello.html").write_text(statistics)
