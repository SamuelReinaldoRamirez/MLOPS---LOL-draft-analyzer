"""
Prediction gauge component for win probability visualization.
"""
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


def render_prediction_gauge(
    blue_win_prob: float,
    title: str = "Win Probability",
    height: int = 250,
):
    """
    Render a gauge chart showing win probability.

    Args:
        blue_win_prob: Probability of blue team winning (0 to 1)
        title: Chart title
        height: Chart height in pixels
    """
    red_win_prob = 1 - blue_win_prob

    # Create gauge
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=blue_win_prob * 100,
        number={"suffix": "%", "font": {"size": 40, "color": COLORS["text_primary"]}},
        title={"text": title, "font": {"size": 16, "color": COLORS["text_secondary"]}},
        gauge={
            "axis": {
                "range": [0, 100],
                "tickwidth": 1,
                "tickcolor": COLORS["text_secondary"],
                "tickfont": {"color": COLORS["text_secondary"]},
            },
            "bar": {"color": COLORS["blue_team"] if blue_win_prob >= 0.5 else COLORS["red_team"]},
            "bgcolor": COLORS["background_light"],
            "borderwidth": 2,
            "bordercolor": COLORS["gold_accent"],
            "steps": [
                {"range": [0, 50], "color": hex_to_rgba(COLORS['red_team'], 0.25)},
                {"range": [50, 100], "color": hex_to_rgba(COLORS['blue_team'], 0.25)},
            ],
            "threshold": {
                "line": {"color": COLORS["gold_accent"], "width": 4},
                "thickness": 0.75,
                "value": 50,
            },
        },
    ))

    fig.update_layout(
        height=height,
        margin=dict(l=20, r=20, t=50, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        font={"color": COLORS["text_primary"]},
    )

    st.plotly_chart(fig, use_container_width=True)

    # Display team labels
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            f"""
            <div style="text-align: center;">
                <span style="color: {COLORS['red_team']}; font-size: 1.2em; font-weight: bold;">
                    Red Team: {red_win_prob*100:.1f}%
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f"""
            <div style="text-align: center;">
                <span style="color: {COLORS['blue_team']}; font-size: 1.2em; font-weight: bold;">
                    Blue Team: {blue_win_prob*100:.1f}%
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_simple_probability_bar(
    blue_win_prob: float,
    show_labels: bool = True,
):
    """
    Render a simple horizontal bar showing win probability.

    Args:
        blue_win_prob: Probability of blue team winning (0 to 1)
        show_labels: Whether to show team labels
    """
    red_win_prob = 1 - blue_win_prob

    # Create horizontal bar
    fig = go.Figure()

    # Red team portion (left)
    fig.add_trace(go.Bar(
        y=["Win Probability"],
        x=[red_win_prob * 100],
        orientation="h",
        name="Red Team",
        marker_color=COLORS["red_team"],
        text=f"{red_win_prob*100:.1f}%",
        textposition="inside",
        textfont={"color": "white", "size": 14},
        hoverinfo="name+x",
    ))

    # Blue team portion (right)
    fig.add_trace(go.Bar(
        y=["Win Probability"],
        x=[blue_win_prob * 100],
        orientation="h",
        name="Blue Team",
        marker_color=COLORS["blue_team"],
        text=f"{blue_win_prob*100:.1f}%",
        textposition="inside",
        textfont={"color": "white", "size": 14},
        hoverinfo="name+x",
    ))

    fig.update_layout(
        barmode="stack",
        height=80,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        xaxis={"visible": False, "range": [0, 100]},
        yaxis={"visible": False},
    )

    st.plotly_chart(fig, use_container_width=True)

    if show_labels:
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(
                f"<p style='color: {COLORS['red_team']}; text-align: left; margin: 0;'>Red Team</p>",
                unsafe_allow_html=True,
            )
        with col2:
            st.markdown(
                f"<p style='color: {COLORS['blue_team']}; text-align: right; margin: 0;'>Blue Team</p>",
                unsafe_allow_html=True,
            )
