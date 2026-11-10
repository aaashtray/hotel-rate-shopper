import base64
import json
import shutil
from pathlib import Path
from typing import Any


def write_html(report: dict[str, Any], output: Path) -> None:
    root = Path(__file__).parent
    def expand(template: str) -> str:
        # Recursive substitution keeps each delivered HTML autonomous and offline.
        for token, filename in (
            ("__ANALYTICS_JS__", "analytics.js"), ("__FILTER_UI_JS__", "filter-ui.js"),
            ("__TARIFF_COMPARISON_JS__", "tariff-comparison.js"),
            ("__ANALYTICS_CORE_JS__", "analytics-core.js"), ("__MAP_JS__", "maps.js"),
            ("__LAYOUT_CSS__", "layout.css"), ("__MAP_CSS__", "maps.css"),
            ("__MAP_DATA__", "map-geometry.json"),
        ):
            if token in template:
                template = template.replace(token, (root / filename).read_text())
        return template
    template = expand((root / "dashboard.html").read_text())
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
    for source, destination in (("statistics.html", "hotel-statistics-otello.html"),
                                ("maps.html", "hotel-map-otello.html")):
        page = expand((root / source).read_text()).replace("__REPORT_DATA__", data)
        for font in assets.glob("*.ttf"):
            page = page.replace(
                f"assets/{font.name}",
                "data:font/ttf;base64," + base64.b64encode(font.read_bytes()).decode("ascii"),
            )
        (output / destination).write_text(page)
