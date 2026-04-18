# 📊 ERP Data Analyst Agent

> **Natural-language analytics for ERP systems** — powered by LangChain, GPT-4o, and Streamlit.
> Ask business questions in plain English. Get SQL, tables, and visualizations instantly.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)
![Streamlit](https://img.shields.io/badge/Streamlit-1.35%2B-FF4B4B?logo=streamlit)
![LangChain](https://img.shields.io/badge/LangChain-0.2%2B-1C3C3C)
![OpenAI](https://img.shields.io/badge/GPT--4o-OpenAI-412991?logo=openai)
![License](https://img.shields.io/badge/License-MIT-green)

---

## What it does

The ERP Analyst Agent lets non-technical business users query any SQL-based ERP database using plain English. It:

1. **Understands** the question using GPT-4o
2. **Generates** a safe, optimized SQL query
3. **Validates** the query is read-only (SELECT-only guard)
4. **Executes** against your database via SQLAlchemy
5. **Visualizes** results as bar, line, pie, scatter, or heatmap charts
6. **Explains** findings in plain language

No SQL knowledge required. No risk of data modification.

---

## Architecture

```
Streamlit UI
  ├── Sidebar      (DB connection, API key, sample questions, schema viewer)
  ├── Chat Tab     (NL → SQL → results pipeline)
  └── Dashboard    (auto KPI cards, pre-built charts, query history)
          │
    LangChain Agent (GPT-4o)
          │  generates SQL
    Safety Validator  ← SELECT-only guard, blocks all writes
          │
    SQLAlchemy (read-only connection)
          │  returns DataFrame
    Plotly Charts  (auto chart-type selection)
```

**Database support:** SQLite · PostgreSQL · MySQL · SQL Server · Oracle (via SQLAlchemy URIs)

---

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/YOUR_USERNAME/erp-analyst-agent.git
cd erp-analyst-agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Add your OpenAI key
cp .env.example .env
# Edit .env → OPENAI_API_KEY=sk-...

# 3. Generate demo data (1,200 orders, 120 customers, 80 products)
python data/generate_demo_db.py

# 4. Launch
streamlit run app/main.py
```

Or with the Makefile:

```bash
make install && make start   # installs deps, generates demo DB, launches app
```

---

## Sample Questions

**Sales & Revenue**
- "Top 10 customers by total revenue this year"
- "Monthly revenue trend for the last 12 months"
- "Which sales reps exceeded their quota last quarter?"

**Inventory & Supply Chain**
- "Products with lowest stock and highest demand"
- "Inventory turnover ratio by warehouse"
- "Suppliers with the most delayed deliveries"

**Finance & AR**
- "Open invoices older than 30 days"
- "Average days-to-pay by customer segment"
- "Customers who have exceeded their credit limits"

---

## Security Design

| Layer | Control |
|-------|---------|
| Query validation | `is_safe_query()` blocks all non-SELECT SQL before execution |
| SQLite mode | Opens in `?mode=ro` URI — filesystem-level read-only |
| Comment stripping | SQL comments removed before validation to prevent injection |
| Row cap | All generated queries include `LIMIT 500` |
| No credential storage | API keys and DB passwords are never persisted to disk |
| Blocklist | Regex blocks INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, TRUNCATE, EXEC, GRANT, REVOKE |

The safety validator runs **before every query**, regardless of whether it came from the LLM or was typed manually.

---

## Project Structure

```
erp-analyst-agent/
├── app/
│   ├── main.py                  # Streamlit entry point
│   ├── components/
│   │   ├── sidebar.py           # DB connection + settings
│   │   ├── chat.py              # NL → SQL → results pipeline
│   │   └── dashboard.py         # KPI cards + query history
│   └── utils/
│       ├── session.py           # Session state helpers
│       ├── database.py          # SQLAlchemy + safety validator
│       ├── agent.py             # LangChain agent + SQL extractor
│       └── charts.py            # Plotly visualization layer
├── data/
│   └── generate_demo_db.py      # Realistic ERP SQLite generator (Faker)
├── assets/
│   └── styles.css               # Custom dark-theme CSS
├── tests/
│   └── test_agent.py            # Pytest: safety, SQL extractor, integration
├── .env.example
├── .gitignore
├── Makefile
└── requirements.txt
```

---

## 1-Week Build Sprint

| Day | Focus | Deliverable |
|-----|-------|-------------|
| 1–2 | Foundation | Streamlit UI, multi-dialect DB connection, schema introspection, session state |
| 3–4 | AI Core | LangChain agent, SQL generator, safety validator, chart advisor |
| 5   | Visuals | Plotly renderer (5 chart types), KPI dashboard, CSV export |
| 6   | Polish | Demo DB (12 tables, 3 yrs data), sample questions, query history |
| 7   | Quality | Pytest suite, Makefile, README, `.env.example` |

---

## Running Tests

```bash
pytest tests/ -v
```

Covers: SQL safety guard · injection via comments · SQL extractor · chart advisor heuristics · SQLite integration (run_query, schema_info, empty results)

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | required | Your OpenAI API key |
| `OPENAI_MODEL` | `gpt-4o` | Model (`gpt-4o-mini` for lower cost) |
| `DATABASE_URL` | SQLite demo | SQLAlchemy connection string |
| `MAX_ROWS` | `500` | Max rows per query result |

---

## Extending

**New chart type:** add an `elif` branch in `app/utils/charts.py → auto_visualize()`

**New dashboard panel:** add to `CHART_QUERIES` dict in `app/components/dashboard.py`

**Different LLM:**
```python
# app/utils/agent.py
from langchain_anthropic import ChatAnthropic
llm = ChatAnthropic(model="claude-3-5-sonnet-20241022", ...)
```

**Your real ERP:** install the right SQLAlchemy driver, enter your URI in the sidebar — schema is introspected automatically.

---

## Stack

Python · LangChain · OpenAI GPT-4o · Streamlit · SQLAlchemy · Plotly · Pandas · Faker · Pytest

## License

MIT
