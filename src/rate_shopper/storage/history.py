import json
import sqlite3
from pathlib import Path
from typing import Any


def save_run(path: Path, run_id: str, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        db.execute(
            "INSERT OR IGNORE INTO runs VALUES (?, ?)",
            (run_id, json.dumps(payload, ensure_ascii=False, sort_keys=True)),
        )
