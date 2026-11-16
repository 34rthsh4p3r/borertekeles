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
