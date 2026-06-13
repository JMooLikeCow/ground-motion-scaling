"""
QA/QC Plotly charts for the ground motion scaling tool.

Plot sequence:
  1. Spectra overlay — full period range
  2. Spectra overlay — zoomed to [T_min, T_max], y-axis normalised
  3. Deviation ratio — full period range
  4. Deviation ratio — zoomed to [T_min, T_max], y-axis normalised
  5. Time histories — unscaled (grey) vs scaled (colour)
Scale factors shown as a table in the app, not as a chart.
"""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots


COLOURS = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    "#4C72B0", "#DD8452",
]


# ── Shared axis / layout helpers ──────────────────────────────────────────────

def _xaxis(title="Period (s)"):
    return dict(
        type="linear",
        title=dict(text=title, font=dict(color="black")),
        showgrid=True, gridcolor="#e0e0e0",
        tickfont=dict(color="black"), linecolor="black",
        zeroline=False,
    )


def _yaxis(title="Sa (g)"):
    return dict(
        title=dict(text=title, font=dict(color="black")),
        showgrid=True, gridcolor="#e0e0e0",
        tickfont=dict(color="black"), linecolor="black",
        zeroline=False,
    )


def _base():
    return dict(
        plot_bgcolor="white", paper_bgcolor="white",
        font=dict(color="black"),
        legend=dict(font=dict(color="black", size=10)),
        hovermode="x unified",
    )


def _range_band(fig, t_min, t_max, row=None, col=None):
    kwargs = dict(row=row, col=col) if row else {}
    fig.add_vrect(
        x0=t_min, x1=t_max,
        fillcolor="rgba(200,200,200,0.18)", line_width=0,
        annotation_text=f"[{t_min}–{t_max}s]",
        annotation_position="top left",
        annotation_font=dict(size=9, color="black"),
        **kwargs,
    )


# ── Plot 1: Full-range spectra overlay ────────────────────────────────────────

def plot_spectra_overlay(
    periods: np.ndarray,
    scaled_spectra: dict[str, np.ndarray],
    sa_target: np.ndarray,
    t_min: float,
    t_max: float,
    title: str = "Response Spectra — Scaled Suite vs Target (full range)",
) -> go.Figure:
    fig = go.Figure()
    all_sa = np.vstack(list(scaled_spectra.values()))
    mean_sa = np.mean(all_sa, axis=0)

    for i, (rid, sa) in enumerate(scaled_spectra.items()):
        fig.add_trace(go.Scatter(
            x=periods, y=sa, name=rid,
            line=dict(color=COLOURS[i % len(COLOURS)], width=1),
            opacity=0.45, legendgroup=rid,
        ))

    fig.add_trace(go.Scatter(
        x=periods, y=mean_sa, name="Suite Mean",
        line=dict(color="black", width=2.5),
    ))
    fig.add_trace(go.Scatter(
        x=periods, y=sa_target, name="Target Spectrum",
        line=dict(color="red", width=2, dash="dash"),
    ))
    _range_band(fig, t_min, t_max)

    fig.update_layout(
        title=dict(text=title, font=dict(color="black")),
        xaxis=_xaxis(), yaxis=_yaxis(),
        **_base(),
    )
    return fig


# ── Plot 2: Zoomed spectra overlay (period range of interest) ─────────────────

def plot_spectra_overlay_zoomed(
    periods: np.ndarray,
    scaled_spectra: dict[str, np.ndarray],
    sa_target: np.ndarray,
    t_min: float,
    t_max: float,
    title: str = "Response Spectra — Scaled Suite vs Target (period range of interest)",
) -> go.Figure:
    """Same as plot 1 but x-axis limited to [T_min, T_max] and y-axis auto-scaled."""
    mask = (periods >= t_min) & (periods <= t_max)
    p_zoom = periods[mask]

    fig = go.Figure()
    all_sa = np.vstack([sa[mask] for sa in scaled_spectra.values()])
    mean_sa = np.mean(all_sa, axis=0)
    target_zoom = sa_target[mask]

    for i, (rid, sa) in enumerate(scaled_spectra.items()):
        fig.add_trace(go.Scatter(
            x=p_zoom, y=sa[mask], name=rid,
            line=dict(color=COLOURS[i % len(COLOURS)], width=1.2),
            opacity=0.55, legendgroup=rid,
        ))

    fig.add_trace(go.Scatter(
        x=p_zoom, y=mean_sa, name="Suite Mean",
        line=dict(color="black", width=2.5),
    ))
    fig.add_trace(go.Scatter(
        x=p_zoom, y=target_zoom, name="Target Spectrum",
        line=dict(color="red", width=2, dash="dash"),
    ))

    # Y-axis bounds: 0 to 110% of max visible value
    all_vals = np.concatenate([all_sa.flatten(), target_zoom])
    y_max = float(np.max(all_vals)) * 1.10
    y_min = 0.0

    fig.update_layout(
        title=dict(text=title, font=dict(color="black")),
        xaxis={**_xaxis(), "range": [t_min, t_max]},
        yaxis={**_yaxis(), "range": [y_min, y_max]},
        **_base(),
    )
    return fig


# ── Plot 3: Deviation ratio — full range ──────────────────────────────────────

def plot_deviation_ratio(
    periods: np.ndarray,
    scaled_spectra: dict[str, np.ndarray],
    sa_target: np.ndarray,
    t_min: float,
    t_max: float,
    alpha_h: float,
    code: str,
    title: str = "Deviation Ratio — Mean / Target (full range)",
) -> go.Figure:
    all_sa = np.vstack(list(scaled_spectra.values()))
    mean_sa = np.mean(all_sa, axis=0)

    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(sa_target > 0, mean_sa / sa_target, np.nan)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=periods, y=ratio, name="Mean / Target",
        line=dict(color="#1f77b4", width=2.5),
    ))
    fig.add_hline(y=1.0, line_dash="solid", line_color="red",
                  annotation_text="1.0 (target)", annotation_position="top right",
                  annotation_font=dict(color="black"))
    if not np.isclose(alpha_h, 1.0):
        fig.add_hline(y=alpha_h, line_dash="dash", line_color="orange",
                      annotation_text=f"α = {alpha_h:.2f} ({code})",
                      annotation_position="bottom right",
                      annotation_font=dict(color="black"))
    _range_band(fig, t_min, t_max)

    fig.update_layout(
        title=dict(text=title, font=dict(color="black")),
        xaxis=_xaxis(),
        yaxis={**_yaxis("Mean Sa / Target Sa"), "range": [0, None]},
        **_base(),
    )
    return fig


# ── Plot 4: Deviation ratio — zoomed to period range of interest ──────────────

def plot_deviation_ratio_zoomed(
    periods: np.ndarray,
    scaled_spectra: dict[str, np.ndarray],
    sa_target: np.ndarray,
    t_min: float,
    t_max: float,
    alpha_h: float,
    code: str,
    title: str = "Deviation Ratio — Mean / Target (period range of interest)",
) -> go.Figure:
    mask = (periods >= t_min) & (periods <= t_max)
    p_zoom    = periods[mask]
    mean_sa   = np.mean(np.vstack(list(scaled_spectra.values())), axis=0)[mask]
    target_z  = sa_target[mask]

    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(target_z > 0, mean_sa / target_z, np.nan)

    # Y range: bracket the compliance threshold with some margin
    valid = ratio[np.isfinite(ratio)]
    y_min = max(0.0, float(np.min(valid)) * 0.90) if len(valid) else 0.0
    y_max = float(np.max(valid)) * 1.10 if len(valid) else 2.0
    # Ensure alpha and 1.0 are always visible
    y_min = min(y_min, alpha_h * 0.90)
    y_max = max(y_max, 1.05)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=p_zoom, y=ratio, name="Mean / Target",
        line=dict(color="#1f77b4", width=2.5),
    ))
    fig.add_hline(y=1.0, line_dash="solid", line_color="red",
                  annotation_text="1.0 (target)", annotation_position="top right",
                  annotation_font=dict(color="black"))
    if not np.isclose(alpha_h, 1.0):
        fig.add_hline(y=alpha_h, line_dash="dash", line_color="orange",
                      annotation_text=f"α = {alpha_h:.2f} ({code})",
                      annotation_position="bottom right",
                      annotation_font=dict(color="black"))

    fig.update_layout(
        title=dict(text=title, font=dict(color="black")),
        xaxis={**_xaxis(), "range": [t_min, t_max]},
        yaxis={**_yaxis("Mean Sa / Target Sa"), "range": [y_min, y_max]},
        **_base(),
    )
    return fig


# ── Plot 5: Time histories ─────────────────────────────────────────────────────

def plot_time_histories(
    records: dict,
    scaling_results: dict,
    selected_id: str,
) -> go.Figure:
    if selected_id not in records:
        return go.Figure()

    group  = records[selected_id]
    result = scaling_results[selected_id]
    components = [k for k in ["H1", "H2", "V"] if k in group]

    fig = make_subplots(
        rows=len(components), cols=1,
        subplot_titles=[f"{selected_id} — {c}" for c in components],
        shared_xaxes=True,
    )

    comp_sf = {"H1": result.sf_h, "H2": result.sf_h, "V": result.sf_v}

    for row, comp in enumerate(components, 1):
        rec    = group[comp]
        sf     = comp_sf[comp] or 1.0
        t      = np.arange(rec.npts) * rec.dt
        a_raw  = rec.acceleration
        a_sc   = a_raw * sf

        fig.add_trace(go.Scatter(
            x=t, y=a_raw,
            name=f"{comp} — unscaled",
            line=dict(color="#aaaaaa", width=0.8),
            legendgroup=f"{comp}_un",
        ), row=row, col=1)

        fig.add_trace(go.Scatter(
            x=t, y=a_sc,
            name=f"{comp} — scaled (SF={sf:.3f})",
            line=dict(color=COLOURS[row - 1], width=1.2),
            legendgroup=f"{comp}_sc",
        ), row=row, col=1)

        pga_raw = float(np.max(np.abs(a_raw)))
        pga_sc  = float(np.max(np.abs(a_sc)))
        fig.add_annotation(
            text=f"PGA unscaled = {pga_raw:.4f} g | PGA scaled = {pga_sc:.4f} g",
            xref="x domain", yref="y domain",
            x=0.01, y=0.97, showarrow=False,
            row=row, col=1,
            font=dict(size=9, color="black"),
        )

    fig.update_xaxes(
        title_text="Time (s)", title_font=dict(color="black"),
        tickfont=dict(color="black"), linecolor="black",
        showgrid=True, gridcolor="#e0e0e0",
        row=len(components), col=1,
    )
    fig.update_yaxes(
        title_text="Acceleration (g)", title_font=dict(color="black"),
        tickfont=dict(color="black"), linecolor="black",
        showgrid=True, gridcolor="#e0e0e0",
    )
    fig.update_layout(
        title=dict(
            text=f"Time Histories — {selected_id}   (grey = unscaled | colour = scaled)",
            font=dict(color="black"),
        ),
        height=280 * len(components),
        **_base(),
    )
    return fig
