from statistics import mean

import plotly.graph_objects as go
import streamlit as st

from utils.aggregates import answer_counts, aroma_counts, decimal_label, score_statistics
from utils.constants import BALANCES, LOTS, RED_VARIETIES, SCORES, TECHNIQUES, WHITE_VARIETIES


BURGUNDY = "#762C47"
COLORS = (BURGUNDY, "#815344", "#6D7757", "#AB765C")


def plot(figure: go.Figure, key: str, *, height: int, left: int = 38, bottom: int = 54) -> None:
    figure.update_layout(
        height=height, margin=dict(t=14, b=bottom, l=left, r=22),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Source Sans 3, sans-serif", color="#30232B", size=13),
        hoverlabel=dict(bgcolor="#FFFFFF", font_color="#30232B"),
    )
    figure.update_xaxes(automargin=True, gridcolor="#E8DBD9", zeroline=False)
    figure.update_yaxes(automargin=True, gridcolor="#E8DBD9", zeroline=False)
    st.plotly_chart(figure, key=key, theme=None, width="stretch",
                    config={"displayModeBar": False, "responsive": True})


def horizontal_chart(title: str, counts: dict, key: str, *, respondent_count: int = 0) -> None:
    st.subheader(title)
    labels = sorted(counts, key=lambda label: -counts[label])
    labels.reverse()
    values = [counts[label] for label in labels]
    hover = "%{y}<br>%{x} válasz"
    percentages = [count / respondent_count for count in values] if respondent_count else None
    if respondent_count:
        hover += " · a válaszadók %{customdata:.0%}-a"
    figure = go.Figure(go.Bar(
        x=values, y=labels, orientation="h", marker_color=BURGUNDY,
        text=values, textposition="outside", cliponaxis=False,
        customdata=percentages, hovertemplate=hover + "<extra></extra>",
    ))
    figure.update_xaxes(title_text="Válaszok száma", rangemode="tozero", dtick=1 if max(values) < 10 else None,
                        range=[0, max(1, max(values) * 1.15)])
    figure.update_yaxes(showgrid=False, categoryorder="array", categoryarray=labels)
    plot(figure, key, height=max(250, 34 * len(labels) + 70))


def donut(title: str, records: list[dict], field: str, options) -> None:
    st.subheader(title)
    counts = answer_counts(records, field)
    if not counts:
        st.caption("Ehhez a kérdéshez még nincs aktív válasz.")
        return
    figure = go.Figure(go.Pie(
        labels=list(options), values=[counts[value] for value in options], hole=0.6, sort=False,
        marker=dict(colors=COLORS, line=dict(color="#FFFFFF", width=2)),
        textinfo="percent", textposition="inside", insidetextfont=dict(color="#FFFFFF"),
        hovertemplate="%{label}<br>%{value} válasz (%{percent})<extra></extra>",
    ))
    figure.update_layout(legend=dict(orientation="h", y=-0.04, x=0.5, xanchor="center"))
    plot(figure, f"chart-{field}", height=246, left=14, bottom=26)


def scores_chart(records: list[dict]) -> None:
    st.subheader("Pontszámok")
    counts, average, middle = score_statistics(records)
    st.caption(f"Átlag {decimal_label(average)} · Medián {decimal_label(middle)} · {len(records)} aktív értékelés")
    figure = go.Figure(go.Bar(
        x=list(counts), y=list(counts.values()), marker_color=BURGUNDY,
        customdata=[SCORES[score][0] for score in counts],
        hovertemplate="%{x} pont · %{customdata}<br>%{y} értékelés<extra></extra>",
    ))
    figure.update_xaxes(title_text="Pontszám", tickmode="array", tickvals=list(SCORES), showgrid=False)
    figure.update_yaxes(title_text="Értékelések száma", rangemode="tozero",
                        dtick=1 if max(counts.values()) < 10 else None)
    plot(figure, "chart-scores", height=306)


def comparison_chart(records: list[dict]) -> None:
    by_lot = {lot: [] for lot in LOTS}
    for record in records:
        by_lot[record["lot"]].append(record["score"])
    st.subheader("Átlagpontszám tételenként")
    figure = go.Figure(go.Bar(
        x=[f"{lot}. tétel" for lot in LOTS],
        y=[mean(scores) if scores else None for scores in by_lot.values()],
        customdata=[[decimal_label(mean(scores)) if scores else "–", len(scores)] for scores in by_lot.values()],
        marker_color=[COLORS[1] if wine == "Fehérbor" else BURGUNDY for wine in LOTS.values()],
        hovertemplate="%{x}<br>Átlag %{customdata[0]}/10<br>%{customdata[1]} értékelés<extra></extra>",
    ))
    figure.update_xaxes(showgrid=False)
    figure.update_yaxes(title_text="Átlagpontszám", range=[0, 10.5], dtick=2)
    plot(figure, "chart-lot-comparison", height=280)


def render_charts(records: list[dict], lot: int | None) -> None:
    if not records:
        st.info("Ehhez a tételhez még nem érkezett aktív értékelés.")
        return
    with st.container(border=True):
        scores_chart(records)
    if lot is None:
        with st.container(border=True):
            comparison_chart(records)
    with st.container(border=True):
        horizontal_chart("Aromacsoportok", aroma_counts(records), "chart-aromas", respondent_count=len(records))
    with st.container(border=True):
        first, second = st.columns(2)
        with first:
            donut("Borkészítési technológia", records, "technique", TECHNIQUES)
        with second:
            donut("Egyensúly", records, "balance", BALANCES)
    with st.container(border=True):
        if lot is None:
            white, red = st.columns(2)
            with white:
                donut("Illatosság (fehérborok)", records, "fragrance", WHITE_VARIETIES)
            with red:
                donut("Fajtacsoport (vörösborok)", records, "variety_group", RED_VARIETIES)
        elif LOTS[lot] == "Fehérbor":
            donut("Illatosság (fehérborok)", records, "fragrance", WHITE_VARIETIES)
        else:
            donut("Fajtacsoport (vörösborok)", records, "variety_group", RED_VARIETIES)
    with st.container(border=True):
        horizontal_chart("Szőlőfajták", answer_counts(records, "grape"), "chart-grapes")
    with st.container(border=True):
        horizontal_chart("Borvidékek", answer_counts(records, "region"), "chart-regions")
