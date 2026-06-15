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
        **kwargs,
    )
    # Vertical dashed boundary lines labelled T_min / T_max
    for t_val, label, pos in [
        (t_min, "T_min", "top right"),
        (t_max, "T_max", "top left"),
    ]:
        fig.add_vline(
            x=t_val,
            line_dash="dash", line_color="rgba(80,80,80,0.55)", line_width=1.2,
            annotation_text=label,
            annotation_position=pos,
            annotation_font=dict(size=8, color="black"),
            **kwargs,
        )


def _ec8_check_annotation(fig, checks):
    """Stamp the EC8-2 Annex D.3(8a) band + average check results onto the figure."""
    if not checks:
        return
    bl, bu = checks["band_lower"], checks["band_upper"]
    bp, ap = checks["band_pass"], checks["avg_pass"]
    avg, amin = checks["avg_ratio"], checks["avg_min"]
    mark = lambda p: "✓" if p else "✗"
    verdict = lambda p: "MET" if p else "NOT MET"
    text = (
        "<b>EC8-2 Annex D.3(8a) compliance</b><br>"
        f"{mark(bp)} {bl:.2f} &lt; mean/target ≤ {bu:.2f} : <b>{verdict(bp)}</b><br>"
        f"{mark(ap)} average mean/target &gt; {amin:.2f} (avg = {avg:.3f}) : <b>{verdict(ap)}</b>"
    )
    all_pass = bool(bp) and bool(ap)
    fig.add_annotation(
        xref="paper", yref="paper", x=0.02, y=0.98,
        xanchor="left", yanchor="top", align="left", showarrow=False,
        text=text, font=dict(size=11, color="black"),
        bordercolor=("#2ca02c" if all_pass else "#d62728"), borderwidth=1.2,
        bgcolor=("rgba(220,245,220,0.92)" if all_pass else "rgba(250,224,224,0.92)"),
    )


# ── Plot 1: Full-range spectra overlay ────────────────────────────────────────

def plot_spectra_overlay(
    periods: np.ndarray,
    scaled_spectra: dict[str, np.ndarray],
    sa_target: np.ndarray,
    t_min: float,
    t_max: float,
    alpha_h: float = 0.90,
    floor_frac: float | None = None,
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
        line=dict(color="red", width=2),
        opacity=0.70,
    ))
    fig.add_trace(go.Scatter(
        x=periods, y=alpha_h * sa_target, name=f"α × Target (α={alpha_h:.2f})",
        line=dict(color="red", width=1.5, dash="dash"),
        opacity=0.70,
    ))
    if floor_frac is not None:
        fig.add_trace(go.Scatter(
            x=periods, y=floor_frac * sa_target,
            name=f"{floor_frac*100:.0f}% Target floor (EC8-2)",
            line=dict(color="red", width=1, dash="dot"),
            opacity=0.60,
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
    alpha_h: float = 0.90,
    floor_frac: float | None = None,
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
        line=dict(color="red", width=2),
        opacity=0.70,
    ))
    fig.add_trace(go.Scatter(
        x=p_zoom, y=alpha_h * target_zoom, name=f"α × Target (α={alpha_h:.2f})",
        line=dict(color="red", width=1.5, dash="dash"),
        opacity=0.70,
    ))
    if floor_frac is not None:
        fig.add_trace(go.Scatter(
            x=p_zoom, y=floor_frac * target_zoom,
            name=f"{floor_frac*100:.0f}% Target floor (EC8-2)",
            line=dict(color="red", width=1, dash="dot"),
            opacity=0.60,
        ))

    # Y-axis bounds: 0 to 110% of max visible value (include α×target in range)
    all_vals = np.concatenate([all_sa.flatten(), target_zoom, alpha_h * target_zoom])
    y_max = float(np.max(all_vals)) * 1.10
    y_min = 0.0

    x_pad = (t_max - t_min) * 0.05
    fig.update_layout(
        title=dict(text=title, font=dict(color="black")),
        xaxis={**_xaxis(), "range": [t_min - x_pad, t_max + x_pad]},
        yaxis={**_yaxis(), "range": [y_min, y_max]},
        **_base(),
    )
    _range_band(fig, t_min, t_max)
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
    band: tuple[float, float] | None = None,
    ec8_checks: dict | None = None,
    title: str = "Deviation Ratio — Mean / Target (full range)",
) -> go.Figure:
    all_sa = np.vstack(list(scaled_spectra.values()))
    mean_sa = np.mean(all_sa, axis=0)

    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(sa_target > 0, mean_sa / sa_target, np.nan)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=periods, y=ratio, name="Mean Sa / Target Sa",
        line=dict(color="#1f77b4", width=2.5),
    ))
    fig.add_trace(go.Scatter(
        x=periods, y=np.ones_like(periods), name="Target (ratio = 1.0)",
        line=dict(color="red", width=1.5, dash="solid"),
    ))
    if band is not None:
        # EC8-2 D.3(8a) band edges
        for edge, lbl in [(band[0], "lower"), (band[1], "upper")]:
            fig.add_trace(go.Scatter(
                x=periods, y=np.full_like(periods, edge),
                name=f"Band {lbl} ({edge:.2f}) — EC8-2",
                line=dict(color="red", width=1.5, dash="dash"),
                opacity=0.70,
            ))
        fig.add_trace(go.Scatter(
            x=periods, y=np.full_like(periods, alpha_h),
            name=f"Average min ({alpha_h:.2f}) — EC8-2",
            line=dict(color="orange", width=1.2, dash="dashdot"),
            opacity=0.70,
        ))
    else:
        fig.add_trace(go.Scatter(
            x=periods, y=np.full_like(periods, alpha_h), name=f"α × Target (α = {alpha_h:.2f})",
            line=dict(color="red", width=1.5, dash="dash"),
        ))
    _range_band(fig, t_min, t_max)
    _ec8_check_annotation(fig, ec8_checks)

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
    band: tuple[float, float] | None = None,
    ec8_checks: dict | None = None,
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
    if band is not None:
        y_min = min(y_min, band[0] * 0.90)
        y_max = max(y_max, band[1] * 1.05)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=p_zoom, y=ratio, name="Mean Sa / Target Sa",
        line=dict(color="#1f77b4", width=2.5),
    ))
    fig.add_trace(go.Scatter(
        x=p_zoom, y=np.ones_like(p_zoom), name="Target (ratio = 1.0)",
        line=dict(color="red", width=1.5, dash="solid"),
        opacity=0.70,
    ))
    if band is not None:
        for edge, lbl in [(band[0], "lower"), (band[1], "upper")]:
            fig.add_trace(go.Scatter(
                x=p_zoom, y=np.full_like(p_zoom, edge),
                name=f"Band {lbl} ({edge:.2f}) — EC8-2",
                line=dict(color="red", width=1.5, dash="dash"),
                opacity=0.70,
            ))
        fig.add_trace(go.Scatter(
            x=p_zoom, y=np.full_like(p_zoom, alpha_h),
            name=f"Average min ({alpha_h:.2f}) — EC8-2",
            line=dict(color="orange", width=1.2, dash="dashdot"),
            opacity=0.70,
        ))
    else:
        fig.add_trace(go.Scatter(
            x=p_zoom, y=np.full_like(p_zoom, alpha_h), name=f"α × Target (α = {alpha_h:.2f})",
            line=dict(color="red", width=1.5, dash="dash"),
            opacity=0.70,
        ))

    x_pad = (t_max - t_min) * 0.05
    fig.update_layout(
        title=dict(text=title, font=dict(color="black")),
        xaxis={**_xaxis(), "range": [t_min - x_pad, t_max + x_pad]},
        yaxis={**_yaxis("Mean Sa / Target Sa"), "range": [y_min, y_max]},
        **_base(),
    )
    _range_band(fig, t_min, t_max)
    _ec8_check_annotation(fig, ec8_checks)
    return fig

