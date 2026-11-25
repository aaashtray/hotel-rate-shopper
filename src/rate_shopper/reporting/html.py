import base64
import json
import shutil
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


def write_html(report: dict[str, Any], output: Path) -> None:
    root = Path(__file__).parent
    monitoring = report.get("monitoring")
    banner = ""
    if monitoring:
        stamp = datetime.fromisoformat(report["checked_at"]).astimezone(
            ZoneInfo(monitoring.get("timezone", "Europe/Moscow"))
        ).strftime("%d.%m.%Y")
        banner = (
            '<p class="monitoring-note" style="margin-top:14px;max-width:950px">'
            f'Сбор: {stamp}. План обновлений: раз в две недели, понедельник, 09:00 МСК. '
            'Проживание — ближайшая пятница–воскресенье. '
            'В этом срезе обновлены Отелло и Островок; Яндекс и Ozon ожидают обновления.'
            '</p>'
        )
        previous = monitoring.get("previous_snapshot_url", "")
        # Only relative archive links authored by our publisher are accepted.
        if (isinstance(previous, str) and previous.startswith("history/")
                and ".." not in previous and ":" not in previous):
            banner += (f'<p style="margin-top:10px"><a style="color:#A7FC26" '
                       f'href="{escape(previous, quote=True)}">Предыдущий срез</a></p>')
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
        if banner:
            template = template.replace("</header>", banner + "</header>", 1)
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
