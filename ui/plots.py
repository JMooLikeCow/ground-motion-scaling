"""
All five QA/QC Plotly charts.
"""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots


COLOURS = [
    "#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B2",
    "#937860", "#DA8BC3", "#8C8C8C", "#CCB974", "#64B5CD",
    "#1f77b4", "#ff7f0e",
]


def _period_axis_layout():
    return dict(
        type="log",
        title="Period (s)",
        showgrid=True,
        gridcolor="#e0e0e0",
        tickformat=".2g",
    )


def _sa_axis_layout():
    return dict(
        title="Sa (g)",
        showgrid=True,
        gridcolor="#e0e0e0",
    )


def plot_spectra_overlay(
    periods: np.ndarray,
    scaled_spectra: dict[str, np.ndarray],
    sa_target: np.ndarray,
    t_min: float,
    t_max: float,
    title: str = "Response Spectra — Scaled Suite vs Target",
) -> go.Figure:
    """Plot 1: Individual scaled spectra + mean + target."""
    fig = go.Figure()
    record_ids = list(scaled_spectra.keys())
    all_sa = np.vstack(list(scaled_spectra.values()))
    mean_sa = np.mean(all_sa, axis=0)

    for i, rid in enumerate(record_ids):
        fig.add_trace(go.Scatter(
            x=periods, y=scaled_spectra[rid],
            name=rid, line=dict(color=COLOURS[i % len(COLOURS)], width=1),
            opacity=0.45, legendgroup=rid, showlegend=True,
        ))

    fig.add_trace(go.Scatter(
        x=periods, y=mean_sa,
        name="Suite Mean", line=dict(color="black", width=2.5),
    ))
    fig.add_trace(go.Scatter(
        x=periods, y=sa_target,
        name="Target Spectrum", line=dict(color="red", width=2, dash="dash"),
    ))

    _add_period_range_band(fig, t_min, t_max)

    fig.update_layout(
        title=title, xaxis=_period_axis_layout(), yaxis=_sa_axis_layout(),
        legend=dict(font=dict(size=10)), hovermode="x unified",
        plot_bgcolor="white", paper_bgcolor="white",
    )
    return fig


def plot_mean_sigma(
    periods: np.ndarray,
    scaled_spectra: dict[str, np.ndarray],
    sa_target: np.ndarray,
    t_min: float,
    t_max: float,
    title: str = "Mean ± 1σ Envelope",
) -> go.Figure:
    """Plot 2: Mean ± one standard deviation band."""
    all_sa = np.vstack(list(scaled_spectra.values()))
    mean_sa = np.mean(all_sa, axis=0)
    std_sa = np.std(all_sa, axis=0, ddof=1) if all_sa.shape[0] > 1 else np.zeros_like(mean_sa)

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=np.concatenate([periods, periods[::-1]]),
        y=np.concatenate([mean_sa + std_sa, (mean_sa - std_sa)[::-1]]),
        fill="toself", fillcolor="rgba(76,114,176,0.15)",
        line=dict(color="rgba(255,255,255,0)"),
        name="Mean ± 1σ", showlegend=True,
    ))
    fig.add_trace(go.Scatter(
        x=periods, y=mean_sa,
        name="Suite Mean", line=dict(color="#4C72B0", width=2.5),
    ))
    fig.add_trace(go.Scatter(
        x=periods, y=sa_target,
        name="Target Spectrum", line=dict(color="red", width=2, dash="dash"),
    ))

    _add_period_range_band(fig, t_min, t_max)

    fig.update_layout(
        title=title, xaxis=_period_axis_layout(), yaxis=_sa_axis_layout(),
        hovermode="x unified", plot_bgcolor="white", paper_bgcolor="white",
    )
    return fig


def plot_scale_factors(
    sf_h: dict[str, float],
    sf_v: dict[str, float] | None = None,
    title: str = "Scale Factors by Record",
) -> go.Figure:
    """Plot 3: Scale factor bar chart per record."""
    record_ids = list(sf_h.keys())
    sf_h_vals = [sf_h[r] for r in record_ids]
    mean_sf_h = np.mean(sf_h_vals)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="SF (Horizontal)", x=record_ids, y=sf_h_vals,
        marker_color="#4C72B0", opacity=0.85,
    ))

    if sf_v:
        sf_v_vals = [sf_v.get(r, None) for r in record_ids]
        fig.add_trace(go.Bar(
            name="SF (Vertical)", x=record_ids, y=sf_v_vals,
            marker_color="#DD8452", opacity=0.85,
        ))

    fig.add_hline(
        y=mean_sf_h, line_dash="dash", line_color="black",
        annotation_text=f"Mean SF_H = {mean_sf_h:.3f}",
        annotation_position="top right",
    )

    fig.update_layout(
        title=title,
        xaxis_title="Record ID",
        yaxis_title="Scale Factor",
        barmode="group",
        plot_bgcolor="white", paper_bgcolor="white",
        xaxis=dict(tickangle=-30),
    )
    return fig


def plot_deviation_ratio(
    periods: np.ndarray,
    scaled_spectra: dict[str, np.ndarray],
    sa_target: np.ndarray,
    t_min: float,
    t_max: float,
    alpha_h: float,
    code: str,
    title: str = "Deviation Ratio — Mean / Target",
) -> go.Figure:
    """Plot 4: mean Sa / target Sa vs period, with threshold lines."""
    all_sa = np.vstack(list(scaled_spectra.values()))
    mean_sa = np.mean(all_sa, axis=0)

    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(sa_target > 0, mean_sa / sa_target, np.nan)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=periods, y=ratio,
        name="Mean / Target", line=dict(color="#4C72B0", width=2.5),
    ))
    fig.add_hline(y=1.0, line_dash="solid", line_color="red",
                  annotation_text="Target (1.0)", annotation_position="top left")
    if not np.isclose(alpha_h, 1.0):
        fig.add_hline(y=alpha_h, line_dash="dash", line_color="orange",
                      annotation_text=f"α = {alpha_h:.2f} ({code})",
                      annotation_position="bottom left")
    else:
        fig.add_hline(y=alpha_h, line_dash="dash", line_color="orange",
                      annotation_text=f"α = {alpha_h:.2f} ({code} default)",
                      annotation_position="bottom left")

    _add_period_range_band(fig, t_min, t_max)

    fig.update_layout(
        title=title,
        xaxis=_period_axis_layout(),
        yaxis=dict(title="Mean Sa / Target Sa", showgrid=True, gridcolor="#e0e0e0"),
        hovermode="x unified", plot_bgcolor="white", paper_bgcolor="white",
    )
    return fig


def plot_time_histories(
    records: dict,  # {record_id: {'H1': GroundMotionRecord, ...}}
    scaling_results: dict,  # {record_id: ScalingResult}
    selected_id: str,
) -> go.Figure:
    """Plot 5: Pre and post-scaling time histories for a selected record."""
    if selected_id not in records:
        return go.Figure()

    group = records[selected_id]
    result = scaling_results[selected_id]
    components = [k for k in ["H1", "H2", "V"] if k in group]

    fig = make_subplots(
        rows=len(components), cols=1,
        subplot_titles=[f"{selected_id} — {c}" for c in components],
        shared_xaxes=True,
    )

    comp_sf = {"H1": result.sf_h, "H2": result.sf_h, "V": result.sf_v}

    for row, comp in enumerate(components, 1):
        rec = group[comp]
        t = np.arange(rec.npts) * rec.dt
        sf = comp_sf[comp] or 1.0
        accel_unscaled = rec.acceleration
        accel_scaled = accel_unscaled * sf

        fig.add_trace(go.Scatter(
            x=t, y=accel_unscaled,
            name=f"{comp} unscaled", line=dict(color="#aaaaaa", width=0.8),
            legendgroup=f"{comp}_un", showlegend=(row == 1),
        ), row=row, col=1)
        fig.add_trace(go.Scatter(
            x=t, y=accel_scaled,
            name=f"{comp} scaled (SF={sf:.3f})",
            line=dict(color=COLOURS[row - 1], width=1.2),
            legendgroup=f"{comp}_sc", showlegend=True,
        ), row=row, col=1)

        pga_scaled = float(np.max(np.abs(accel_scaled)))
        fig.add_annotation(
            text=f"PGA = {pga_scaled:.4f} g",
            xref="x domain", yref="y domain",
            x=0.01, y=0.97, showarrow=False,
            row=row, col=1, font=dict(size=10),
        )

    fig.update_xaxes(title_text="Time (s)", row=len(components), col=1)
    fig.update_yaxes(title_text="Acceleration (g)")
    fig.update_layout(
        title=f"Time Histories — {selected_id}",
        height=280 * len(components),
        plot_bgcolor="white", paper_bgcolor="white",
        hovermode="x unified",
    )
    return fig


def _add_period_range_band(fig: go.Figure, t_min: float, t_max: float):
    """Add a light shaded vertical band marking the scaling period range."""
    fig.add_vrect(
        x0=t_min, x1=t_max,
        fillcolor="rgba(200,200,200,0.18)", line_width=0,
        annotation_text=f"[{t_min}–{t_max}s]",
        annotation_position="top left",
        annotation_font_size=10,
    )
