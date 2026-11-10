"""Minimal SM-2 spaced repetition scheduling."""
from datetime import date, timedelta

# Grades shown as buttons in the flashcard UI.
GRADES = {"again": 0, "hard": 3, "good": 4, "easy": 5}


def schedule(ease: float, interval: int, reps: int, grade: str, today: date | None = None):
    """Return (ease, interval_days, reps, due_iso) after reviewing a card."""
    q = GRADES[grade]
    today = today or date.today()
    if q < 3:
        reps, interval = 0, 0  # see it again today
    else:
        reps += 1
        if reps == 1:
            interval = 1
        elif reps == 2:
            interval = 3
        else:
            interval = max(1, round(interval * ease))
        if grade == "easy":
            interval = max(interval + 1, round(interval * 1.3))
    ease = max(1.3, ease + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02)))
    return round(ease, 3), interval, reps, (today + timedelta(days=interval)).isoformat()
