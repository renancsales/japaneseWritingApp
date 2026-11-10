"""Claude-powered grammar checking and word suggestions (structured JSON outputs)."""
import json
import os

import anthropic

MODEL = os.environ.get("JWA_MODEL", "claude-opus-5-5")
FALLBACK_BETA = "server-side-fallback-2026-07-01"

_client: anthropic.Anthropic | None = None


class LLMError(RuntimeError):
    """User-presentable failure from the language model layer."""


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {
        "type": "object",
        "properties": props,
        "required": required or list(props),
        "additionalProperties": False,
    }


_S = {"type": "string"}
_EXAMPLE = _obj({"japanese": _S, "reading": _S, "english": _S})

CHECK_SCHEMA = _obj({
    "is_correct": {"type": "boolean"},
    "corrected_text": _S,
    "natural_version": _S,
    "overall_feedback": _S,
    "grammar_point_used": {"type": "boolean"},
    "grammar_point_feedback": _S,
    "errors": {"type": "array", "items": _obj({
        "original": _S, "correction": _S, "explanation": _S,
    })},
    "words": {"type": "array", "items": _obj({
        "word": _S, "reading": _S, "meaning": _S, "part_of_speech": _S, "example": _S,
    })},
})

SUGGEST_SCHEMA = _obj({
    "suggestions": {"type": "array", "items": _obj({
        "word": _S, "reading": _S, "meaning": _S, "part_of_speech": _S,
        "usage_note": _S,
        "examples": {"type": "array", "items": _EXAMPLE},
    })},
})

CHECK_SYSTEM = """You are a patient, precise Japanese teacher reviewing a learner's short daily journal entry.
The learner is studying for JLPT {level} and was asked to use a specific grammar point.

Review the entry and return:
- is_correct: true only if there are no grammatical errors (stylistic suggestions don't count).
- corrected_text: the learner's text with only the errors fixed, keeping their wording and meaning as much as possible. Identical to the input if nothing is wrong.
- natural_version: how a native speaker would naturally write the same thing, still around {level} level.
- errors: one item per mistake (particles, conjugation, word choice, kanji, register mixing, etc.). `original` and `correction` are the short spans involved; `explanation` is in English and says why.
- grammar_point_used / grammar_point_feedback: whether the target grammar point appears and is used correctly; give concrete English feedback on its usage (or how they could have used it).
- overall_feedback: 1-3 encouraging, specific sentences in English.
- words: every distinct content word in the learner's entry (nouns, verbs, adjectives, adverbs, set expressions; skip particles, copulas and auxiliaries). Use the dictionary form for `word` (the corrected word if they misused one), hiragana `reading`, short English `meaning`, `part_of_speech`, and `example`: the sentence from the corrected text in which the word appears.

Keep explanations short and appropriate for an intermediate learner. Never invent errors."""

SUGGEST_SYSTEM = """You help a JLPT {level} learner find Japanese words while writing a journal entry.
Given what they want to express (in English, Japanese, or a mix), suggest 3-6 useful words or set expressions, most appropriate first.
For each: dictionary-form `word`, hiragana `reading`, short English `meaning`, `part_of_speech`, a brief `usage_note` (nuance, register, common collocations or confusions), and 2 short natural `examples` at about {level} level with hiragana reading and English translation.
When it fits naturally, make one example use the grammar point the learner is practising."""


def _call(system: str, user: str, schema: dict, effort: str) -> dict:
    try:
        response = client().beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            betas=[FALLBACK_BETA],
            fallbacks="default",
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        )
    except anthropic.AuthenticationError as e:
        raise LLMError("Claude API authentication failed - check ANTHROPIC_API_KEY.") from e
    except TypeError as e:
        if "authentication" not in str(e):
            raise
        raise LLMError("No Claude API credentials found - set ANTHROPIC_API_KEY and restart the server.") from e
    except anthropic.RateLimitError as e:
        raise LLMError("Rate limited by the Claude API - try again in a moment.") from e
    except anthropic.APIStatusError as e:
        raise LLMError(f"Claude API error ({e.status_code}): {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise LLMError("Could not reach the Claude API - check your connection.") from e

    if response.stop_reason == "refusal":
        raise LLMError("The model declined to process this text.")
    if response.stop_reason == "max_tokens":
        raise LLMError("The response was cut off - try a shorter entry.")
    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        raise LLMError("The model returned no answer.")
    return json.loads(text)


def check_entry(text: str, grammar_point: dict, level: str) -> dict:
    user = (
        f"Target grammar point: {grammar_point['pattern']} — {grammar_point['meaning']}\n"
        f"Formation: {grammar_point['formation']}\n\n"
        f"Learner's entry:\n<entry>\n{text}\n</entry>"
    )
    return _call(CHECK_SYSTEM.format(level=level), user, CHECK_SCHEMA, effort="medium")


def suggest_words(query: str, grammar_point: dict | None, level: str) -> dict:
    user = f"What I want to say: {query}"
    if grammar_point:
        user += f"\nGrammar point I'm practising: {grammar_point['pattern']} ({grammar_point['meaning']})"
    return _call(SUGGEST_SYSTEM.format(level=level), user, SUGGEST_SCHEMA, effort="low")
