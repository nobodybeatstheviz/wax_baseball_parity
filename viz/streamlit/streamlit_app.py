"""Keeping Score — home runs witnessed, by year · Streamlit in Snowflake (Build 2.5, the 6th-inning door).

Source: the governed semantic view BASEBALL.SEMANTICS.KEEPING_SCORE (play_year × home_runs_witnessed).
Presentation: this app, deployed headlessly with `snow streamlit deploy` (see viz/README.md).
The number is the parity harness's G2 — 400 — and this page shows it, never states it.
"""
import altair as alt
import streamlit as st
from snowflake.snowpark.context import get_active_session

# NBTV chart tokens (~/.claude/skills/nbtv-design/tokens/chart.json is the home; values copied here by the
# deploy step would be a second appearance, so the app carries the four it needs as constants — brand is a ceiling).
BAR, SURFACE, INK, MUTED = "#DB1D1D", "#FAFAF7", "#1A1A1A", "#6B6B6B"
TITLE = "Home runs witnessed, by year"

SQL = """
SELECT * FROM SEMANTIC_VIEW(
    BASEBALL.SEMANTICS.KEEPING_SCORE
    DIMENSIONS plays.play_year
    METRICS    plays.home_runs_witnessed)
ORDER BY PLAY_YEAR
"""

st.set_page_config(page_title="Keeping Score · HR by year", layout="centered")
session = get_active_session()
df = session.sql(SQL).to_pandas()
df.columns = ["Year", "Home runs"]
df["Year"] = df["Year"].astype(int).astype(str)
total = int(df["Home runs"].sum())

st.caption("KEEPING SCORE · NOBODY BEATS THE VIZ")
st.title(TITLE)
st.markdown(f"Streamlit in Snowflake · **{total}** home runs · 178 games · 1984–2025")

chart = (
    alt.Chart(df)
    .mark_bar(color=BAR, cornerRadiusTopLeft=4, cornerRadiusTopRight=4, size=18)
    .encode(
        x=alt.X("Year:O", title=None, axis=alt.Axis(labelAngle=0, values=[y for y in df["Year"] if y.endswith(("0", "5"))])),
        y=alt.Y("Home runs:Q", title=None, axis=alt.Axis(tickMinStep=10, gridColor="#E4E1D8")),
        tooltip=["Year", "Home runs"],
    )
    .properties(height=380, background=SURFACE)
    .configure_axis(labelColor=MUTED, labelFont="Cascadia Code, Consolas, monospace", domainColor=MUTED, tickColor=MUTED)
    .configure_view(strokeWidth=0)
)
st.altair_chart(chart, use_container_width=True)

with st.expander(f"Table view · {len(df)} seasons"):
    st.dataframe(df, hide_index=True, use_container_width=True)

st.caption("Source: BASEBALL.SEMANTICS.KEEPING_SCORE, the same semantic view Cortex Analyst reads · "
           "the number is the parity harness's G2 (400 on six surfaces)")
