# Movie Review Summarizer

A Python tool that ingests a list of movie reviews, processes each one through a Groq-hosted LLM, and stores the results in a local SQLite database.

---

## How it works

The script runs in two sequential phases, with SQLite as the single source of truth throughout:

1. **Ingest** — `reviews.json` is loaded and each review is inserted into the database with `status = 'pending'`. Re-running is safe: rows already present are silently skipped (`INSERT OR IGNORE`).
2. **Process** — All `pending` rows are read from the database, sent to Groq one at a time, and the same row is updated with the result (`status = 'done'`) or the error (`status = 'failed'`). Each update is committed immediately, so a crash mid-run leaves already-processed rows intact.

---

## Database schema

Single table: `reviews`

| Column | Type | Description |
|---|---|---|
| `id` | `INTEGER PK` | Auto-incremented row ID |
| `reviewer` | `TEXT` | Reviewer handle from the source JSON |
| `original_review` | `TEXT` | Raw review text as loaded from JSON |
| `summary` | `TEXT` | 1-2 sentence LLM-generated summary |
| `rating` | `INTEGER` | Estimated rating 1–10 (1 = very negative, 10 = very positive). Extrapolated from any explicit score in the review text, or inferred from overall tone. |
| `sentiment` | `TEXT` | `positive` or `negative` |
| `status` | `TEXT` | `pending` → `done` or `failed` |
| `error_message` | `TEXT` | Populated on failure; null otherwise |
| `processed_at` | `TEXT` | ISO-8601 UTC timestamp of last processing attempt |

The `(reviewer, original_review)` pair has a `UNIQUE` constraint so the source JSON can never be double-loaded.

---

## Setup

### Prerequisites

- Python 3.11+
- A Groq API key — get one free at https://console.groq.com

### Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configure

```bash
cp .env.example .env
# Edit .env — set LLM_PROVIDER to 'groq' or 'gemini' and fill in the matching API key
```

**Groq** (default) — get a free key at https://console.groq.com  
Default model: `llama-3.3-70b-versatile`. Override with `GROQ_MODEL`.

**Gemini** — get a free key at https://ai.google.dev/gemini-api/docs/api-key  
Default model: `gemini-2.0-flash`. Override with `GEMINI_MODEL`.

---

## Run

```bash
python main.py
```

On the first run, all 10 reviews will be ingested and processed. Subsequent runs will skip already-loaded reviews and only process any that are still `pending` or were not yet inserted.

---

## Query results

```bash
sqlite3 reviews.db "SELECT reviewer, rating, sentiment, summary FROM reviews"
```

Or inspect the full table:

```bash
sqlite3 reviews.db ".mode column" ".headers on" "SELECT * FROM reviews"
```
