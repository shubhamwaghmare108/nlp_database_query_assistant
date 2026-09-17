# NLP Database Query Assistant

Ask supported SQL databases questions in plain English and get back the
generated SQL, a results table, an automatic chart, and a
plain-language explanation — no SQL required.

> "Show the top 5 customers by total sales" → generated SQL,
> validated, executed read-only, charted, and explained.

---

## 1. Features

- Natural-language question box → LLM-generated SQL (Google Gemini)
- Dynamic schema discovery — nothing about your tables is hard-coded
- Multi-layer SQL security validator (statement type, keyword deny-list,
  table allow-list, forced `LIMIT`) before anything touches the database
- Read-only execution via a dedicated database user and connection pooling
- Multiple database profiles selectable from the sidebar
- Automatic Plotly chart selection (bar / line / scatter / pie / table),
  with manual override
- Optional AI-generated plain-language explanation of the result
- Bounded LLM self-correction loop (2–3 attempts) when SQL fails
- Query history for the session (question, SQL, status, timing, rows)
- Structured logging (console + rotating file), no secrets ever logged
- Test suite covering the validator, execution layer, generator, and
  the full pipeline — all runnable without a live database or API key

## 2. Architecture

```text
Streamlit UI (app.py)
        ↓
services/query_service.py      (orchestration + correction loop)
        ↓                ↓                    ↓
nlp/sql_generator.py   security/sql_validator.py   database/query_executor.py
        ↓                                             ↓
nlp/llm_client.py (Gemini / pluggable)        database/connection.py (SQLAlchemy)
        ↓
database/schema.py (live schema discovery)
```

Each layer only talks to the layer(s) shown — the UI never imports the
database or LLM modules directly, and SQL is never executed without
first passing through the validator.

## 3. Technology Stack

| Layer          | Technology                     |
|----------------|---------------------------------|
| Frontend       | Streamlit                       |
| Backend        | Python, SQLAlchemy              |
| Database       | MySQL, PostgreSQL, SQLite, SQL Server, Oracle, DuckDB, Snowflake, BigQuery |
| NLP / LLM      | Google Gemini (`google-genai`)  |
| Data           | Pandas                          |
| Visualization  | Plotly                          |
| SQL validation | sqlglot + custom security rules |
| Config         | python-dotenv                   |
| Testing        | pytest                          |

## 4. Project Structure

```text
nlp_database_query_assistant/
├── app.py                     # Streamlit UI only
├── config.py                  # All environment/config in one place
├── database/
│   ├── connection.py          # SQLAlchemy engine + pooling
│   ├── schema.py               # Dynamic schema discovery
│   └── query_executor.py       # Read-only execution
├── nlp/
│   ├── llm_client.py           # Provider-agnostic LLM client (Gemini, OpenRouter-ready)
│   ├── prompt_builder.py       # All prompt templates
│   └── sql_generator.py        # NL → SQL + schema relevance filter
├── security/
│   └── sql_validator.py        # Defense-in-depth SQL validation
├── visualization/
│   └── charts.py                # Chart-type inference + Plotly builders
├── services/
│   └── query_service.py        # Orchestration + correction loop + history types
├── utils/
│   ├── logging_config.py
│   └── helpers.py
├── tests/                      # pytest suite, no external deps required
├── data/
│   └── sample_data.sql          # Sample sales_db schema + data
├── requirements.txt
├── .env.example
├── render.yaml
└── .streamlit/config.toml
```

## 5. Installation

```bash
git clone <your-fork-url>
cd nlp_database_query_assistant
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 6. Database Setup

1. Start a MySQL server you control.
2. Load the sample schema and data:
   ```bash
   mysql -u root -p < data/sample_data.sql
   ```
3. Create a **read-only** application user (never point the app at an
   admin account):
   ```sql
   CREATE USER 'nlp_reader'@'%' IDENTIFIED BY 'strong_password';
   GRANT SELECT ON sales_db.* TO 'nlp_reader'@'%';
   FLUSH PRIVILEGES;
   ```

## 7. Environment Variables

```bash
cp .env.example .env
```

Fill in `DB_HOST`, `DB_USER`, `DB_PASSWORD`, and `GEMINI_API_KEY`
(get a free-tier key at https://aistudio.google.com/apikey). `.env` is
already in `.gitignore` — never commit it.

The base `DB_*` variables create the `Default` profile. To configure
additional databases, list profile names in `DB_PROFILES` and add variables
with the uppercase profile name in the prefix:

```bash
DB_PROFILES=warehouse,analytics

DB_WAREHOUSE_DIALECT=postgresql
DB_WAREHOUSE_HOST=warehouse.example.com
DB_WAREHOUSE_PORT=5432
DB_WAREHOUSE_NAME=sales
DB_WAREHOUSE_USER=readonly
DB_WAREHOUSE_PASSWORD=strong_password

DB_ANALYTICS_DIALECT=duckdb
DB_ANALYTICS_NAME=data/analytics.duckdb
```

Supported dialects are `mysql`, `mariadb`, `postgresql`, `sqlite`, `mssql`,
`oracle`, `duckdb`, `snowflake`, and `bigquery`. Some backends also require
an installed native client or ODBC driver; the Python drivers are listed in
`requirements.txt`.

## 8. Running Locally

```bash
streamlit run app.py
```

Open the URL Streamlit prints (usually `http://localhost:8501`).

## 9. Example Questions

- Show all customers from Mumbai.
- What is the total revenue?
- Show monthly sales for 2025.
- Which product generated the highest revenue?
- Show the top 5 customers by sales.
- What is the average order value?
- Compare sales between cities.

## 10. Security

Every generated query passes through `security/sql_validator.py`
before it can reach the database:

1. Rejects multiple/stacked statements.
2. Deny-lists `INSERT/UPDATE/DELETE/DROP/ALTER/TRUNCATE/CREATE/GRANT/...`
   and dangerous functions, as a keyword-level check independent of the parser.
3. Parses the SQL (via `sqlglot`) and only allows `SELECT` / `WITH ... SELECT`.
4. Rejects any query touching `information_schema`, `mysql`, `performance_schema`,
   `sys`, or tables outside the discovered/allow-listed schema.
5. Auto-injects a `LIMIT` when one is missing from a non-aggregate query.
6. Execution itself uses a **read-only** MySQL user as a final backstop —
   the application never assumes the LLM or the validator alone is sufficient.

The LLM is never trusted to enforce these rules on its own — the prompt's
security rules are a first line of defense, not the only one.

## 11. Testing

```bash
pytest tests/ -v
```

All 27 tests pass without a live database or API key — the database
and LLM layers are faked/mocked so the suite is fast and CI-friendly.

## 12. Deployment

### Streamlit Community Cloud
1. Push this repo to GitHub.
2. On https://share.streamlit.io, create a new app pointing at `app.py`.
3. Under **Secrets**, paste the contents of your `.env` in TOML format:
   ```toml
   DB_HOST = "..."
   DB_USER = "..."
   DB_PASSWORD = "..."
   GEMINI_API_KEY = "..."
   ```

### Render
`render.yaml` is included — connect the repo in the Render dashboard,
Render will detect the blueprint automatically. Fill in the `sync: false`
environment variables in the dashboard (they're secrets, so they aren't
committed).

### AWS / Oracle Cloud (VM)
```bash
sudo apt update && sudo apt install -y python3-venv git
git clone <repo-url> && cd nlp_database_query_assistant
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in values
# open the firewall/security group for the port you choose, then:
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
```
Run it under `systemd`, `tmux`, or `pm2` for persistence in production.

## 13. Future Enhancements

- OpenRouter as a second LLM provider (`nlp/llm_client.py` already has
  a stub `OpenRouterClient`)
- Persistent (database-backed) query history instead of session-only
- Role-based table/column access restrictions per user
- Streamed LLM responses for perceived latency reduction
