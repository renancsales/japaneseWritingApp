"""Grammar catalogue and the deterministic 'grammar point of the day' selection."""
import json
import random
from datetime import date
from functools import lru_cache
from pathlib import Path

from . import db

DATA_DIR = Path(__file__).parent / "data"
# Proof of concept: only N3 ships. Add "N4": "n4_grammar.json" etc. to extend.
LEVEL_FILES = {"N3": "n3_grammar.json"}
SUPPORTED_LEVELS = list(LEVEL_FILES)


@lru_cache
def load_level(level: str) -> list[dict]:
    if level not in LEVEL_FILES:
        raise KeyError(level)
    return json.loads((DATA_DIR / LEVEL_FILES[level]).read_text(encoding="utf-8"))


def get_point(grammar_id: str) -> dict | None:
    for level in LEVEL_FILES:
        for point in load_level(level):
            if point["id"] == grammar_id:
                return {**point, "level": level}
    return None


def point_for_day(level: str, day: date | None = None) -> dict:
    """Return the grammar point for `day`, picking (and persisting) one if needed.

    Picks favour points that haven't been used yet, so the whole level is cycled
    through before anything repeats.
    """
    day_s = (day or date.today()).isoformat()
    points = load_level(level)
    with db.connect() as conn:
        row = conn.execute(
            "SELECT grammar_id FROM daily_grammar WHERE day = ? AND level = ?",
            (day_s, level),
        ).fetchone()
        if row and (p := get_point(row["grammar_id"])):
            return p

        used = {
            r["grammar_id"]
            for r in conn.execute("SELECT grammar_id FROM daily_grammar WHERE level = ?", (level,))
        }
        unused = [p for p in points if p["id"] not in used]
        pool = unused or points
        choice = random.Random(f"{level}-{day_s}").choice(pool)
        conn.execute(
            "INSERT OR REPLACE INTO daily_grammar (day, level, grammar_id) VALUES (?, ?, ?)",
            (day_s, level, choice["id"]),
        )
    return {**choice, "level": level}


def reroll(level: str, day: date | None = None) -> dict:
    """Swap today's point for a different one (user asked for another)."""
    day_s = (day or date.today()).isoformat()
    current = point_for_day(level, day)
    others = [p for p in load_level(level) if p["id"] != current["id"]]
    choice = random.choice(others)
    with db.connect() as conn:
        conn.execute(
            "UPDATE daily_grammar SET grammar_id = ? WHERE day = ? AND level = ?",
            (choice["id"], day_s, level),
        )
    return {**choice, "level": level}
