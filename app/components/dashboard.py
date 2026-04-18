"""
Dashboard tab — fully dynamic, works with ANY database.
"""
from __future__ import annotations
import pandas as pd
import sqlalchemy as sa
from sqlalchemy import inspect
import streamlit as st
from app.utils.database import run_query
from app.utils.charts import auto_visualize

def _get_tables(engine):
    return inspect(engine).get_table_names()

def _get_columns(engine, table):
    return [c["name"] for c in inspect(engine).get_columns(table)]

def _find_table(engine, *candidates):
    tables_lower = {t.lower(): t for t in _get_tables(engine)}
    for c in candidates:
        if c.lower() in tables_lower:
            return tables_lower[c.lower()]
    return None

def _find_col(cols, *candidates):
    cols_lower = {c.lower(): c for c in cols}
    for c in candidates:
        if c.lower() in cols_lower:
            return cols_lower[c.lower()]
    return None

def _build_kpis(engine):
    kpis = {}
    orders_tbl = _find_table(engine, "orders","sales","sales_orders","invoices","transactions")
    if orders_tbl:
        cols = _get_columns(engine, orders_tbl)
        amt = _find_col(cols,"total_amount","amount","total","revenue","value","net_amount")
        status = _find_col(cols,"status","order_status","state")
        cust = _find_col(cols,"customer_id","client_id","account_id")
        where = f"WHERE {status} != 'cancelled'" if status else ""
        if amt:
            kpis["Total Revenue"] = f"SELECT ROUND(SUM({amt}),2) AS total_revenue FROM {orders_tbl} {where}"
            kpis["Avg Order Value"] = f"SELECT ROUND(AVG({amt}),2) AS avg_order FROM {orders_tbl} {where}"
        kpis["Total Orders"] = f"SELECT COUNT(*) AS total_orders FROM {orders_tbl}"
        if cust:
            kpis["Active Customers"] = f"SELECT COUNT(DISTINCT {cust}) AS customers FROM {orders_tbl}"
    prod_tbl = _find_table(engine,"products","items","inventory","product")
    if prod_tbl:
        kpis["Total Products"] = f"SELECT COUNT(*) AS products FROM {prod_tbl}"
    if not kpis:
        for tbl in _get_tables(engine)[:4]:
            kpis[f"{tbl} rows"] = f"SELECT COUNT(*) AS row_count FROM {tbl}"
    return kpis

def _build_charts(engine):
    charts = {}
    dialect = engine.dialect.name
    orders_tbl = _find_table(engine,"orders","sales","sales_orders","transactions")
    if orders_tbl:
        cols = _get_columns(engine, orders_tbl)
        amt = _find_col(cols,"total_amount","amount","total","revenue","value","net_amount")
        date = _find_col(cols,"order_date","date","created_at","sale_date","transaction_date")
        status = _find_col(cols,"status","order_status","state")
        cust = _find_col(cols,"customer_id","client_id","account_id")
        if amt and date:
            if dialect == "sqlite":
                m = f"strftime('%Y-%m', {date})"
            elif dialect in ("postgresql","mssql"):
                m = f"TO_CHAR({date}, 'YYYY-MM')"
            else:
                m = f"DATE_FORMAT({date}, '%Y-%m')"
            where = f"WHERE {status} != 'cancelled'" if status else ""
            charts["Revenue over time"] = {
                "sql": f"SELECT {m} AS month, ROUND(SUM({amt}),2) AS revenue FROM {orders_tbl} {where} GROUP BY 1 ORDER BY 1 LIMIT 24",
                "chart": "line"
            }
        if status:
            charts["Orders by status"] = {
                "sql": f"SELECT {status}, COUNT(*) AS count FROM {orders_tbl} GROUP BY 1 ORDER BY 2 DESC",
                "chart": "pie"
            }
        cust_tbl = _find_table(engine,"customers","clients","accounts")
        if amt and cust and cust_tbl:
            ccols = _get_columns(engine, cust_tbl)
            name = _find_col(ccols,"company_name","name","customer_name","client_name","full_name","account_name")
            pk = _find_col(ccols,"customer_id","id","client_id","account_id")
            where = f"WHERE o.{status} != 'cancelled'" if status else ""
            if name and pk:
                charts["Top 10 customers"] = {
                    "sql": f"SELECT c.{name}, ROUND(SUM(o.{amt}),2) AS revenue FROM {orders_tbl} o JOIN {cust_tbl} c ON o.{cust}=c.{pk} {where} GROUP BY 1 ORDER BY 2 DESC LIMIT 10",
                    "chart": "bar"
                }
    prod_tbl = _find_table(engine,"products","items","product")
    if prod_tbl:
        pcols = _get_columns(engine, prod_tbl)
        cat = _find_col(pcols,"category","type","product_type","department","group")
        if cat:
            charts["Products by category"] = {
                "sql": f"SELECT {cat}, COUNT(*) AS count FROM {prod_tbl} WHERE {cat} IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 10",
                "chart": "bar"
            }
    if not charts:
        tables = _get_tables(engine)[:6]
        if tables:
            union = " UNION ALL ".join([f"SELECT '{t}' AS tbl, COUNT(*) AS rows FROM {t}" for t in tables])
            charts["Rows per table"] = {"sql": union, "chart": "bar"}
    return charts

def _metric_card(label, value):
    st.markdown(f"""
    <div style="background:#12122a;border:1px solid #2a2a4a;border-radius:12px;padding:1.2rem 1.5rem;margin-bottom:0.5rem">
        <div style="font-size:0.75rem;color:#888;letter-spacing:0.1em;text-transform:uppercase">{label}</div>
        <div style="font-size:1.8rem;font-weight:700;color:#00D4FF;margin:0.3rem 0">{value}</div>
    </div>""", unsafe_allow_html=True)

def render_dashboard():
    if not st.session_state.db_connected:
        st.info("Connect to a database in the sidebar to see the dashboard.")
        return
    engine = st.session_state.db_engine
    st.markdown("## ERP Overview Dashboard")
    st.caption("Auto-generated from your connected database schema.")

    kpis = _build_kpis(engine)
    kpi_cols = st.columns(len(kpis))
    for col, (label, sql) in zip(kpi_cols, kpis.items()):
        with col:
            df, err = run_query(engine, sql)
            if df is not None and not df.empty:
                val = df.iloc[0, 0]
                formatted = f"{val:,.2f}" if isinstance(val, float) else f"{val:,}"
                _metric_card(label, formatted)
            else:
                _metric_card(label, "N/A")

    st.divider()
    charts = _build_charts(engine)
    chart_items = list(charts.items())
    for i in range(0, len(chart_items), 2):
        cols = st.columns(2)
        for j, col in enumerate(cols):
            if i + j >= len(chart_items): break
            name, cfg = chart_items[i + j]
            with col:
                st.markdown(f"**{name}**")
                df, err = run_query(engine, cfg["sql"])
                if df is not None and not df.empty:
                    fig = auto_visualize(df, chart_type=cfg["chart"], title=name)
                    if fig:
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.dataframe(df, use_container_width=True, hide_index=True)
                else:
                    st.warning(f"No data ({err})")

    st.divider()
    if st.session_state.query_history:
        st.markdown("## Query History")
        history_df = pd.DataFrame(st.session_state.query_history)
        st.dataframe(history_df[["question","rows","chart"]].rename(columns={"question":"Question","rows":"Rows","chart":"Chart"}), use_container_width=True, hide_index=True)
        selected = st.selectbox("View SQL", options=range(len(st.session_state.query_history)), format_func=lambda i: st.session_state.query_history[i]["question"][:80])
        if selected is not None:
            st.code(st.session_state.query_history[selected]["sql"], language="sql")