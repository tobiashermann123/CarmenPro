"""
CarmenPro Dashboard — Streamlit app
Run: streamlit run dashboard/app.py
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime

from layers.layer3_storage.client import get_client

st.set_page_config(
    page_title="CarmenPro Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Styling ────────────────────────────────────────────────────────────────────
SIGNAL_COLORS = {
    "Strong Buy":     "#22763d",
    "Buy":            "#48bb78",
    "Hold/Accumulate":"#d69e2e",
    "Neutral":        "#718096",
    "Caution":        "#dd6b20",
    "Avoid":          "#c53030",
}

GRADE_COLORS = {
    "A+": "#22763d", "A": "#48bb78", "B": "#d69e2e",
    "C":  "#dd6b20", "D": "#c53030", "F": "#742a2a",
}

# ── Data loading ───────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_signals() -> pd.DataFrame:
    client = get_client()
    result = (
        client.table("trade_signals")
        .select("*")
        .order("generated_at", desc=True)
        .execute()
    )
    if not result.data:
        return pd.DataFrame()
    df = pd.DataFrame(result.data)
    df["generated_at"] = pd.to_datetime(df["generated_at"])
    return df


@st.cache_data(ttl=300)
def load_daily_brief() -> dict | None:
    client = get_client()
    result = (
        client.table("system_state")
        .select("value")
        .eq("key", "daily_brief")
        .limit(1)
        .execute()
    )
    if result.data:
        return result.data[0].get("value")
    return None


def latest_per_ticker(df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_values("generated_at", ascending=False).drop_duplicates("ticker")


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("CarmenPro")
    st.caption("EUR-denominated quant fund")
    st.divider()
    page = st.radio(
        "View",
        ["Signal Overview", "Score History", "DCF Valuation", "Sub-Scores", "Daily Brief"],
        index=0,
    )
    st.divider()
    if st.button("Refresh data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.caption(f"Last refresh: {datetime.now().strftime('%H:%M:%S')}")

# ── Load data ──────────────────────────────────────────────────────────────────
df_all  = load_signals()
brief   = load_daily_brief()

if df_all.empty:
    st.error("No signals in database. Run `/trade score` or `/trade analyze` first.")
    st.stop()

df_latest = latest_per_ticker(df_all)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 1 — Signal Overview
# ══════════════════════════════════════════════════════════════════════════════
if page == "Signal Overview":
    st.header("Signal Overview")
    st.caption("Latest signal per ticker — scores, valuation, action state")

    # KPI row
    col1, col2, col3, col4 = st.columns(4)
    n_buy     = df_latest["signal"].isin(["Strong Buy", "Buy"]).sum()
    n_accum   = df_latest["signal"].isin(["Hold/Accumulate"]).sum()
    n_caution = df_latest["signal"].isin(["Caution", "Avoid"]).sum()
    col1.metric("Tickers tracked", len(df_latest))
    col2.metric("Buy signals",     int(n_buy),     delta=None)
    col3.metric("Accumulate",      int(n_accum))
    col4.metric("Caution / Avoid", int(n_caution))

    st.divider()

    # Build display table
    cols_show = [
        "ticker", "signal", "grade", "composite_score",
        "margin_of_safety_pct", "piotroski_score",
        "action_state",
        "intrinsic_value_eur", "entry_low_eur", "stop_eur", "target1_eur",
        "source", "generated_at",
    ]
    cols_present = [c for c in cols_show if c in df_latest.columns]
    tbl = df_latest[cols_present].copy()

    if "margin_of_safety_pct" in tbl.columns:
        tbl["margin_of_safety_pct"] = tbl["margin_of_safety_pct"].apply(
            lambda x: f"{x:.1f}%" if pd.notna(x) else "—"
        )
    for col in ["intrinsic_value_eur", "entry_low_eur", "stop_eur", "target1_eur"]:
        if col in tbl.columns:
            tbl[col] = tbl[col].apply(lambda x: f"€{x:.2f}" if pd.notna(x) else "—")
    if "composite_score" in tbl.columns:
        tbl["composite_score"] = tbl["composite_score"].apply(
            lambda x: f"{x:.0f}/100" if pd.notna(x) else "—"
        )
    if "generated_at" in tbl.columns:
        tbl["generated_at"] = tbl["generated_at"].dt.strftime("%Y-%m-%d")

    tbl = tbl.rename(columns={
        "ticker": "Ticker", "signal": "Signal", "grade": "Grade",
        "composite_score": "Score", "margin_of_safety_pct": "MoS %",
        "piotroski_score": "Piotroski", "action_state": "Action",
        "intrinsic_value_eur": "IV (€)", "entry_low_eur": "Entry Low (€)",
        "stop_eur": "Stop (€)", "target1_eur": "T1 (€)",
        "source": "Source", "generated_at": "Date",
    })
    tbl = tbl.sort_values("Score", ascending=False) if "Score" in tbl.columns else tbl

    def colour_signal(val):
        c = SIGNAL_COLORS.get(val, "")
        return f"color: {c}; font-weight: bold" if c else ""

    def colour_grade(val):
        c = GRADE_COLORS.get(str(val), "")
        return f"color: {c}; font-weight: bold" if c else ""

    styled = tbl.style
    if "Signal" in tbl.columns:
        styled = styled.map(colour_signal, subset=["Signal"])
    if "Grade" in tbl.columns:
        styled = styled.map(colour_grade, subset=["Grade"])

    st.dataframe(styled, use_container_width=True, hide_index=True)

    # Signal distribution chart
    st.subheader("Signal Distribution")
    sig_counts = df_latest["signal"].value_counts().reset_index()
    sig_counts.columns = ["Signal", "Count"]
    sig_counts["Color"] = sig_counts["Signal"].map(SIGNAL_COLORS).fillna("#718096")
    fig = px.bar(
        sig_counts, x="Signal", y="Count",
        color="Signal", color_discrete_map=SIGNAL_COLORS,
        height=300,
    )
    fig.update_layout(showlegend=False, margin=dict(t=20, b=20))
    st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 2 — Score History
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Score History":
    st.header("Score History")
    st.caption("Composite score over time — tracks drift and momentum changes")

    if "composite_score" not in df_all.columns:
        st.warning("No composite_score data available.")
        st.stop()

    tickers = sorted(df_all["ticker"].unique())
    selected = st.multiselect("Select tickers", tickers, default=tickers[:8])

    df_hist = df_all[df_all["ticker"].isin(selected)].copy()
    df_hist["date"] = df_hist["generated_at"].dt.date

    fig = px.line(
        df_hist.sort_values("generated_at"),
        x="date", y="composite_score",
        color="ticker", markers=True,
        height=450,
        labels={"composite_score": "Composite Score", "date": "Date"},
    )
    fig.add_hline(y=70, line_dash="dot", line_color="green",
                  annotation_text="Buy threshold (70)")
    fig.add_hline(y=40, line_dash="dot", line_color="red",
                  annotation_text="Caution threshold (40)")
    fig.update_layout(margin=dict(t=20))
    st.plotly_chart(fig, use_container_width=True)

    # Latest scores table
    st.subheader("Current Scores")
    score_tbl = (
        df_latest[df_latest["ticker"].isin(selected)][["ticker", "composite_score", "grade", "signal"]]
        .sort_values("composite_score", ascending=False)
    )
    st.dataframe(score_tbl, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 3 — DCF Valuation
# ══════════════════════════════════════════════════════════════════════════════
elif page == "DCF Valuation":
    st.header("DCF Valuation Summary")
    st.caption("Intrinsic value vs current price — margin of safety ranking")

    dcf_cols = ["intrinsic_value_eur", "margin_of_safety_pct", "piotroski_score",
                "dcf_wacc", "dcf_fcf_growth_rate"]
    available = [c for c in dcf_cols if c in df_latest.columns]

    if not available:
        st.warning("No DCF valuation data yet. Run the nightly valuation flow first.")
        st.stop()

    df_dcf = df_latest.dropna(subset=["intrinsic_value_eur"]).copy()

    if df_dcf.empty:
        st.info("DCF values not yet computed. Run `nightly_valuation_flow` to populate.")
        st.stop()

    # MoS chart
    st.subheader("Margin of Safety")
    fig = px.bar(
        df_dcf.sort_values("margin_of_safety_pct", ascending=True),
        x="margin_of_safety_pct", y="ticker",
        orientation="h",
        color="margin_of_safety_pct",
        color_continuous_scale=["#c53030", "#d69e2e", "#22763d"],
        range_color=[-50, 50],
        labels={"margin_of_safety_pct": "Margin of Safety %", "ticker": "Ticker"},
        height=max(300, len(df_dcf) * 40),
    )
    fig.add_vline(x=0, line_dash="solid", line_color="gray")
    fig.add_vline(x=30, line_dash="dot", line_color="green",
                  annotation_text="30% MoS target")
    fig.update_layout(margin=dict(t=20))
    st.plotly_chart(fig, use_container_width=True)

    # Detailed table
    st.subheader("Valuation Detail")
    tbl_cols = ["ticker", "intrinsic_value_eur", "margin_of_safety_pct",
                "piotroski_score", "dcf_wacc", "dcf_fcf_growth_rate", "signal"]
    tbl_cols = [c for c in tbl_cols if c in df_dcf.columns]
    tbl = df_dcf[tbl_cols].sort_values("margin_of_safety_pct", ascending=False)
    tbl = tbl.rename(columns={
        "ticker": "Ticker",
        "intrinsic_value_eur": "IV (€)",
        "margin_of_safety_pct": "MoS %",
        "piotroski_score": "Piotroski",
        "dcf_wacc": "WACC %",
        "dcf_fcf_growth_rate": "FCF Growth %",
        "signal": "Signal",
    })
    st.dataframe(tbl, use_container_width=True, hide_index=True)

    # Piotroski distribution
    if "Piotroski" in tbl.columns:
        st.subheader("Piotroski F-Score Distribution")
        fig2 = px.histogram(
            tbl.dropna(subset=["Piotroski"]),
            x="Piotroski", nbins=10, height=280,
            labels={"Piotroski": "F-Score (0-9)"},
        )
        fig2.update_layout(margin=dict(t=20))
        st.plotly_chart(fig2, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 4 — Sub-Scores
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Sub-Scores":
    st.header("Sub-Score Breakdown")
    st.caption("Per-dimension scores for the latest signal on each ticker")

    if "sub_scores_json" not in df_latest.columns:
        st.warning("No sub-score data available.")
        st.stop()

    df_sub = df_latest.dropna(subset=["sub_scores_json"]).copy()
    if df_sub.empty:
        st.info("No sub-score data yet. Run /trade score or /trade analyze to populate.")
        st.stop()

    # Expand sub-scores into flat columns
    def expand_sub(row):
        ss = row["sub_scores_json"] or {}
        out: dict[str, float] = {}
        for dim, subs in ss.items():
            if isinstance(subs, dict):
                for k, v in subs.items():
                    try:
                        out[f"{dim}.{k}"] = float(v)
                    except (TypeError, ValueError):
                        pass
        return pd.Series(out)

    expanded = df_sub.apply(expand_sub, axis=1)
    df_radar = pd.concat([df_sub[["ticker"]].reset_index(drop=True),
                          expanded.reset_index(drop=True)], axis=1)

    ticker_sel = st.selectbox("Select ticker", df_radar["ticker"].tolist())
    row = df_radar[df_radar["ticker"] == ticker_sel].iloc[0]
    sub_vals = row.drop("ticker").dropna()

    if sub_vals.empty:
        st.warning("No sub-score data for this ticker.")
    else:
        # Radar chart
        categories = sub_vals.index.tolist()
        values     = sub_vals.values.tolist()
        values_closed = values + [values[0]]
        categories_closed = categories + [categories[0]]

        fig = go.Figure(go.Scatterpolar(
            r=values_closed, theta=categories_closed,
            fill="toself", name=ticker_sel,
            line_color="#4299e1",
        ))
        fig.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 20])),
            showlegend=False,
            height=500,
        )
        st.plotly_chart(fig, use_container_width=True)

        # Table
        sub_tbl = sub_vals.reset_index()
        sub_tbl.columns = ["Dimension", "Score"]
        sub_tbl["Score"] = sub_tbl["Score"].round(1)
        st.dataframe(sub_tbl, use_container_width=True, hide_index=True)

    # All tickers comparison — heatmap of total dimension scores
    st.subheader("All Tickers — Dimension Totals")
    dim_cols = {}
    for col in expanded.columns:
        dim = col.split(".")[0]
        dim_cols.setdefault(dim, []).append(col)

    totals: dict[str, list] = {"ticker": df_radar["ticker"].tolist()}
    for dim, cols in dim_cols.items():
        totals[dim] = df_radar[cols].sum(axis=1).round(1).tolist()

    df_totals = pd.DataFrame(totals).set_index("ticker")
    if not df_totals.empty:
        fig2 = px.imshow(
            df_totals,
            color_continuous_scale="RdYlGn",
            aspect="auto", height=max(300, len(df_totals) * 40),
            labels=dict(color="Score"),
        )
        fig2.update_layout(margin=dict(t=20))
        st.plotly_chart(fig2, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 5 — Daily Brief
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Daily Brief":
    st.header("Daily Brief")

    if not brief:
        st.info("No daily brief available. Run the daily flow first.")
    else:
        date_str = brief.get("date", "—")
        st.subheader(f"Brief for {date_str}")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**BUY NOW**")
            for t in brief.get("buy_now", []):
                st.success(f"✅ {t}")
        with col2:
            st.markdown("**LIMIT QUEUED**")
            for t in brief.get("limit_queued", []):
                st.info(f"📋 {t}")

        st.divider()

        if "market_context" in brief:
            st.markdown("**Market Context**")
            st.write(brief["market_context"])

        if "sector_rotation" in brief:
            st.markdown("**Sector Rotation**")
            st.write(brief["sector_rotation"])

        if "risk_flags" in brief:
            st.markdown("**Risk Flags**")
            for flag in brief.get("risk_flags", []):
                st.warning(flag)

    # Recent signals history
    st.divider()
    st.subheader("Recent Scoring Activity")
    recent = df_all.sort_values("generated_at", ascending=False).head(20)
    cols_show = ["ticker", "signal", "composite_score", "source", "generated_at"]
    cols_show = [c for c in cols_show if c in recent.columns]
    st.dataframe(recent[cols_show], use_container_width=True, hide_index=True)

# ── Footer ─────────────────────────────────────────────────────────────────────
st.sidebar.divider()
st.sidebar.caption("CarmenPro — EUR fund ~€100K")
st.sidebar.caption("AI + hardware supply chain focus")
