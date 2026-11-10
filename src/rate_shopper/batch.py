import csv
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from rate_shopper.domain.capture import BatchConfig, BrowserCapture
from rate_shopper.domain.models import Offer, Platform, Scenario, Status
from rate_shopper.extraction.browser import capture_status, extract
from rate_shopper.matching.rules import match
from rate_shopper.quality.gates import issues
from rate_shopper.reporting.statistics import statistics_bundle
from rate_shopper.storage.history import save_run

STATUS_REASONS = {
    Status.HOTEL_NOT_FOUND: "Источник сообщает, что страницы отеля нет",
    Status.SOLD_OUT: "Источник явно сообщает, что на эти даты нет номеров",
    Status.CAPTCHA: "Сайт запросил CAPTCHA. Сбор остановлен",
    Status.PRICE_NOT_EXPOSED: "Карточка открыта, но тарифы не получены",
    Status.UNKNOWN: "Название, география или адрес требуют проверки",
    Status.SCENARIO_MISMATCH: "Даты, гости или длительность не подтверждены",
    Status.PARSE_ERROR: "Тарифные блоки получены, цена не разобрана",
}


def load_captures(directory: Path) -> list[tuple[Path, BrowserCapture]]:
    captures = []
    for path in sorted(directory.glob("*.json")):
        data = json.loads(path.read_text())
        if isinstance(data, dict) and "cards" in data:
            captures.append((path, BrowserCapture.model_validate(data)))
    return captures


def write_batch(
    directory: Path, config_path: Path, scenario_path: Path, output: Path
) -> dict[str, Any]:
    config = BatchConfig.model_validate_json(config_path.read_bytes())
    scenario = Scenario.model_validate_json(scenario_path.read_bytes())
    captures = load_captures(directory)
    if any(c.provenance != "observed" for _, c in captures):
        raise ValueError("Live batch refuses synthetic captures")
    output.mkdir(parents=True, exist_ok=True)
    evidence_dir = output / "evidence"
    evidence_dir.mkdir(exist_ok=True)
    offers: list[Offer] = []
    observations: list[dict[str, Any]] = []
    rejected_captures = []
    used: set[Path] = set()
    for hotel in config.hotels:
        for platform in config.platforms:
            url = hotel.urls.get(platform)
            candidates = [
                (p, c)
                for p, c in captures
                if url
                and c.platform == platform
                and urlsplit(c.requested_url or c.url).path.rstrip("/")
                == urlsplit(url).path.rstrip("/")
                and urlsplit(c.requested_url or c.url).hostname == urlsplit(url).hostname
            ]
            candidates.sort(key=lambda item: item[1].checked_at)
            if not candidates:
                observations.append(
                    dict(
                        hotel_id=hotel.id,
                        hotel=hotel.name,
                        platform=platform,
                        status="UNKNOWN",
                        offer_count=0,
                        source_url=url,
                        discovery_status="candidate_found" if url else "search_pending",
                        mapping_note=hotel.mapping_notes.get(platform, ""),
                        reason=("Карточка найдена, тарифы ещё не собраны" if url
                                else "Поиск карточки не завершён"),
                        checked_at=None,
                        evidence=None,
                    )
                )
                continue
            path, capture = candidates[-1]
            used.add(path)
            content = path.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            evidence = evidence_dir / f"{digest}.json"
            if evidence.exists() and evidence.read_bytes() != content:
                raise ValueError("Evidence integrity failure")
            if not evidence.exists():
                evidence.write_bytes(content)
            status = capture_status(capture, scenario, hotel)
            parsed = extract(capture, scenario, hotel, digest)
            if status == Status.AVAILABLE and not parsed:
                status = Status.PARSE_ERROR
            offers.extend(parsed)
            observations.append(
                dict(
                    hotel_id=hotel.id,
                    hotel=hotel.name,
                    platform=platform.value,
                    status=status.value,
                    offer_count=len(parsed),
                    source_url=capture.requested_url or capture.url,
                    final_url=capture.url,
                    reason="" if parsed else STATUS_REASONS.get(
                        status, capture.collection_error or status.value
                    ),
                    checked_at=capture.checked_at.isoformat(),
                    evidence=f"evidence/{digest}.json",
                    content_hash=digest,
                    coverage=capture.coverage,
                    capture_method=capture.capture_method,
                    authorization_state=capture.authorization_state,
                    discovery_status="candidate_found",
                    mapping_note=hotel.mapping_notes.get(platform, ""),
                )
            )
    for path, capture in captures:
        if path not in used:
            rejected_captures.append(
                dict(
                    file=path.name,
                    title=capture.title,
                    reason="Не выбран: другой объект либо более старое наблюдение",
                )
            )
    checked = max((c.checked_at for _, c in captures), default=datetime.now(UTC))
    matches = []
    for hotel in config.hotels:
        references = [
            o for o in offers if o.hotel_canonical_id == hotel.id and o.platform == Platform.OTELLO
        ]
        competitors = [
            o for o in offers if o.hotel_canonical_id == hotel.id and o.platform != Platform.OTELLO
        ]
        for reference in references:
            # Only same category candidates; unrelated room pairs never flood manual review.
            for competitor in competitors:
                if reference.room_category_normalized != competitor.room_category_normalized:
                    continue
                if reference.meal_plan != competitor.meal_plan:
                    continue
                result = match(reference, competitor, scenario, checked, require_registration=True)
                matches.append(result.model_dump(mode="json"))
    quality = {
        o.id: issues(o, scenario)
        + ([] if o.registration else ["registration ID not confirmed in source"])
        for o in offers
    }
    counts = Counter(o["status"] for o in observations)
    extracted_observations = counts["AVAILABLE"] + counts["SOLD_OUT"]
    business_success = sum(not quality[o.id] for o in offers) + counts["SOLD_OUT"]
    expected = len(config.hotels) * len(config.platforms)
    report: dict[str, Any] = {
        "schema_version": 6,
        "platforms": [p.value for p in config.platforms],
        "provenance": "observed",
        "checked_at": checked.isoformat(),
        "scenario": scenario.model_dump(mode="json"),
        "hotels": [h.model_dump(mode="json") for h in config.hotels],
        "observations": observations,
        "offers": [o.model_dump(mode="json") for o in offers],
        "matches": matches,
        "quality_issues": quality,
        "rejected_captures": rejected_captures,
        "excluded_platforms": config.excluded_platforms,
        "status": "PARTIAL_SUCCESS" if business_success else "FAILED",
        "collection_status": "SUCCESS"
        if extracted_observations == expected
        else "PARTIAL_SUCCESS"
        if extracted_observations
        else "FAILED",
        "metrics": {
            "expected_observations": expected,
            "captured_observations": len(used),
            "extracted_offers": len(offers),
            "available": counts["AVAILABLE"],
            "sold_out": counts["SOLD_OUT"],
            "unresolved": expected - extracted_observations,
            "comparable_pairs": sum(m["percent_gap"] is not None for m in matches),
            "review_pairs": sum(m["manual_review_required"] for m in matches),
        },
        "notes": [
            "Цены за весь период среди загруженных тарифов; скрытые тарифы могут отсутствовать.",
            "Яндекс: текст видимых тарифов и частичная ручная транскрипция обычной сессии "
            "Safari с выполненным входом. Условия графических цен Пэй подтверждены не везде; "
            "неподтверждённые дополнительные суммы не включены.",
            "Островок: публичные тарифы из колонок таблицы; баннер ГУРУ не является тарифом.",
            "Строгие сравнения отделены от предварительных минимумов; "
            "типы доступа к цене разделены.",
            "Налоги и точное время отмены не подтверждены для большинства тарифов.",
        ],
    }
    report["statistics"] = statistics_bundle(offers, config, observations, matches)
    seed_path = config_path.with_name("registration-seeds.json")
    report["registration_references"] = (
        json.loads(seed_path.read_text()) if seed_path.exists() else []
    )
    digest = hashlib.sha256(json.dumps(report, sort_keys=True).encode()).hexdigest()
    report["run_id"] = f"browser-v3-{digest}"
    save_run(output / "history.sqlite3", report["run_id"], report)
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    with (output / "offers.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "Отель",
                "Страна",
                "Гео",
                "Звёзды",
                "Площадка",
                "Номер",
                "Питание",
                "Отмена",
                "Цена RUB",
                "Доступ",
                "Цена в сессии RUB",
                "Цена банка RUB",
                "Дополнительные сборы (валюта источника)",
                "Источник",
            ]
        )
        for offer in offers:
            # Prevent spreadsheet formula injection in source-derived strings.
            hotel = next(h for h in config.hotels if h.id == offer.hotel_canonical_id)
            row = [
                hotel.name,
                hotel.country,
                hotel.geo,
                hotel.stars,
                offer.platform.value,
                offer.room_name_raw,
                offer.meal_plan,
                offer.cancellation_type,
                offer.public_total,
                offer.access_type,
                offer.member_total,
                offer.bank_product_total,
                offer.source_fragments.get("additional_fees", ""),
                offer.source_url,
            ]
            writer.writerow(
                [
                    "'" + v if isinstance(v, str) and v.startswith(("=", "+", "-", "@")) else v
                    for v in row
                ]
            )
    from rate_shopper.reporting.html import write_html

    write_html(report, output)
    return report
