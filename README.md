# NLP Database Query Assistant

Ask supported SQL databases questions in plain English and get back generated SQL, a results table, an automatic chart, and a plain-language explanation — no SQL required.

> "Show the top 5 customers by total sales" → generated SQL, validated, executed read-only, charted, and explained.

---

## 1. Features

- Natural-language question box → LLM-generated SQL with Google Gemini
- Dynamic schema discovery — table metadata is read from the selected database
- Multiple database profiles selectable from the sidebar
- Provider-aware connection settings for SQL/warehouse databases
- Multi-layer SQL security validation before execution
- Read-only database execution with provider-specific query timeouts
- Automatic Plotly chart selection (bar / line / scatter / pie / table), with manual override
- Optional AI-generated plain-language explanation of results
- Bounded LLM self-correction loop for **execution failures** only
- Session query history with question, SQL, status, timing, and row count
- Structured logging with secrets excluded from application logs
- Test suite covering configuration, schema discovery, SQL validation, execution, LLM generation, sessions, and the query pipeline
- CI on GitHub Actions using Python 3.11

## 2. Architecture

```text
User Question
     ↓
Streamlit UI (app.py)
     ↓
services/query_service.py
     ↓
Schema Discovery ──→ LLM SQL Generation
     ↓                     ↓
     └────────────→ SQL Security Validation
                           ↓
                    ┌──────┴──────┐
                    │             │
                  PASS          REJECT
                    ↓             ↓
              Query Execution   Return security error
                    ↓
              Result + Chart
                    ↓
              Explanation

Execution failure
     ↓
Bounded correction attempt
     ↓
Validation → Execution
```

Security-validation failures are returned directly to the user; they are **not** sent back to the LLM for correction.

Main modules:

- `app.py` — Streamlit presentation layer
- `services/query_service.py` — pipeline orchestration, correction loop, history
- `nlp/sql_generator.py` — natural language → SQL generation
- `nlp/llm_client.py` — LLM provider abstraction
- `security/sql_validator.py` — SQL security and safety validation
- `database/schema.py` — dynamic schema discovery
- `database/query_executor.py` — validated SQL execution and timeout handling
- `database/connection.py` — SQLAlchemy connections and pooling

## 3. Technology Stack

| Layer | Technology |
|---|---|
| Frontend | Streamlit |
| Backend | Python, SQLAlchemy |
| Databases | MySQL, MariaDB, PostgreSQL, SQLite, SQL Server, Oracle, DuckDB, Snowflake, BigQuery |
| NLP / LLM | Google Gemini via `google-genai` |
| Data | Pandas |
| Visualization | Plotly |
| SQL parsing / validation | sqlglot + custom security rules |
| Configuration | python-dotenv |
| Testing | pytest |
| CI | GitHub Actions |

Provider aliases supported by configuration include `postgres`/`postgresql`, `mssql`/`sqlserver`, and `bigquery`/`googlebigquery`.

## 4. Project Structure

```text
nlp_database_query_assistant/
├── app.py
├── config.py
├── database/
│   ├── connection.py
│   ├── connection_options.py
│   ├── schema.py
│   └── query_executor.py
├── nlp/
│   ├── llm_client.py
│   ├── prompt_builder.py
│   └── sql_generator.py
├── security/
│   └── sql_validator.py
├── visualization/
│   └── charts.py
├── services/
│   └── query_service.py
├── auth/
│   └── session.py
├── utils/
│   ├── logging_config.py
│   └── helpers.py
├── tests/
├── data/
│   └── sample_data.sql
├── requirements.txt
├── .env.example
├── render.yaml
└── .streamlit/
    └── config.toml
```

## 5. Installation

```bash
git clone https://github.com/shubhamwaghmare108/nlp_database_query_assistant.git
cd nlp_database_query_assistant

python -m venv venv

# Windows
venv\Scripts\activate

# Linux / macOS
source venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 6. Database Configuration

The application is designed around a read-only database connection. For the sample setup, start a MySQL server and load:

```bash
mysql -u root -p < data/sample_data.sql
```

Create a dedicated read-only user instead of using an administrator account:

```sql
CREATE USER 'nlp_reader'@'%' IDENTIFIED BY 'strong_password';
GRANT SELECT ON retail_demo.* TO 'nlp_reader'@'%';
FLUSH PRIVILEGES;
```

The application also supports provider-specific configuration such as:

- PostgreSQL schemas
- Snowflake database/schema, warehouse, and role
- BigQuery project and dataset
- SQL Server ODBC driver, encryption, and authentication options
- Oracle service name or SID
- SQLite and DuckDB file paths
- SSL options where supported

### Schema and dataset handling

If a database profile specifies a schema, the schema discovery layer uses that configured schema rather than exposing system schemas.

For BigQuery, the configured dataset is used for schema discovery when supplied. The project ID is required for BigQuery connections.

## 7. Environment Variables

Copy the example configuration:

```bash
cp .env.example .env
```

On Windows, copy the file using Explorer or:

```powershell
Copy-Item .env.example .env
```

### Default database

```env
DB_DIALECT=mysql
DB_DRIVER=pymysql
DB_HOST=localhost
DB_PORT=3306
DB_NAME=retail_demo
DB_USER=nlp_reader
DB_PASSWORD=your_database_password
```

### LLM

```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-3.5-flash-lite
```

OpenRouter settings are also recognized by configuration, although Gemini is the currently documented provider:

```env
OPENROUTER_API_KEY=
OPENROUTER_MODEL=
```

### Application controls

```env
APP_ENV=development
LOG_LEVEL=INFO
MAX_RESULT_ROWS=1000
QUERY_TIMEOUT_SECONDS=15
MAX_SQL_CORRECTION_ATTEMPTS=2
```

### Multiple database profiles

The default connection is exposed as the **Default** profile. Additional profiles can be declared with `DB_PROFILES`:

```env
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

Profile variables follow the pattern `DB_<PROFILE>_<SETTING>`.

Never commit `.env` or real credentials.

## 8. Running Locally

```bash
streamlit run app.py
```

Open the URL printed by Streamlit, normally:

```text
http://localhost:8501
```

## 9. Query Examples

Try questions such as:

- Show all customers from Mumbai.
- What is the total revenue?
- Show monthly sales for 2025.
- Which product generated the highest revenue?
- Show the top 5 customers by sales.
- What is the average order value?
- Compare sales between cities.

The generated SQL is shown to the user before/with execution results so the query can be inspected.

## 10. SQL Security

Every generated query passes through `security/sql_validator.py` before execution.

The validator uses multiple layers:

1. **Statement protection** — stacked/multiple statements are rejected.
2. **Dangerous-operation checks** — write and administrative operations such as `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`, `CREATE`, `GRANT`, `REVOKE`, `EXEC`, `CALL`, and related dangerous operations are blocked.
3. **Parser validation** — SQL is parsed with sqlglot and only supported read-query roots are accepted, including `SELECT`, `WITH`, and `UNION`.
4. **Table/schema controls** — referenced tables are checked against discovered or explicitly configured allowed tables.
5. **System metadata protection** — system schemas/tables are restricted, while approved metadata queries such as `information_schema.tables` and `information_schema.columns` are supported for schema discovery.
6. **Qualified-name handling** — catalog/database/schema/table forms are validated where the selected provider supports them.
7. **BigQuery metadata handling** — qualified `INFORMATION_SCHEMA` forms such as `project.region-us.INFORMATION_SCHEMA.TABLES` and `project.dataset.INFORMATION_SCHEMA.COLUMNS` are recognized.
8. **PostgreSQL system-schema protection** — PostgreSQL `pg_*` system schemas are blocked, including qualified forms.
9. **Result-size protection** — a default `LIMIT` is added to applicable non-aggregate queries when one is missing.
10. **Execution backstop** — database connections should use least-privilege/read-only credentials, and query execution applies the configured timeout.

The LLM prompt is not treated as a security boundary. Validation happens independently after SQL generation.

### Important correction behavior

If SQL is rejected by the **security validator**, the request stops and the security error is returned. The application does not ask the LLM to bypass or rewrite a security rejection.

If SQL passes validation but **execution fails**, the application can make a bounded number of correction attempts according to `MAX_SQL_CORRECTION_ATTEMPTS`.

## 11. Testing

Run the complete test suite:

```bash
pytest tests/ -v
```

The current CI suite contains **55 tests** and the latest successful GitHub Actions run passed all 55 tests.

Tests are designed to run without requiring a live production database or a real LLM API key. Database and LLM boundaries are mocked/faked where appropriate.

CI uses Python 3.11 and runs on pushes and pull requests targeting `master`.

## 12. Deployment

### Streamlit Community Cloud

1. Push the repository to GitHub.
2. Create a new Streamlit app pointing to `app.py`.
3. Add the required secrets in the Streamlit Secrets configuration.

Example:

```toml
DB_DIALECT = "mysql"
DB_HOST = "..."
DB_USER = "..."
DB_PASSWORD = "..."
DB_NAME = "..."
GEMINI_API_KEY = "..."
```

Do not paste real credentials into source files.

### Render

The repository includes `render.yaml`. Connect the repository in Render and configure the environment variables marked as secrets.

### VM deployment

For a Linux VM:

```bash
sudo apt update
sudo apt install -y python3-venv git

git clone https://github.com/shubhamwaghmare108/nlp_database_query_assistant.git
cd nlp_database_query_assistant

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env with production values

streamlit run app.py --server.port 8501 --server.address 0.0.0.0
```

For production, place Streamlit behind an appropriate reverse proxy and process/service manager, and use a least-privilege database account.

## 13. Operational Notes

- Keep database credentials and API keys outside Git.
- Prefer read-only database users.
- Keep `QUERY_TIMEOUT_SECONDS` enabled for production deployments.
- Review the generated SQL before granting the application access to sensitive data.
- Restrict database network access so only the application host can connect where practical.
- Use separate database profiles for separate environments or data sources.
- The application is not a replacement for database-level authorization; database permissions remain the final security boundary.

## 14. Future Enhancements

- Complete a second LLM provider implementation through the existing provider abstraction
- Persistent database-backed query history
- Role-based table and column access controls per user
- Column-level data masking/redaction
- Streamed LLM responses
- More provider-specific SQL dialect tests
- Expanded integration tests against disposable databases

## License

See the repository for the current project license and contribution information.
