"""
Gold timeline chart component.
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import COLORS


def hex_to_rgba(hex_color: str, alpha: float = 1.0) -> str:
    """Convert hex color to rgba string."""
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def render_gold_timeline_chart(
    timeline_df: pd.DataFrame,
    title: str = "Gold Difference Timeline",
    height: int = 400,
    show_markers: bool = True,
):
    """
    Render a line chart showing gold difference over time.

    Args:
        timeline_df: DataFrame with 'minute' and 'gold_diff' columns
        title: Chart title
        height: Chart height in pixels
        show_markers: Whether to show data point markers
    """
    if timeline_df.empty:
        st.info("No timeline data available for this match.")
        return

    fig = go.Figure()

    # Add gold difference line
    fig.add_trace(go.Scatter(
        x=timeline_df["minute"],
        y=timeline_df["gold_diff"],
        mode="lines+markers" if show_markers else "lines",
        name="Gold Difference",
        line=dict(width=3),
        marker=dict(size=6),
        fill="tozeroy",
        fillcolor="rgba(52, 152, 219, 0.2)",
        hovertemplate="Minute %{x}<br>Gold Diff: %{y:,.0f}<extra></extra>",
    ))

    # Color the line based on which team is ahead
    colors = []
    for diff in timeline_df["gold_diff"]:
        if diff >= 0:
            colors.append(COLORS["blue_team"])
        else:
            colors.append(COLORS["red_team"])

    fig.update_traces(
        line_color=COLORS["blue_team"],  # Default color
    )

    # Add zero line
    fig.add_hline(
        y=0,
        line_dash="dash",
        line_color=COLORS["gold_accent"],
        line_width=2,
        annotation_text="Even",
        annotation_position="right",
    )

    # Add annotations for key moments
    max_diff = timeline_df["gold_diff"].max()
    min_diff = timeline_df["gold_diff"].min()

    if abs(max_diff) > 1000:
        max_row = timeline_df[timeline_df["gold_diff"] == max_diff].iloc[0]
        fig.add_annotation(
            x=max_row["minute"],
            y=max_diff,
            text=f"Blue peak: +{max_diff:,.0f}g",
            showarrow=True,
            arrowhead=2,
            arrowcolor=COLORS["blue_team"],
            font=dict(color=COLORS["blue_team"]),
        )

    if abs(min_diff) > 1000:
        min_row = timeline_df[timeline_df["gold_diff"] == min_diff].iloc[0]
        fig.add_annotation(
            x=min_row["minute"],
            y=min_diff,
            text=f"Red peak: {min_diff:,.0f}g",
            showarrow=True,
            arrowhead=2,
            arrowcolor=COLORS["red_team"],
            font=dict(color=COLORS["red_team"]),
        )

    fig.update_layout(
        title=dict(
            text=title,
            font=dict(color=COLORS["text_primary"], size=16),
        ),
        height=height,
        margin=dict(l=60, r=20, t=60, b=40),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor=COLORS["background_light"],
        font=dict(color=COLORS["text_primary"]),
        xaxis=dict(
            title="Game Time (minutes)",
            gridcolor="rgba(255,255,255,0.1)",
            tickfont=dict(color=COLORS["text_secondary"]),
        ),
        yaxis=dict(
            title="Gold Difference (Blue - Red)",
            gridcolor="rgba(255,255,255,0.1)",
            tickfont=dict(color=COLORS["text_secondary"]),
            tickformat=",d",
        ),
        hovermode="x unified",
        showlegend=False,
    )

    # Add colored regions
    fig.add_shape(
        type="rect",
        xref="paper",
        yref="y",
        x0=0,
        x1=1,
        y0=0,
        y1=timeline_df["gold_diff"].max() * 1.1 if timeline_df["gold_diff"].max() > 0 else 1000,
        fillcolor=hex_to_rgba(COLORS['blue_team'], 0.06),
        line=dict(width=0),
        layer="below",
    )

    fig.add_shape(
        type="rect",
        xref="paper",
        yref="y",
        x0=0,
        x1=1,
        y0=timeline_df["gold_diff"].min() * 1.1 if timeline_df["gold_diff"].min() < 0 else -1000,
        y1=0,
        fillcolor=hex_to_rgba(COLORS['red_team'], 0.06),
        line=dict(width=0),
        layer="below",
    )

    st.plotly_chart(fig, use_container_width=True)


def render_team_gold_comparison(
    timeline_df: pd.DataFrame,
    title: str = "Team Gold Over Time",
    height: int = 400,
):
    """
    Render a chart comparing both teams' total gold over time.

    Args:
        timeline_df: DataFrame with 'minute', 'team_100_gold', 'team_200_gold' columns
        title: Chart title
        height: Chart height in pixels
    """
    if timeline_df.empty or "team_100_gold" not in timeline_df.columns:
        st.info("No team gold data available.")
        return

    fig = go.Figure()

    # Blue team line
    fig.add_trace(go.Scatter(
        x=timeline_df["minute"],
        y=timeline_df["team_100_gold"],
        mode="lines",
        name="Blue Team",
        line=dict(color=COLORS["blue_team"], width=3),
        hovertemplate="Minute %{x}<br>Blue Gold: %{y:,.0f}<extra></extra>",
    ))

    # Red team line
    fig.add_trace(go.Scatter(
        x=timeline_df["minute"],
        y=timeline_df["team_200_gold"],
        mode="lines",
        name="Red Team",
        line=dict(color=COLORS["red_team"], width=3),
        hovertemplate="Minute %{x}<br>Red Gold: %{y:,.0f}<extra></extra>",
    ))

    fig.update_layout(
        title=dict(
            text=title,
            font=dict(color=COLORS["text_primary"], size=16),
        ),
        height=height,
        margin=dict(l=60, r=20, t=60, b=40),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor=COLORS["background_light"],
        font=dict(color=COLORS["text_primary"]),
        xaxis=dict(
            title="Game Time (minutes)",
            gridcolor="rgba(255,255,255,0.1)",
            tickfont=dict(color=COLORS["text_secondary"]),
        ),
        yaxis=dict(
            title="Total Gold",
            gridcolor="rgba(255,255,255,0.1)",
            tickfont=dict(color=COLORS["text_secondary"]),
            tickformat=",d",
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5,
        ),
        hovermode="x unified",
    )

    st.plotly_chart(fig, use_container_width=True)
