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
    _method_desc = (
        "Log-space geometric mean k1 + suite correction k2 (NZS 1170.5 framework)"
        if scaling_method == "logspace" else
        "Linear MSE single factor k1 + suite correction k2 (ASCE 7-22 §16.2)"
    )
    lines.append(f"- **Scale factor derivation:** {_method_desc}")
    lines.append("")

    # ── 3. Scale Factor Results ───────────────────────────────────────────────
    lines.append("## 3. Scale Factor Results")
    sf_h_vals = [r.sf_h for r in scaling_results.values()]
    sf_h_ind_vals = [r.sf_h_k1 for r in scaling_results.values()]
    k2 = list(scaling_results.values())[0].sf_h_k2
    lines.append(f"- **Scaling method:** Step 1 — per-record log-space geometric mean (k1); Step 2 — suite correction (k2)")
    lines.append(f"- **Suite correction factor k2 (horizontal):** {k2:.4f}" +
                 (" (no correction required)" if k2 <= 1.001 else " (applied to all records)"))
    lines.append(f"- **Final SF range (horizontal):** {min(sf_h_vals):.4f} – {max(sf_h_vals):.4f}")
    lines.append(f"- **Suite mean SF (horizontal):** {np.mean(sf_h_vals):.4f}")

    if has_vertical:
        sf_v_vals = [r.sf_v for r in scaling_results.values() if r.sf_v is not None]
        if sf_v_vals:
            lines.append(f"- **Suite mean SF (vertical):** {np.mean(sf_v_vals):.4f}")
            lines.append(f"- **SF range (vertical):** {min(sf_v_vals):.4f} – {max(sf_v_vals):.4f}")

    lines.append("")
    lines.append("| Record ID | k1 (log-space fit) | k2 (suite correction) | SF final (H) | SF final (V) |")
    lines.append("|---|---|---|---|---|")
    for rid, r in scaling_results.items():
        sf_v_str = f"{r.sf_v:.4f}" if r.sf_v is not None else "N/A"
        lines.append(f"| {rid} | {r.sf_h_k1:.4f} | ×{r.sf_h_k2:.4f} | {r.sf_h:.4f} | {sf_v_str} |")
    lines.append("")

    # ── 4. Compliance Results ─────────────────────────────────────────────────
    lines.append("## 4. Compliance Results")
    for comp in compliance_results:
        lines.append(f"### {comp.code}")

        if not comp.alpha_h_is_default:
            lines.append(
                f"> ⚠️ **Custom horizontal tolerance applied:** α = {comp.alpha_h:.2f}. "
                f"Code default for {comp.code} is α = {_default_alpha(comp.code):.2f}. "
                "Engineer is responsible for confirming this is appropriate."
            )

        status_h = "✅ PASS" if comp.suite_pass_h else "❌ FAIL"
        lines.append(f"- **Horizontal suite compliance (α = {comp.alpha_h:.2f}):** {status_h}")
        if not comp.suite_pass_h:
            lines.append(
                f"  - Maximum deficiency: {comp.deficiency_h * 100:.1f}% below "
                f"α × target at T = {comp.worst_period_h:.3f} s"
            )

        if comp.suite_pass_v is not None:
            if not comp.alpha_v_is_default:
                lines.append(
                    f"> ⚠️ **Custom vertical tolerance applied:** α = {comp.alpha_v:.2f}."
                )
            status_v = "✅ PASS" if comp.suite_pass_v else "❌ FAIL"
            lines.append(f"- **Vertical suite compliance (α = {comp.alpha_v:.2f}):** {status_v}")
            if not comp.suite_pass_v:
                lines.append(
                    f"  - Maximum deficiency: {comp.deficiency_v * 100:.1f}% below "
                    f"α × target at T = {comp.worst_period_v:.3f} s"
                )

        if comp.min_records_warning:
            min_r = {"ASCE 7-22": 11, "EC8-1": 3}[comp.code]
            lines.append(
                f"> ⚠️ **Record count warning:** {comp.n_records} record sets provided. "
                f"{comp.code} recommends a minimum of {min_r}."
            )

        lines.append("")
        lines.append("**Per-record flags (informational — suite mean governs compliance):**")
        lines.append("")
        lines.append("| Record ID | H below α·target? | V below α·target? |")
        lines.append("|---|---|---|")
        for rr in comp.record_results:
            h_flag = "Yes" if rr.below_target_h else "No"
            v_flag = ("Yes" if rr.below_target_v else "No") if rr.below_target_v is not None else "N/A"
            lines.append(f"| {rr.record_id} | {h_flag} | {v_flag} |")
        lines.append("")

    return "\n".join(lines)


def _default_alpha(code: str) -> float:
    return {"ASCE 7-22": 0.90, "EC8-1": 0.90}.get(code, 0.90)
