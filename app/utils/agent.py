"""
LangChain SQL Analyst Agent

Architecture:
  User NL question
      ↓
  SQLAgent (OpenAI function-calling)
      ↓ generates SQL
  SafetyValidator (SELECT-only guard)
      ↓
  SQLAlchemy → DataFrame
      ↓
  ChartAdvisor  (picks best Plotly chart type)
      ↓
  Streamlit render
"""

from __future__ import annotations
import re
from typing import Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from app.utils.database import is_safe_query

_CHART_KEYWORDS = {
    "over time": "line", "trend": "line", "monthly": "line",
    "weekly": "line", "daily": "line", "by month": "line",
    "distribution": "pie", "share": "pie", "breakdown": "pie", "percent": "pie",
    "compare": "bar", "top": "bar", "rank": "bar",
    "correlation": "scatter", "vs": "scatter",
    "heatmap": "heatmap", "matrix": "heatmap",
}

def advise_chart(question: str, df_columns: list[str]) -> str:
    q = question.lower()
    for kw, chart in _CHART_KEYWORDS.items():
        if kw in q:
            return chart
    numeric_cols = [c for c in df_columns if any(t in c.lower() for t in
        ["amount", "total", "count", "revenue", "qty", "quantity", "price", "cost", "profit"])]
    return "bar" if numeric_cols else "table"

_SQL_BLOCK = re.compile(r"```sql\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_BARE_SELECT = re.compile(r"(SELECT\s.+)", re.DOTALL | re.IGNORECASE)

def extract_sql(text: str) -> Optional[str]:
    m = _SQL_BLOCK.search(text)
    if m:
        return m.group(1).strip()
    m = _BARE_SELECT.search(text)
    if m:
        return m.group(1).strip()
    return None

DIRECT_SQL_PROMPT = """You are an expert SQL analyst for an ERP system.
Generate a single SELECT query for the question below.

STRICT RULES:
- Only use columns that EXIST in the schema below. Never guess or invent column names.
- Only SELECT statements. Always LIMIT 500.
- Use aliases. Round currency to 2 decimals.
- Dialect: {dialect}

EXACT SCHEMA (use ONLY these tables and columns):
{schema}

Question: {question}

Return ONLY the SQL query, no explanation, no markdown fences."""

def generate_sql_direct(question: str, schema: str, dialect: str, openai_api_key: str, model: str = "gpt-4o") -> str:
    llm = ChatOpenAI(model=model, temperature=0, api_key=openai_api_key)
    prompt = DIRECT_SQL_PROMPT.format(dialect=dialect, schema=schema, question=question)
    response = llm.invoke([HumanMessage(content=prompt)])
    sql = extract_sql(response.content) or response.content.strip()
    safe, reason = is_safe_query(sql)
    if not safe:
        raise ValueError(f"Generated unsafe SQL: {reason}\n\nSQL:\n{sql}")
    return sql

def generate_human_response(
    question: str,
    sql: str,
    df_summary: str,
    openai_api_key: str,
    model: str = "gpt-4o",
) -> str:
    llm = ChatOpenAI(model=model, temperature=0.3, api_key=openai_api_key)
    prompt = f"""You are a smart, friendly business analyst assistant.
A business owner just asked: "{question}"

You ran this SQL query and got these results:
{df_summary}

Now respond like a human analyst would — in 3-5 sentences max.
- Lead with the most important insight
- Mention specific numbers but explain what they mean
- Flag anything good or bad worth acting on
- Sound like a person, not a report
- No bullet points, no headers, just natural conversational text"""
    
    response = llm.invoke([HumanMessage(content=prompt)])
    return response.content.strip()