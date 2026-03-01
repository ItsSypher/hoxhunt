# Movie Review Summarizer

A Python tool that ingests a list of movie reviews, processes each one through an LLM, and stores the results in a local SQLite database. Supports both **Groq** and **Gemini** as LLM providers, switchable via a single environment variable.

---

## How it works

The script runs in two sequential phases, with SQLite as the single source of truth throughout:

1. **Ingest** — `reviews.json` is parsed and each review is inserted into the database with `status = 'pending'`. Already-present rows are silently skipped (`INSERT OR IGNORE` on a unique constraint), so re-running is always safe.
2. **Process** — All `pending` rows are read from the database and sent to the configured LLM one at a time. Each row is updated in its own committed transaction with the result (`status = 'done'`) or the error message (`status = 'failed'`). A crash mid-run leaves already-processed rows intact; the next run will pick up from where it left off.

The LLM is instructed to return a structured JSON object containing:
- A 1–2 sentence **summary** of the reviewer's opinion
- A **rating** from 1 to 10 — extracted from the review text if an explicit score is given (and extrapolated to the 1–10 scale), otherwise inferred from tone
- A **sentiment** classification: `positive` or `negative`

---

## Database schema

Single table: `reviews`

| Column | Type | Description |
|---|---|---|
| `id` | `INTEGER PK` | Auto-incremented row ID |
| `reviewer` | `TEXT` | Reviewer handle from the source JSON |
| `original_review` | `TEXT` | Raw review text as loaded from JSON |
| `summary` | `TEXT` | 1–2 sentence LLM-generated summary |
| `rating` | `INTEGER` | Rating 1–10 (1 = very negative, 10 = very positive). Extracted from the review text if explicit, otherwise inferred from tone. |
| `sentiment` | `TEXT` | `positive` or `negative` |
| `status` | `TEXT` | `pending` → `done` or `failed` |
| `error_message` | `TEXT` | Error detail on failure; null otherwise |
| `processed_at` | `TEXT` | ISO-8601 UTC timestamp of last processing attempt |

The `(reviewer, original_review)` pair has a `UNIQUE` constraint, preventing double-loading the source JSON.

---

## Setup

### Prerequisites

- Python 3.11+
- An API key for your chosen provider (see [Configure](#configure) below)

### Install

```bash
pip install -r requirements.txt
```

### Configure

```bash
cp .env.example .env
# Edit .env — set LLM_PROVIDER and fill in the matching API key
```

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `groq` | Which provider to use: `groq` or `gemini` |
| `GROQ_API_KEY` | — | Required when `LLM_PROVIDER=groq`. Get one free at https://console.groq.com |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq model name |
| `GEMINI_API_KEY` | — | Required when `LLM_PROVIDER=gemini`. Get one free at https://ai.google.dev/gemini-api/docs/api-key |
| `GEMINI_MODEL` | `gemini-3.0-flash` | Gemini model name |

---

## Run

```bash
python main.py
```

**First run:** all 10 reviews are ingested into the DB (`pending`) and then processed.  
**Subsequent runs:** ingest skips rows already present; processing only runs against any remaining `pending` or previously `failed` rows (after resetting their status — see below).

### Re-running failed reviews

```bash
sqlite3 reviews.db "UPDATE reviews SET status='pending', error_message=NULL WHERE status='failed'"
python main.py
```

---

## Query results

```bash
sqlite3 reviews.db "SELECT reviewer, rating, sentiment, summary FROM reviews"
```

Or inspect the full table:

```bash
sqlite3 reviews.db ".mode column" ".headers on" "SELECT * FROM reviews"
```
