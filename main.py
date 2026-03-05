import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv

load_dotenv()

DB_PATH = Path("reviews.db")
SCHEMA_PATH = Path("schema.sql")
REVIEWS_PATH = Path("reviews.json")
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"


# DB setup

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for safer concurrent access and better crash recovery
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    schema = SCHEMA_PATH.read_text()
    conn.executescript(schema)
    conn.commit()
    print("[db] Schema initialised.")


# Phase 1 — Ingest

def ingest(conn: sqlite3.Connection, path: Path) -> None:
    """Load reviews.json into the DB. Rows already present are silently skipped."""
    reviews = json.loads(path.read_text())

    inserted = 0
    skipped = 0

    with conn:
        for item in reviews:
            reviewer = item["reviewer"].strip()
            original_review = item["review"].strip()

            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO reviews (reviewer, original_review, status)
                VALUES (?, ?, 'pending')
                """,
                (reviewer, original_review),
            )
            if cursor.rowcount == 1:
                inserted += 1
            else:
                skipped += 1

    print(f"[ingest] {inserted} new rows inserted, {skipped} already present — skipped.")


# Phase 2 — LLM processing

SYSTEM_PROMPT = """\
You are a movie review analyst. Given a movie review, you must return a JSON object
with exactly these three keys:

  "summary"   – A 1-2 sentence summary of the reviewer's opinion (string).
  "rating"    – An integer from 1 to 10 reflecting how positively the reviewer
                feels about the film (1 = very negative, 10 = very positive). 
                The reviewer might also give an explicit rating in the text 
                (e.g. "I give this movie 4/5 stars"), extrapolate your rating out of 10 if that happens but if not,
                infer it from the overall tone and content of the review. 
  "sentiment" – Either the string "positive" or "negative".

Return only the JSON object. No markdown, no explanation, no extra keys.
"""


def build_messages(review_text: str) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": review_text},
    ]


def validate_response(data: dict) -> None:
    """Raise ValueError if the parsed JSON doesn't match the expected schema."""
    if not isinstance(data.get("summary"), str) or not data["summary"].strip():
        raise ValueError(f"Invalid or missing 'summary': {data.get('summary')!r}")

    rating = data.get("rating")
    if not isinstance(rating, int) or rating not in range(1, 11):
        raise ValueError(f"Invalid 'rating' (must be int 1-10): {rating!r}")

    sentiment = data.get("sentiment")
    if sentiment not in ("positive", "negative"):
        raise ValueError(f"Invalid 'sentiment' (must be 'positive' or 'negative'): {sentiment!r}")


def call_groq(client, model: str, review_text: str) -> dict:
    response = client.chat.completions.create(
        model=model,
        messages=build_messages(review_text),
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    raw = response.choices[0].message.content
    data = json.loads(raw)
    validate_response(data)
    return data


def normalize_gemini_model_name(model_name: str) -> str:
    model_name = model_name.strip()
    if model_name.startswith("models/"):
        return model_name.removeprefix("models/")
    return model_name


def is_gemini_model_not_found_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "404" in message or "not found" in message or "not supported" in message


def call_gemini(client, model_name: str, review_text: str) -> dict:
    response = client.models.generate_content(
        model=model_name,
        contents=review_text,
        config={
            "system_instruction": SYSTEM_PROMPT,
            "response_mime_type": "application/json",
            "temperature": 0.2,
        },
    )
    raw = (getattr(response, "text", "") or "").strip()
    if not raw:
        raise ValueError("Gemini returned an empty response.")
    data = json.loads(raw)
    validate_response(data)
    return data


# Phase 2 — Process pending rows


def process(conn: sqlite3.Connection, call_fn: Callable[[str], dict]) -> None:
    pending = conn.execute(
        "SELECT id, reviewer, original_review FROM reviews WHERE status = 'pending'"
    ).fetchall()

    if not pending:
        print("[process] No pending reviews found.")
        return

    print(f"[process] Processing {len(pending)} pending review(s)...")

    done = 0
    failed = 0

    for row in pending:
        review_id = row["id"]
        reviewer = row["reviewer"]
        print(f"  → [{review_id}] {reviewer} ...", end=" ", flush=True)

        try:
            result = call_fn(row["original_review"])
            conn.execute(
                """
                UPDATE reviews
                SET summary      = ?,
                    rating       = ?,
                    sentiment    = ?,
                    status       = 'done',
                    error_message = NULL,
                    processed_at = ?
                WHERE id = ?
                """,
                (
                    result["summary"],
                    result["rating"],
                    result["sentiment"],
                    datetime.now(timezone.utc).isoformat(),
                    review_id,
                ),
            )
            conn.commit()
            print(f"done (rating={result['rating']}, sentiment={result['sentiment']})")
            done += 1

        except Exception as exc:  # noqa: BLE001
            conn.execute(
                """
                UPDATE reviews
                SET status        = 'failed',
                    error_message = ?,
                    processed_at  = ?
                WHERE id = ?
                """,
                (str(exc), datetime.now(timezone.utc).isoformat(), review_id),
            )
            conn.commit()
            print(f"FAILED — {exc}")
            failed += 1

    print(f"\n[process] Finished: {done} done, {failed} failed.")


# Entry point


def main() -> None:
    provider = os.environ.get("LLM_PROVIDER", "groq").lower()

    if provider == "groq":
        from groq import Groq

        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GROQ_API_KEY is not set. Copy .env.example to .env and add your key."
            )
        model_name = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
        client = Groq(api_key=api_key)
        call_fn: Callable[[str], dict] = lambda text: call_groq(client, model_name, text)
        print(f"[llm] Provider: Groq | Model: {model_name}")

    elif provider == "gemini":
        from google import genai

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GEMINI_API_KEY is not set. Copy .env.example to .env and add your key."
            )
        requested_model = os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
        model_name = normalize_gemini_model_name(requested_model) or DEFAULT_GEMINI_MODEL
        client = genai.Client(api_key=api_key)

        def gemini_call(text: str) -> dict:
            nonlocal model_name
            try:
                return call_gemini(client, model_name, text)
            except Exception as exc:  # noqa: BLE001
                if (
                    model_name != DEFAULT_GEMINI_MODEL
                    and is_gemini_model_not_found_error(exc)
                ):
                    model_name = DEFAULT_GEMINI_MODEL
                    print(f"[llm] Gemini default fallback: {model_name}")
                    return call_gemini(client, model_name, text)
                raise

        call_fn = gemini_call
        print(f"[llm] Provider: Gemini | Model: {model_name}")

    else:
        raise EnvironmentError(
            f"Unknown LLM_PROVIDER: {provider!r}. Must be 'groq' or 'gemini'."
        )

    conn = get_connection()
    try:
        init_db(conn)
        ingest(conn, REVIEWS_PATH)
        process(conn, call_fn)
    finally:
        conn.close()

    print("\nDone. Query results with:")
    print("  sqlite3 reviews.db \"SELECT reviewer, rating, sentiment, summary FROM reviews\"")


if __name__ == "__main__":
    main()
