"""
Tests for ERP Analyst Agent
Run: pytest tests/ -v
"""

import pytest
import pandas as pd
import sqlalchemy as sa

from app.utils.database import is_safe_query, run_query, create_engine, get_schema_info
from app.utils.agent import extract_sql, advise_chart


# ── Safety tests ──────────────────────────────────────────────────────────────

class TestSafetyGuard:
    def test_select_allowed(self):
        safe, _ = is_safe_query("SELECT * FROM orders LIMIT 10")
        assert safe

    def test_with_cte_allowed(self):
        sql = "WITH cte AS (SELECT id FROM customers) SELECT * FROM cte"
        safe, _ = is_safe_query(sql)
        assert safe

    def test_explain_allowed(self):
        safe, _ = is_safe_query("EXPLAIN SELECT * FROM orders")
        assert safe

    def test_insert_blocked(self):
        safe, reason = is_safe_query("INSERT INTO orders VALUES (1, 2, 3)")
        assert not safe
        assert "write" in reason.lower() or "INSERT" in reason

    def test_update_blocked(self):
        safe, _ = is_safe_query("UPDATE customers SET name='x' WHERE id=1")
        assert not safe

    def test_delete_blocked(self):
        safe, _ = is_safe_query("DELETE FROM orders WHERE order_id = 1")
        assert not safe

    def test_drop_blocked(self):
        safe, _ = is_safe_query("DROP TABLE customers")
        assert not safe

    def test_create_blocked(self):
        safe, _ = is_safe_query("CREATE TABLE hacked (id INT)")
        assert not safe

    def test_truncate_blocked(self):
        safe, _ = is_safe_query("TRUNCATE TABLE orders")
        assert not safe

    def test_comment_injection_blocked(self):
        # SQL injection attempt via comment stripping
        sql = "/* fake */ DROP TABLE orders; -- SELECT 1"
        safe, _ = is_safe_query(sql)
        assert not safe


# ── SQL extraction ────────────────────────────────────────────────────────────

class TestSQLExtractor:
    def test_extract_sql_block(self):
        text = "Here is the query:\n```sql\nSELECT * FROM orders\n```"
        sql = extract_sql(text)
        assert sql == "SELECT * FROM orders"

    def test_extract_bare_select(self):
        text = "The answer is SELECT id FROM customers LIMIT 5"
        sql = extract_sql(text)
        assert "SELECT" in sql.upper()

    def test_extract_returns_none_for_garbage(self):
        sql = extract_sql("There is no query here.")
        assert sql is None


# ── Chart advisor ─────────────────────────────────────────────────────────────

class TestChartAdvisor:
    def test_trend_suggests_line(self):
        assert advise_chart("Show revenue trend over time", ["month", "revenue"]) == "line"

    def test_top_suggests_bar(self):
        assert advise_chart("Top 10 customers", ["company_name", "revenue"]) == "bar"

    def test_distribution_suggests_pie(self):
        assert advise_chart("Show distribution by category", ["category", "count"]) == "pie"

    def test_scatter_on_vs(self):
        assert advise_chart("Revenue vs Cost by product", ["revenue", "cost"]) == "scatter"


# ── Integration: SQLite in-memory ─────────────────────────────────────────────

@pytest.fixture
def mem_engine():
    """Create an in-memory SQLite DB with a simple schema."""
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        conn.execute(sa.text("""
            CREATE TABLE customers (
                customer_id INTEGER PRIMARY KEY,
                company_name TEXT,
                region TEXT,
                credit_limit REAL
            )
        """))
        conn.execute(sa.text("""
            INSERT INTO customers VALUES
            (1, 'Acme Corp', 'North America', 50000.0),
            (2, 'Globex', 'Europe', 75000.0),
            (3, 'Initech', 'APAC', 30000.0)
        """))
        conn.commit()
    return engine


class TestDatabaseUtils:
    def test_run_select(self, mem_engine):
        df, err = run_query(mem_engine, "SELECT * FROM customers")
        assert err == ""
        assert len(df) == 3
        assert "company_name" in df.columns

    def test_run_write_blocked(self, mem_engine):
        df, err = run_query(mem_engine, "INSERT INTO customers VALUES (4, 'Bad', 'X', 0)")
        assert df is None
        assert len(err) > 0

    def test_schema_info_contains_table(self, mem_engine):
        schema = get_schema_info(mem_engine)
        assert "customers" in schema
        assert "company_name" in schema

    def test_empty_result(self, mem_engine):
        df, err = run_query(mem_engine, "SELECT * FROM customers WHERE customer_id = 999")
        assert err == ""
        assert len(df) == 0
