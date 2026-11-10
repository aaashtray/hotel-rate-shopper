"""Parse user-visible Safari selection text; never fetch pages or infer prices."""

import re
from typing import Any

PRICE = re.compile(r"^\d[\d ]*(?:[,.]\d{1,2})? ₽$")
BANK = re.compile(r"^(\d[\d ]*(?:[,.]\d{1,2})? ₽) с$")


def normalize(text: str) -> list[str]:
    return [
        line for raw in text.splitlines() if (line := " ".join(raw.replace("\ufffc", "").split()))
    ]


def parse_selection(
    raw: dict[str, Any], nights: int = 2
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    lines = normalize(raw["text"])
    starts = sorted(
        {
            i - 1
            for i, line in enumerate(lines)
            if (line == "В номере:" or re.fullmatch(r"В каждом из \d+ номеров:", line)) and i
        }
        | {i + 1 for i, line in enumerate(lines[:-1]) if line == "нет фото"}
    )
    for i, line in enumerate(lines):
        if line == "Подробнее о предложении" and i:
            previous_booking = max((j for j in range(i) if lines[j] == "Забронировать"), default=0)
            if not any(
                line == "В номере:" or re.fullmatch(r"В каждом из \d+ номеров:", line)
                for line in lines[previous_booking:i]
            ):
                starts.append(i - 1)
    starts = sorted(set(starts))
    cards, unresolved_bank = [], []
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        block = lines[start:end]
        for marker in ("Занятые варианты размещений", "Об этом месте"):
            if marker in block:
                block = block[: block.index(marker)]
        meals = (
            "Без питания",
            "Включён завтрак",
            "Всё включено",
            "Все включено",
            "Завтрак и ужин",
            "Завтрак, обед и ужин",
            "Полупансион",
            "Включён завтрак, обед и ужин",
            "Включён завтрак и ужин",
            "Полный пансион",
            "Включён ужин",
        )
        split = next((i for i, line in enumerate(block) if line in meals), None)
        if split is None:
            continue
        room_lines = [line for line in block[:split] if line != "Подробнее о предложении"]
        room = re.sub(r"(\d+(?:[.,]\d+)?) м\n2\b", r"\1 м²", "\n".join(room_lines))
        rates = []
        for segment in "\n".join(block[split:]).split("Забронировать")[:-1]:
            rate_lines = normalize(segment)
            if not any(
                re.fullmatch(rf"за {nights} ноч(?:ь|и|ей)(?: и 1 номер)?", line)
                for line in rate_lines
            ):
                continue
            prices = [(i, line) for i, line in enumerate(rate_lines) if PRICE.fullmatch(line)]
            if not prices or len(prices) > 2:
                raise ValueError(f"Ambiguous primary price for {room}: {prices}")
            if len(prices) == 2:
                i, _ = prices[1]
                if not i or not re.fullmatch(r"(?:[−-]\d+)?%", rate_lines[i - 1]):
                    raise ValueError(f"Unverified crossed-out price: {room}")
            bank = [match.group(1) for line in rate_lines if (match := BANK.fullmatch(line))]
            # A copied SVG logo can be missing. Only label a bank price after a
            # screenshot independently confirms the logo on this observed page.
            text = "\n".join(line for line in rate_lines if not BANK.fullmatch(line))
            rates.append({"text": text, "price": "\n".join(p for _, p in prices)})
            if bank and raw.get("bank_label_confirmed") == "Яндекс Пэй":
                if len(bank) != 1:
                    raise ValueError("More than one bank price in a rate")
                conditions = [
                    line
                    for line in rate_lines
                    if not PRICE.fullmatch(line)
                    and not BANK.fullmatch(line)
                    and not re.fullmatch(r"(?:[−-]\d+)?%", line)
                ]
                rates.append(
                    {"text": "\n".join(conditions + [bank[0] + " с Яндекс Пэй"]), "price": bank[0]}
                )
            elif bank:
                unresolved_bank.append({"room": room.splitlines()[0], "prices": bank})
        if rates:
            cards.append({"text": room, "rates": rates})
    # Exclude account balance/profile and reviews from the normal capture. The
    # complete original selection remains in private work evidence only.
    header = next((i for i, line in enumerate(lines) if line == "Куда вы хотите поехать?"), None)
    if header is None:
        header = next((i for i, line in enumerate(lines) if line.startswith("Жильё ")), None)
    if header is None:
        if "Страница не найдена" in " ".join(lines) or "Страница не найдена" in " ".join(
            raw["title"].split()
        ):
            return {
                "provenance": raw.get("provenance", "observed"),
                "platform": "yandex_travel",
                "checked_at": raw["checked_at"],
                "url": raw["url"],
                "title": raw["title"],
                "snapshot": "Страница не найдена",
                "cards": [],
                "capture_method": "safari_selection_text",
                "coverage": "visible",
                "collection_error": "HOTEL_NOT_FOUND",
                "authorization_state": raw.get("authorization_state", "authenticated"),
            }, []
        raise ValueError("Hotel content boundary not observed")
    end = lines.index("Об этом месте") if "Об этом месте" in lines else len(lines)
    snapshot = "\n".join(lines[header:end])
    registry = re.search(r"Объект №[СC]\d{12}", "\n".join(lines))
    if registry:
        snapshot += "\n" + registry.group(0)
    return {
        "provenance": raw.get("provenance", "observed"),
        "platform": "yandex_travel",
        "checked_at": raw["checked_at"],
        "url": raw["url"],
        "title": raw["title"],
        "snapshot": snapshot,
        "cards": cards,
        "capture_method": "safari_selection_text",
        "coverage": "visible",
        "authorization_state": raw.get("authorization_state", "authenticated"),
    }, unresolved_bank
