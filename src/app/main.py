"""FastAPI app: daily grammar journaling with AI correction and vocabulary flashcards."""
import json
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db, grammar, llm, srs

STATIC = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_app):
    db.init_db()
    yield


app = FastAPI(title="Japanese Writing App", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


def _level(level: str) -> str:
    level = level.upper()
    if level not in grammar.SUPPORTED_LEVELS:
        raise HTTPException(400, f"Only {', '.join(grammar.SUPPORTED_LEVELS)} is available in this version.")
    return level


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/levels")
def levels():
    return {"levels": grammar.SUPPORTED_LEVELS, "all": ["N5", "N4", "N3", "N2", "N1"]}


@app.get("/api/today")
def today(level: str = "N3"):
    return grammar.point_for_day(_level(level))


@app.post("/api/today/reroll")
def reroll(level: str = "N3"):
    return grammar.reroll(_level(level))


@app.get("/api/grammar")
def grammar_list(level: str = "N3"):
    return grammar.load_level(_level(level))


# ---------- journal entries ----------

class EntryIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    grammar_id: str
    level: str = "N3"


def _store_words(conn, entry_id: int, words: list[dict]) -> list[dict]:
    stored = []
    for w in words:
        word = w["word"].strip()
        if not word:
            continue
        row = conn.execute("SELECT id FROM words WHERE word = ?", (word,)).fetchone()
        if row:
            word_id = row["id"]
            conn.execute("UPDATE words SET seen_count = seen_count + 1 WHERE id = ?", (word_id,))
            is_new = False
        else:
            word_id = conn.execute(
                "INSERT INTO words (word, reading, meaning, pos, example, due) VALUES (?, ?, ?, ?, ?, ?)",
                (word, w["reading"], w["meaning"], w["part_of_speech"], w["example"],
                 date.today().isoformat()),  # local date; SQLite's date('now') is UTC
            ).lastrowid
            is_new = True
        conn.execute("INSERT OR IGNORE INTO entry_words VALUES (?, ?)", (entry_id, word_id))
        stored.append({**w, "id": word_id, "new": is_new})
    return stored


@app.post("/api/entries")
def create_entry(body: EntryIn):
    level = _level(body.level)
    point = grammar.get_point(body.grammar_id)
    if not point:
        raise HTTPException(404, "Unknown grammar point")
    try:
        result = llm.check_entry(body.text, point, level)
    except llm.LLMError as e:
        raise HTTPException(502, str(e)) from e

    with db.connect() as conn:
        entry_id = conn.execute(
            "INSERT INTO entries (day, grammar_id, text, corrected, feedback_json) VALUES (?, ?, ?, ?, ?)",
            (date.today().isoformat(), point["id"], body.text, result["corrected_text"],
             json.dumps(result, ensure_ascii=False)),
        ).lastrowid
        result["words"] = _store_words(conn, entry_id, result["words"])
    return {"id": entry_id, "text": body.text, "grammar": point, **result}


@app.get("/api/entries")
def list_entries(limit: int = 50):
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM entries ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    out = []
    for r in rows:
        point = grammar.get_point(r["grammar_id"]) or {}
        out.append({
            "id": r["id"], "day": r["day"], "text": r["text"], "created_at": r["created_at"],
            "grammar": {"id": r["grammar_id"], "pattern": point.get("pattern")},
            "feedback": json.loads(r["feedback_json"]) if r["feedback_json"] else None,
        })
    return out


@app.delete("/api/entries/{entry_id}")
def delete_entry(entry_id: int):
    with db.connect() as conn:
        conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
    return {"ok": True}


# ---------- word suggestions ----------

class SuggestIn(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    grammar_id: str | None = None
    level: str = "N3"


@app.post("/api/suggest")
def suggest(body: SuggestIn):
    level = _level(body.level)
    point = grammar.get_point(body.grammar_id) if body.grammar_id else None
    try:
        return llm.suggest_words(body.query, point, level)
    except llm.LLMError as e:
        raise HTTPException(502, str(e)) from e


# ---------- vocabulary & flashcards ----------

def _word(r) -> dict:
    return {k: r[k] for k in r.keys()}


@app.get("/api/words")
def list_words():
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM words ORDER BY created_at DESC, id DESC").fetchall()
    return [_word(r) for r in rows]


@app.delete("/api/words/{word_id}")
def delete_word(word_id: int):
    with db.connect() as conn:
        conn.execute("DELETE FROM words WHERE id = ?", (word_id,))
    return {"ok": True}


@app.get("/api/flashcards/due")
def due_cards(limit: int = 30):
    today_s = date.today().isoformat()
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM words WHERE due <= ? ORDER BY due, id LIMIT ?", (today_s, limit)
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM words").fetchone()[0]
    return {"cards": [_word(r) for r in rows], "total_words": total}


class ReviewIn(BaseModel):
    grade: str


@app.post("/api/flashcards/{word_id}/review")
def review(word_id: int, body: ReviewIn):
    if body.grade not in srs.GRADES:
        raise HTTPException(400, f"grade must be one of {list(srs.GRADES)}")
    with db.connect() as conn:
        r = conn.execute("SELECT * FROM words WHERE id = ?", (word_id,)).fetchone()
        if not r:
            raise HTTPException(404, "Unknown word")
        ease, interval, reps, due = srs.schedule(r["ease"], r["interval"], r["reps"], body.grade)
        conn.execute(
            "UPDATE words SET ease = ?, interval = ?, reps = ?, due = ? WHERE id = ?",
            (ease, interval, reps, due, word_id),
        )
    return {"id": word_id, "ease": ease, "interval": interval, "reps": reps, "due": due}
