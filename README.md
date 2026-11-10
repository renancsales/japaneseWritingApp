# japaneseWritingApp — 日記 Grammar Journal

A daily Japanese writing practice app. Each day it picks a JLPT grammar point, explains it, and asks
you to write a short journal entry using it. Claude checks your entry for grammar errors, and every word
you use is saved to a flashcard deck with spaced repetition.

**Proof of concept: JLPT N3 only** (36 hand-written grammar points).

## Features

- **Grammar of the day:** a stable pick for each day. It cycles through every N3 point before repeating, and **↻ Another** swaps today's pick.
  Each point shows its meaning, formation, explanation, examples and a writing prompt.
- **Grammar checking:** returns a corrected version (minimal fixes), a natural native-style version, a list of
  errors with explanations, and feedback on whether the target grammar point was used correctly.
- **Word suggestions:** describe what you want to say (English or Japanese) and get words with reading,
  nuance notes and example sentences. **＋ insert** puts the word into your entry.
- **Vocabulary capture:** every content word in your entries is stored in dictionary form with its reading, meaning
  and the sentence you used it in. Particles and auxiliaries are skipped.
- **Flashcards:** SM-2 spaced repetition with Again / Hard / Good / Easy. Keyboard: Space flips the card, 1–4 grades it.
- **History:** past entries with their feedback.

## Run

Requires [uv](https://docs.astral.sh/uv/), Python 3.10+ and an Anthropic API key.

```powershell
uv sync
$env:ANTHROPIC_API_KEY = "sk-ant-..."
uv run uvicorn app.main:app --reload
```

Then open http://127.0.0.1:8000.

Data is stored in `data/app.db` (SQLite). You can override the location with `JWA_DB_PATH`.

## Tests

```powershell
uv run pytest -q
```

The tests mock the Claude calls, so they don't need an API key.

## Layout

```
src/app/
  main.py        FastAPI routes (today, entries, suggest, words, flashcards)
  llm.py         Claude calls with JSON-schema structured outputs
  grammar.py     grammar catalogue + daily selection
  srs.py         SM-2 scheduling
  db.py          SQLite schema
  data/n3_grammar.json
  static/        single-page frontend (vanilla JS)
tests/
```

## Notes

- Model: `claude-opus-5-5` (override with `JWA_MODEL`). Grammar checks run at `medium` effort and suggestions at `low`.
  Server-side refusal fallback (`fallbacks: "default"`) is enabled.
- To add a level, drop `n4_grammar.json` (same shape) into `src/app/data/` and register it in
  `LEVEL_FILES` in `grammar.py`. The level dropdown already lists N5–N1, and the levels that aren't available yet are greyed out.
