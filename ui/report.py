"""
Generate the bullet-point design note as a Markdown string.
Same content is written to the Excel REPORT sheet.
"""
from __future__ import annotations

import numpy as np
from core.compliance import SuiteCompliance
from core.scaling import ScalingResult


def build_report(
    scaling_results: dict[str, ScalingResult],
    compliance_results: list[SuiteCompliance],
    t_min: float,
    t_max: float,
    t_min_v: float | None,
    t_max_v: float | None,
    damping: float,
    combination_method: str,
    scaling_method: str,
    has_vertical: bool,
) -> str:
    """Return the full design note as a Markdown string."""

    lines = []

    # ── 1. Input Summary ──────────────────────────────────────────────────────
    lines.append("## 1. Input Summary")
    n_rec = len(scaling_results)
    lines.append(f"- **Number of record sets processed:** {n_rec}")
    comp_label = "H1, H2, and V (vertical)" if has_vertical else "H1 and H2 (horizontal pair)"
    lines.append(f"- **Components present:** {comp_label}")
    lines.append("- **Input file format:** PEER AT2 (assumed units: g)")

    _cm_label = "Geometric Mean (RotD50 proxy)" if combination_method == "geomean" else "SRSS (ASCE 7-22 §16.2.3)"
    lines.append(f"- **Horizontal combination method:** {_cm_label}")
    lines.append("")

    # ── 2. Scaling Parameters ─────────────────────────────────────────────────
    lines.append("## 2. Scaling Parameters")
    lines.append("- **Scaling method:** Amplitude scaling (single scalar scale factor per record)")
    lines.append(f"- **Viscous damping ratio:** {damping * 100:.1f}%")
    lines.append(f"- **Horizontal scaling period range:** T_min = {t_min} s, T_max = {t_max} s")
    if has_vertical and t_min_v is not None:
        lines.append(f"- **Vertical scaling period range:** T_min = {t_min_v} s, T_max = {t_max_v} s")
    if scaling_method == "logspace":
        _method_desc = "Log-space geometric mean (k1) per record + suite correction (k2) — NZS 1170.5 framework"
    else:
        _method_desc = "Linear MSE — single scale factor per pair (ASCE 7-22 §16.2)"
    lines.append(f"- **Scale factor derivation:** {_method_desc}")
    lines.append("")

    # ── 3. Scale Factor Results ───────────────────────────────────────────────
    lines.append("## 3. Scale Factor Results")
    sf_h_vals = [r.sf_h for r in scaling_results.values()]

    if scaling_method == "logspace":
        k1_vals = [r.sf_h_k1 for r in scaling_results.values()]
        k2 = list(scaling_results.values())[0].sf_h_k2
        lines.append(f"- **Scaling method:** Step 1 — per-record log-space geometric mean (k1); Step 2 — suite correction (k2)")
        lines.append(f"- **Suite correction factor k2 (horizontal):** {k2:.4f}" +
                     (" (no correction required)" if k2 <= 1.001 else " (applied to all records)"))
    else:
        k2 = list(scaling_results.values())[0].sf_h_k2
        lines.append(f"- **Scaling method:** Linear MSE single factor per pair; suite correction applied if required")
        lines.append(f"- **Suite correction (horizontal):** {k2:.4f}" +
                     (" (no correction required)" if k2 <= 1.001 else " (applied to all records)"))

    lines.append(f"- **SF range (horizontal):** {min(sf_h_vals):.4f} – {max(sf_h_vals):.4f}")
    lines.append(f"- **Suite mean SF (horizontal):** {np.mean(sf_h_vals):.4f}")

    if has_vertical:
        sf_v_vals = [r.sf_v for r in scaling_results.values() if r.sf_v is not None]
        if sf_v_vals:
            lines.append(f"- **Suite mean SF (vertical):** {np.mean(sf_v_vals):.4f}")
            lines.append(f"- **SF range (vertical):** {min(sf_v_vals):.4f} – {max(sf_v_vals):.4f}")

    lines.append("")
    if scaling_method == "logspace":
        lines.append("| Record ID | k1 — H | k2 — H | SF (H) = k1×k2 | k1 — V | k2 — V | SF (V) = k1×k2 |")
        lines.append("|---|---|---|---|---|---|---|")
        for rid, r in scaling_results.items():
            k1v = f"{r.sf_v_k1:.4f}" if r.sf_v_k1 is not None else "N/A"
            k2v = f"×{r.sf_v_k2:.4f}" if r.sf_v_k2 is not None else "N/A"
            sfv = f"{r.sf_v:.4f}" if r.sf_v is not None else "N/A"
            lines.append(f"| {rid} | {r.sf_h_k1:.4f} | ×{r.sf_h_k2:.4f} | {r.sf_h:.4f} | {k1v} | {k2v} | {sfv} |")
    else:
        lines.append("| Record ID | Scale Factor (H) | Scale Factor (V) |")
        lines.append("|---|---|---|")
        for rid, r in scaling_results.items():
            sf_v_str = f"{r.sf_v:.4f}" if r.sf_v is not None else "N/A"
            lines.append(f"| {rid} | {r.sf_h:.4f} | {sf_v_str} |")
    lines.append("")

    return "\n".join(lines)


def _default_alpha(code: str) -> float:
    return {"ASCE 7-22": 0.90, "EC8-1": 0.90}.get(code, 0.90)
