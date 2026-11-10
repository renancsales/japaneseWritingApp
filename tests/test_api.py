import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app import grammar, llm, srs  # noqa: E402

FAKE_CHECK = {
    "is_correct": False,
    "corrected_text": "毎日野菜を食べるようにしています。",
    "natural_version": "毎日、野菜を食べるようにしています。",
    "overall_feedback": "Good use of the grammar point!",
    "grammar_point_used": True,
    "grammar_point_feedback": "Correct usage.",
    "errors": [{"original": "野菜が", "correction": "野菜を", "explanation": "食べる takes を."}],
    "words": [
        {"word": "毎日", "reading": "まいにち", "meaning": "every day", "part_of_speech": "noun", "example": "毎日野菜を食べるようにしています。"},
        {"word": "野菜", "reading": "やさい", "meaning": "vegetable", "part_of_speech": "noun", "example": "毎日野菜を食べるようにしています。"},
        {"word": "食べる", "reading": "たべる", "meaning": "to eat", "part_of_speech": "verb", "example": "毎日野菜を食べるようにしています。"},
    ],
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("JWA_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(llm, "check_entry", lambda text, point, level: dict(FAKE_CHECK, words=list(FAKE_CHECK["words"])))
    monkeypatch.setattr(llm, "suggest_words", lambda q, p, level: {"suggestions": [{"word": "通勤", "reading": "つうきん", "meaning": "commute", "part_of_speech": "noun", "usage_note": "", "examples": []}]})
    from app.main import app
    with TestClient(app) as c:
        yield c


def test_grammar_catalogue_is_valid():
    points = grammar.load_level("N3")
    assert len(points) >= 30
    ids = [p["id"] for p in points]
    assert len(ids) == len(set(ids))
    for p in points:
        assert p["pattern"] and p["meaning"] and p["explanation"] and p["prompt"]
        assert len(p["examples"]) >= 2


def test_today_is_stable_and_only_n3(client):
    a = client.get("/api/today").json()
    b = client.get("/api/today?level=n3").json()
    assert a["id"] == b["id"] and a["level"] == "N3"
    assert client.get("/api/today?level=N2").status_code == 400


def test_daily_pick_avoids_repeats(client):
    seen = {grammar.point_for_day("N3", date(2026, 1, 1) + timedelta(days=i))["id"] for i in range(len(grammar.load_level("N3")))}
    assert len(seen) == len(grammar.load_level("N3"))


def test_entry_stores_words_and_flashcards(client):
    gid = client.get("/api/today").json()["id"]
    r = client.post("/api/entries", json={"text": "毎日野菜が食べるようにしています。", "grammar_id": gid}).json()
    assert [w["new"] for w in r["words"]] == [True, True, True]
    r2 = client.post("/api/entries", json={"text": "野菜を食べた。", "grammar_id": gid}).json()
    assert all(not w["new"] for w in r2["words"])

    words = client.get("/api/words").json()
    assert {w["word"] for w in words} == {"毎日", "野菜", "食べる"}
    assert all(w["seen_count"] == 2 for w in words)
    assert len(client.get("/api/entries").json()) == 2

    due = client.get("/api/flashcards/due").json()["cards"]
    assert len(due) == 3
    rv = client.post(f"/api/flashcards/{due[0]['id']}/review", json={"grade": "good"}).json()
    assert rv["interval"] == 1
    assert len(client.get("/api/flashcards/due").json()["cards"]) == 2


def test_llm_error_maps_to_502(client, monkeypatch):
    def boom(*a):
        raise llm.LLMError("Claude API authentication failed - set ANTHROPIC_API_KEY.")
    monkeypatch.setattr(llm, "check_entry", boom)
    gid = client.get("/api/today").json()["id"]
    r = client.post("/api/entries", json={"text": "テスト", "grammar_id": gid})
    assert r.status_code == 502 and "ANTHROPIC_API_KEY" in r.json()["detail"]


def test_suggest(client):
    r = client.post("/api/suggest", json={"query": "commute"}).json()
    assert r["suggestions"][0]["word"] == "通勤"


def test_srs_progression():
    e, i, n, _ = srs.schedule(2.5, 0, 0, "good")
    assert (i, n) == (1, 1)
    e, i, n, _ = srs.schedule(e, i, n, "good")
    assert i == 3
    e, i, n, _ = srs.schedule(e, i, n, "good")
    assert i > 3
    _, i, n, due = srs.schedule(e, i, n, "again")
    assert (i, n) == (0, 0) and due == date.today().isoformat()
