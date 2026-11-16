from base64 import b64encode
from html import escape

import plotly.graph_objects as go
import streamlit as st

from utils.aggregates import answer_counts, aroma_counts, decimal_label
from utils.constants import BALANCES, LOTS, RED_VARIETIES, SCORES, TECHNIQUES, WHITE_VARIETIES


BURGUNDY = "#762C47"
GRAY = "#A6A0A4"


def leading_colors(values) -> list[str]:
    highest = max((value for value in values if value is not None), default=0)
    return [BURGUNDY if highest > 0 and value == highest else GRAY for value in values]


def chart_title(title: str, caption: str) -> str:
    return (f'<h3 class="geoterroir-chart-title">{escape(title)}</h3>'
            f'<p class="dg-chart-caption">{escape(caption)}</p>')


def percent_label(share: float) -> str:
    return f"{share:.1f}".removesuffix(".0").replace(".", ",") + "%"


def plot(figure: go.Figure, key: str) -> None:
    figure.update_layout(
        height=155,
        margin=dict(t=12, b=27, l=32, r=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Source Sans 3, Segoe UI, sans-serif", color="#30232B", size=12),
        hoverlabel=dict(bgcolor="#FFFFFF", font_color="#30232B"),
    )
    figure.update_xaxes(automargin=True, showgrid=False, zeroline=False)
    figure.update_yaxes(
        automargin=True,
        gridcolor="#E8DBD9",
        zeroline=False,
        showticklabels=True,
        tickformat="d",
    )
    st.plotly_chart(
        figure, key=key, theme=None, width="stretch",
        config={"displayModeBar": False, "responsive": True},
    )


def ranking_chart(title: str, counts: dict, *, respondent_count: int = 0) -> None:
    items = sorted(counts.items(), key=lambda item: -item[1])
    maximum = items[0][1] if items else 0
    heading = chart_title(title, "Válaszok száma")
    if not maximum:
        st.html(f'{heading}<p class="dg-chart-empty">Még nincs válasz.</p>')
        return

    entries = []
    for (name, count), color in zip(items, leading_colors([count for _, count in items])):
        label = escape(name)
        detail = f"{label} · {count} válasz"
        if respondent_count:
            detail += f" · a kitöltők {percent_label(100 * count / respondent_count)}-a"
        entries.append(
            f'<li title="{detail}"><span class="dg-rank-label">{label}</span>'
            f'<span class="dg-rank-track" aria-hidden="true">'
            f'<i style="width:{100 * count / maximum:.3f}%;background:{color}"></i></span>'
            f'<strong>{count}</strong></li>'
        )

    visible = f'<ul class="dg-ranking">{"".join(entries[:5])}</ul>'
    more = ""
    if len(entries) > 5:
        more = (f'<details class="dg-rank-more"><summary>További válaszok</summary>'
                f'<ul class="dg-ranking">{"".join(entries[5:])}</ul></details>')
    st.html(f"{heading}{visible}{more}")


def donut(description: str, records: list[dict], field: str, options) -> None:
    counts = answer_counts(records, field)
    values = [counts[label] for label in options]
    total = sum(values)
    arcs, legend = [], []
    offset = 0.0
    gap = 5 if sum(bool(value) for value in values) > 1 else 0
    for label, value, color in zip(options, values, leading_colors(values)):
        label = escape(label)
        share = value / total * 100 if total else 0
        if value:
            length = max(0.01, share - gap)
            arcs.append(
                f'<circle cx="60" cy="60" r="45" pathLength="100" stroke="{color}" '
                f'stroke-dasharray="{length:.3f} {100-length:.3f}" '
                f'stroke-dashoffset="{-offset-gap/2:.3f}" transform="rotate(-90 60 60)"/>'
            )
            offset += share
        legend.append(
            f'<li><span class="geoterroir-swatch" style="background:{color}"></span>'
            f'<span>{label}</span><strong>{percent_label(share)} <small>({value})</small></strong></li>'
        )

    leader = percent_label(100 * max(values) / total) if total else "–"
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" '
        f'fill="none" stroke-width="10" stroke-linecap="round">'
        f'<circle cx="60" cy="60" r="45" stroke="#EEE8EB"/>{"".join(arcs)}'
        f'<text x="60" y="65" text-anchor="middle" fill="#30232B" font-family="sans-serif" '
        f'font-size="20" font-weight="700">{leader}</text></svg>'
    )
    source = b64encode(svg.encode("utf-8")).decode("ascii")
    st.html(
        f'<section class="geoterroir-ring">'
        f'<img src="data:image/svg+xml;base64,{source}" alt="{escape(description)} · {total} válasz · {leader}">'
        f'<ul>{"".join(legend)}</ul></section>'
    )


def scores_chart(records: list[dict]) -> None:
    st.html(chart_title("Pontszámok", "Értékelések száma pontszámonként"))
    counts = answer_counts(records, "score")
    values = [counts[score] for score in SCORES]
    maximum = max(values)
    figure = go.Figure(go.Bar(
        x=list(SCORES),
        y=values,
        marker=dict(color=leading_colors(values), cornerradius=5),
        width=0.34,
        text=[value or "" for value in values],
        textposition="outside",
        cliponaxis=False,
        customdata=[label for label, _ in SCORES.values()],
        hovertemplate="%{x} pont · %{customdata}<br>%{y} értékelés<extra></extra>",
    ))
    figure.update_xaxes(tickmode="array", tickvals=list(SCORES))
    figure.update_yaxes(
        range=[0, max(1, maximum) * 1.18],
        tick0=0,
        dtick=max(1, (maximum + 3) // 4),
    )
    plot(figure, "chart-scores")


def comparison_chart(averages: dict[int, tuple[float, int]]) -> None:
    st.html(chart_title("Átlagpontszám tételenként", "Mind az öt tétel · 10 pontos skála"))
    scores = [averages.get(number, (None, 0)) for number in LOTS]
    values = [average for average, _ in scores]
    formatted = [decimal_label(average) for average in values]
    categories = [str(number) for number in LOTS]
    figure = go.Figure(go.Bar(
        x=categories,
        y=values,
        customdata=[
            [lot.name, label, count]
            for lot, label, (_, count) in zip(LOTS.values(), formatted, scores)
        ],
        marker=dict(color=leading_colors(values), cornerradius=5),
        width=0.30,
        text=[label if value is not None else "" for label, value in zip(formatted, values)],
        textposition="outside",
        cliponaxis=False,
        hovertemplate="%{customdata[0]}<br>Átlag %{customdata[1]}/10<br>%{customdata[2]} értékelés<extra></extra>",
    ))
    figure.update_xaxes(
        type="category",
        tickmode="array",
        tickvals=categories,
        ticktext=[lot.name for lot in LOTS.values()],
    )
    figure.update_yaxes(range=[0, 10.7], tick0=0, dtick=2)
    plot(figure, "chart-lot-comparison")


def render_charts(records: list[dict], lot: int, averages: dict[int, tuple[float, int]]) -> None:
    first, second, third = st.columns(3, gap="small")
    with first, st.container(border=True, key="dg-card-technique"):
        donut("Borkészítési technológia", records, "technique", TECHNIQUES)
    with second, st.container(border=True, key="dg-card-balance"):
        donut("Egyensúly", records, "balance", BALANCES)
    with third, st.container(border=True, key="dg-card-branch"):
        if LOTS[lot].wine_type == "Fehérbor":
            donut("Illatosság · fehérborok", records, "fragrance", WHITE_VARIETIES)
        else:
            donut("Fajtacsoport · vörösborok", records, "variety_group", RED_VARIETIES)

    scores, comparison = st.columns(2, gap="small")
    with scores, st.container(border=True, key="dg-card-scores"):
        scores_chart(records)
    with comparison, st.container(border=True, key="dg-card-comparison"):
        comparison_chart(averages)

    aromas, grapes, regions = st.columns(3, gap="small")
    with aromas, st.container(border=True, key="dg-card-aromas"):
        ranking_chart("Aromacsoportok", aroma_counts(records), respondent_count=len(records))
    with grapes, st.container(border=True, key="dg-card-grapes"):
        ranking_chart("Szőlőfajták", answer_counts(records, "grape"))
    with regions, st.container(border=True, key="dg-card-regions"):
        ranking_chart("Borvidékek", answer_counts(records, "region"))
