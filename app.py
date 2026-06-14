"""
Ground Motion Scaling Tool
Streamlit web application — entry point.
"""
from __future__ import annotations

import io
import numpy as np
import pandas as pd
import streamlit as st

from core.at2_parser import parse_at2, group_records, GroundMotionRecord
from core.response_spectrum import compute_response_spectrum, PERIOD_ARRAY
from core.scaling import scale_suite, SuiteScalingMetadata
from core.compliance import check_compliance, ALPHA_DEFAULTS
from ui.plots import (
    plot_spectra_overlay,
    plot_spectra_overlay_zoomed,
    plot_deviation_ratio,
    plot_deviation_ratio_zoomed,
)
from ui.report import build_report
from io_excel.excel_output import build_excel
from io_excel.excel_input import parse_excel_template, create_input_template

st.set_page_config(
    page_title="Ground Motion Scaling Tool",
    page_icon="📈",
    layout="wide",
)

# ── Styling ────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .block-container { padding-top: 1.5rem; }
    .stAlert { border-radius: 6px; }
    h1 { color: #2E5E9B; }
    h2 { color: #2E5E9B; border-bottom: 1px solid #e0e0e0; padding-bottom: 4px; }
    .pass-badge { background:#92D050; color:white; padding:3px 10px; border-radius:4px; font-weight:bold; }
    .fail-badge { background:#FF0000; color:white; padding:3px 10px; border-radius:4px; font-weight:bold; }
</style>
""", unsafe_allow_html=True)

st.title("Ground Motion Scaling Tool")
st.caption("Amplitude scaling for nonlinear response history analysis | ASCE 7-22 & EC8-1")

# ── Input Mode Selection ───────────────────────────────────────────────────────
st.markdown("---")
input_mode = st.radio(
    "**Input Mode**",
    ["Mode B — Direct browser input (drag & drop)", "Mode A — Upload Excel input template"],
    horizontal=True,
)

# ── Helper: parse pasted spectrum table ───────────────────────────────────────

def parse_pasted_spectrum(text: str, label: str) -> tuple[np.ndarray, np.ndarray] | None:
    """Parse a pasted Period, Sa table (tab or comma separated)."""
    if not text.strip():
        return None
    rows = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.replace(",", "\t").split()
        if len(parts) < 2:
            st.error(f"{label}: each row must have Period and Sa values.")
            return None
        try:
            rows.append((float(parts[0]), float(parts[1])))
        except ValueError:
            continue  # skip header rows
    if len(rows) < 2:
        st.error(f"{label}: at least 2 data points required.")
        return None
    arr = np.array(rows)
    return arr[:, 0], arr[:, 1]


# ── Shared state containers ────────────────────────────────────────────────────
params = {}
target_h = None
target_v = None
at2_uploads = []
records_manifest = None  # only used in Mode A

# ══════════════════════════════════════════════════════════════════════════════
# MODE A — Excel template
# ══════════════════════════════════════════════════════════════════════════════
if "Excel" in input_mode:
    col_dl, col_up = st.columns([1, 2])
    with col_dl:
        st.markdown("**Step 1 — Download & fill the input template**")
        template_bytes = create_input_template()
        st.download_button(
            "⬇️ Download input template (.xlsx)",
            data=template_bytes,
            file_name="gm_scaling_input_template.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    with col_up:
        st.markdown("**Step 2 — Upload completed template**")
        template_file = st.file_uploader("Upload filled template", type=["xlsx"], key="template_upload")

    if template_file:
        try:
            excel_inputs = parse_excel_template(template_file.read())
            params = {
                "t_min": excel_inputs.t_min,
                "t_max": excel_inputs.t_max,
                "t_min_v": excel_inputs.t_min_v,
                "t_max_v": excel_inputs.t_max_v,
                "damping": excel_inputs.damping,
                "code": excel_inputs.code,
                "combination_method": excel_inputs.combination_method,
                "scaling_method": "mse",
                "alpha_h": excel_inputs.alpha_h,
                "alpha_v": excel_inputs.alpha_v,
            }
            target_h = excel_inputs.sa_target_h
            target_v = excel_inputs.sa_target_v
            records_manifest = excel_inputs.records_manifest
            st.success(f"Template parsed — {len(records_manifest)} records in manifest.")
        except Exception as e:
            st.error(f"Template parse error: {e}")

    st.markdown("**Step 3 — Upload AT2 files** (batch, all files in suite)")
    at2_uploads = st.file_uploader(
        "Upload AT2 files",
        type=["AT2", "at2"],
        accept_multiple_files=True,
        key="at2_mode_a",
        help="Upload all H1, H2, and V AT2 files. Filenames must match those listed in the RECORDS sheet.",
    )

# ══════════════════════════════════════════════════════════════════════════════
# MODE B — Direct browser input
# ══════════════════════════════════════════════════════════════════════════════
else:
    st.markdown("### 1. Upload Ground Motion Pairs")
    st.caption(
        "Upload H1 and H2 files for each record pair. "
        "V (vertical) is optional. Each row is one ground motion pair. "
        "PEER AT2 format, units assumed g."
    )

    n_pairs = st.number_input(
        "Number of ground motion pairs", min_value=1, max_value=30, value=3, step=1,
    )

    # Column headers
    hdr = st.columns([1.2, 2, 2, 2])
    hdr[0].markdown("**Record ID**")
    hdr[1].markdown("**H1 component**")
    hdr[2].markdown("**H2 component**")
    hdr[3].markdown("**V component** *(optional)*")

    pair_uploads = []
    for i in range(int(n_pairs)):
        c0, c1, c2, c3 = st.columns([1.2, 2, 2, 2])
        with c0:
            rid = st.text_input(
                "ID", value=f"GM{i+1:02d}", key=f"rid_{i}",
                label_visibility="collapsed",
            )
        with c1:
            h1 = st.file_uploader(
                f"H1_{i}", type=["AT2", "at2"], key=f"h1_{i}",
                label_visibility="collapsed",
            )
        with c2:
            h2 = st.file_uploader(
                f"H2_{i}", type=["AT2", "at2"], key=f"h2_{i}",
                label_visibility="collapsed",
            )
        with c3:
            v = st.file_uploader(
                f"V_{i}", type=["AT2", "at2"], key=f"v_{i}",
                label_visibility="collapsed",
            )
        pair_uploads.append({"id": rid.strip(), "H1": h1, "H2": h2, "V": v})

    st.markdown("### 2. Target Spectra")
    col_th, col_tv = st.columns(2)
    with col_th:
        st.markdown("**Horizontal target spectrum** (required)")
        st.caption("Paste Period (s) and Sa (g) — tab or comma separated, one pair per line.")
        pasted_h = st.text_area(
            "Horizontal target", height=160, key="target_h_paste",
            placeholder="0.01\t0.45\n0.10\t0.85\n0.20\t1.20\n...",
            label_visibility="collapsed",
        )
        if pasted_h:
            result = parse_pasted_spectrum(pasted_h, "Horizontal target")
            if result:
                target_h = result

    with col_tv:
        st.markdown("**Vertical target spectrum** (optional)")
        st.caption("Leave blank if no vertical records.")
        pasted_v = st.text_area(
            "Vertical target", height=160, key="target_v_paste",
            placeholder="0.01\t0.30\n0.10\t0.55\n...",
            label_visibility="collapsed",
        )
        if pasted_v:
            result = parse_pasted_spectrum(pasted_v, "Vertical target")
            if result:
                target_v = result

    st.markdown("### 3. Scaling Parameters")
    col1, col2, col3 = st.columns(3)

    with col1:
        t_min = st.number_input("T_min — horizontal (s)", value=0.20, min_value=0.01, step=0.05, format="%.2f")
        t_max = st.number_input("T_max — horizontal (s)", value=3.00, min_value=0.05, step=0.10, format="%.2f")
        damping_pct = st.number_input("Damping ratio (%)", value=5.0, min_value=0.1, max_value=30.0, step=0.5, format="%.1f")

    with col2:
        t_min_v = st.number_input("T_min — vertical (s)", value=0.10, min_value=0.01, step=0.05, format="%.2f",
                                   help="Only used if vertical records are uploaded.")
        t_max_v = st.number_input("T_max — vertical (s)", value=1.50, min_value=0.05, step=0.10, format="%.2f")
        code_options = ["ASCE 7-22", "EC8-1", "Both"]
        code = st.selectbox("Compliance code", code_options)

    with col3:
        scaling_method = st.selectbox(
            "SF derivation method",
            ["mse", "logspace"],
            format_func=lambda x: (
                "Linear MSE — single factor (ASCE 7-22 §16.2)"
                if x == "mse" else
                "Log-space geometric mean (NZS 1170.5)"
            ),
        )
        with st.expander("ℹ️ Which SF derivation method?"):
            st.markdown("""
**Linear MSE — single factor (ASCE 7-22 §16.2)**

`SF = Σ(Sa_pair × Sa_target) / Σ(Sa_pair²)`

Minimises the sum of squared residuals between the scaled combined spectrum and the target in linear space. Produces a single scalar applied identically to both H1 and H2 of each pair, consistent with the ASCE 7-22 §16.2 requirement that a single scale factor is applied to both horizontal components. High-Sa periods carry more weight than low-Sa periods in this minimisation.

---

**Log-space geometric mean (NZS 1170.5)**

`SF = exp( mean[ log(Sa_target / Sa_pair) ] )`

Gives equal percentage-error weight at all periods — no bias toward high-Sa regions. Aligned with the NZS 1170.5 k1/k2 framework. Also applies one scalar to both H1 and H2 (the scalar is derived from the combined H1+H2 spectrum). Not explicitly prescribed by ASCE 7-22 but produces more balanced spectral fits.

---

**Practical guidance:** Use **Linear MSE** when strict ASCE 7-22 §16.2 compliance is required. Use **Log-space** when you want equal period weighting or are following NZS 1170.5.
            """)
        combination_method = st.selectbox(
            "Horizontal combination rule",
            ["srss", "geomean"],
            format_func=lambda x: "Geometric Mean (RotD50 proxy)" if x == "geomean" else "SRSS (ASCE 7-22 §16.2.3)",
        )
        with st.expander("ℹ️ Which combination rule?"):
            st.markdown("""
**Geometric Mean (RotD50 proxy)** computes the combined spectrum as:

`Sa_pair(T) = √( Sa_H1(T) × Sa_H2(T) )`

This is the geometric mean of the two as-recorded horizontal components. It is not identical to RotD50 (which requires computing the response spectrum across all rotation azimuths and taking the 50th percentile), but it is the standard engineering proxy and tracks closely with RotD50 on average. The PEER NGA database reports RotD50, and most ASCE 7 site-specific and USGS hazard spectra are defined on a RotD50 basis — **Geometric Mean is the appropriate choice** when your target is RotD50.

---

**SRSS (Square Root of Sum of Squares)** computes:

`Sa_pair(T) = √( Sa_H1(T)² + Sa_H2(T)² )`

This represents the maximum resultant response across both components simultaneously. It is referenced in **ASCE 7-22 §16.2.3** as the combination rule for checking suite compliance. It produces values approximately 1.41× (√2) larger than the geometric mean at any given period, which means it will result in smaller scale factors for the same target. Some engineers apply SRSS when the target spectrum has already been developed on an SRSS or RotD100 basis. Using SRSS against a RotD50 target is overly conservative.

---

**Practical guidance:**
- Target spectrum from USGS, ASCE 7, or PEER CMS → use **Geometric Mean**
- Target spectrum explicitly defined on an SRSS or RotD100 basis → use **SRSS**
- When in doubt, use **Geometric Mean** — it is the more common practice basis
            """)


    st.markdown("#### Spectral Tolerance (α)")
    st.caption(
        "The suite mean spectrum must be ≥ α × target over the scaling range. "
        "Code defaults for amplitude scaling: ASCE 7-22 → α = 0.90 | EC8-1 → α = 0.90. "
        "Override only if project-specific criteria apply."
    )
    col_a1, col_a2 = st.columns(2)
    with col_a1:
        use_custom_ah = st.checkbox("Override horizontal α", value=False)
        alpha_h_input = st.number_input(
            "Horizontal α", value=0.90, min_value=0.50, max_value=1.50, step=0.01, format="%.2f",
            disabled=not use_custom_ah,
        )
    with col_a2:
        use_custom_av = st.checkbox("Override vertical α", value=False)
        alpha_v_input = st.number_input(
            "Vertical α", value=0.90, min_value=0.50, max_value=1.50, step=0.01, format="%.2f",
            disabled=not use_custom_av,
        )

    params = {
        "t_min": t_min,
        "t_max": t_max,
        "t_min_v": t_min_v,
        "t_max_v": t_max_v,
        "damping": damping_pct / 100.0,
        "code": code,
        "combination_method": combination_method,
        "scaling_method": scaling_method,
        "alpha_h": alpha_h_input if use_custom_ah else None,
        "alpha_v": alpha_v_input if use_custom_av else None,
    }

# ══════════════════════════════════════════════════════════════════════════════
# RUN BUTTON
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("---")
run_col, _ = st.columns([1, 4])
with run_col:
    run = st.button("▶ Run Scaling", type="primary", use_container_width=True)

if not run:
    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
# PROCESSING
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("## Results")

if target_h is None:
    st.error("No horizontal target spectrum provided.")
    st.stop()

if params.get("t_min", 0) >= params.get("t_max", 0):
    st.error("T_min must be less than T_max.")
    st.stop()

# ── Parse AT2 files ───────────────────────────────────────────────────────────
with st.spinner("Parsing AT2 files..."):
    parse_errors = []
    grouped: dict[str, dict[str, GroundMotionRecord]] = {}

    if "Excel" in input_mode:
        # Mode A: batch upload + manifest mapping
        if not at2_uploads:
            st.error("No AT2 files uploaded.")
            st.stop()
        raw_records: list[GroundMotionRecord] = []
        for uf in at2_uploads:
            try:
                raw_records.append(parse_at2(uf.read(), uf.name))
            except Exception as e:
                parse_errors.append(f"{uf.name}: {e}")
        if records_manifest:
            filename_to_rec = {r.filename: r for r in raw_records}
            for entry in records_manifest:
                rid = entry["id"]
                grouped[rid] = {}
                for comp in ["H1", "H2", "V"]:
                    fname = entry.get(comp)
                    if fname and fname in filename_to_rec:
                        grouped[rid][comp] = filename_to_rec[fname]
        else:
            grouped = group_records(raw_records)
    else:
        # Mode B: per-pair explicit upload
        active_pairs = [p for p in pair_uploads if p["id"] and p["H1"] is not None]
        if not active_pairs:
            st.error("No ground motion pairs uploaded. Please upload at least one H1 file.")
            st.stop()
        for pair in active_pairs:
            rid = pair["id"]
            grouped[rid] = {}
            for comp in ["H1", "H2", "V"]:
                f = pair[comp]
                if f is not None:
                    try:
                        grouped[rid][comp] = parse_at2(f.read(), f.name)
                    except Exception as e:
                        parse_errors.append(f"{rid}/{comp} ({f.name}): {e}")

    for err in parse_errors:
        st.warning(err)

    if not grouped:
        st.error("No records could be parsed. Check file format.")
        st.stop()

n_records = len(grouped)
has_vertical = any("V" in g for g in grouped.values())

st.info(
    f"Parsed **{n_records}** record set(s). "
    f"Components: {'H1 + H2' + (' + V' if has_vertical else '')}. "
    "Assumed units: **g**. Please verify."
)

# ── Interpolate target spectra onto internal period array ─────────────────────
with st.spinner("Computing response spectra..."):
    t_pts_h, sa_pts_h = target_h
    sa_target_h_interp = np.interp(PERIOD_ARRAY, t_pts_h, sa_pts_h)

    sa_target_v_interp = None
    if target_v is not None:
        t_pts_v, sa_pts_v = target_v
        sa_target_v_interp = np.interp(PERIOD_ARRAY, t_pts_v, sa_pts_v)

    # Compute spectra for each component
    spectra_h1: dict[str, np.ndarray] = {}
    spectra_h2: dict[str, np.ndarray] = {}
    spectra_v: dict[str, np.ndarray] = {}

    progress_bar = st.progress(0)
    total = sum(len(g) for g in grouped.values())
    done = 0

    for rid, group in grouped.items():
        for comp, rec in group.items():
            sa = compute_response_spectrum(rec.acceleration, rec.dt, params["damping"], PERIOD_ARRAY)
            if comp == "H1":
                spectra_h1[rid] = sa
            elif comp == "H2":
                spectra_h2[rid] = sa
            elif comp == "V":
                spectra_v[rid] = sa
            done += 1
            progress_bar.progress(done / total)

    progress_bar.empty()

# ── Scale ─────────────────────────────────────────────────────────────────────
with st.spinner("Computing scale factors..."):
    t_min_v_val = params["t_min_v"] if has_vertical and sa_target_v_interp is not None else None
    t_max_v_val = params["t_max_v"] if has_vertical and sa_target_v_interp is not None else None

    # Resolve alpha values: use user override if provided, else use code default
    codes_to_check = ["ASCE 7-22", "EC8-1"] if params["code"] == "Both" else [params["code"]]
    # For scaling, use the first selected code's alpha as the suite correction target
    primary_code = codes_to_check[0]
    alpha_h_scaling = params["alpha_h"] if params["alpha_h"] is not None else ALPHA_DEFAULTS[primary_code]
    alpha_v_scaling = params["alpha_v"] if params["alpha_v"] is not None else ALPHA_DEFAULTS[primary_code]

    try:
        scaling_results, scaling_metadata = scale_suite(
            spectra_h1=spectra_h1,
            spectra_h2=spectra_h2 if spectra_h2 else None,
            spectra_v=spectra_v if spectra_v else None,
            sa_target_h=sa_target_h_interp,
            sa_target_v=sa_target_v_interp,
            periods=PERIOD_ARRAY,
            t_min=params["t_min"],
            t_max=params["t_max"],
            t_min_v=t_min_v_val,
            t_max_v=t_max_v_val,
            combination_method=params["combination_method"],
            scaling_method=params.get("scaling_method", "mse"),
            alpha_h=alpha_h_scaling,
            alpha_v=alpha_v_scaling,
        )
    except Exception as e:
        st.error(f"Scaling error: {e}")
        st.stop()

    # Show suite correction notice if it was applied
    method_label = ("Log-space geometric mean" if scaling_metadata.scaling_method == "logspace"
                    else "Linear MSE")
    if scaling_metadata.suite_correction_h > 1.001:
        st.info(
            f"ℹ️ Suite correction applied (k2 = **{scaling_metadata.suite_correction_h:.4f}**): "
            f"{method_label} per-record factors (k1) were multiplied by k2 to bring the suite mean "
            f"up to α × target (α = {alpha_h_scaling:.2f}) across the full scaling period range."
        )

# ── Compliance ────────────────────────────────────────────────────────────────
compliance_results = []

scaled_combined = {rid: r.sa_combined_scaled for rid, r in scaling_results.items()}
scaled_v_dict = {rid: r.sf_v * r.sa_v_unscaled
                 for rid, r in scaling_results.items()
                 if r.sf_v is not None and r.sa_v_unscaled is not None}

for code_name in codes_to_check:
    alpha_h = params["alpha_h"] if params["alpha_h"] is not None else None
    alpha_v = params["alpha_v"] if params["alpha_v"] is not None else None

    comp_result = check_compliance(
        scaled_combined=scaled_combined,
        scaled_v=scaled_v_dict if scaled_v_dict else None,
        sa_target_h=sa_target_h_interp,
        sa_target_v=sa_target_v_interp,
        periods=PERIOD_ARRAY,
        t_min=params["t_min"],
        t_max=params["t_max"],
        t_min_v=t_min_v_val,
        t_max_v=t_max_v_val,
        code=code_name,
        alpha_h=alpha_h,
        alpha_v=alpha_v,
    )
    compliance_results.append(comp_result)

# ══════════════════════════════════════════════════════════════════════════════
# DISPLAY RESULTS
# ══════════════════════════════════════════════════════════════════════════════

# ── Compliance warnings ───────────────────────────────────────────────────────
for comp in compliance_results:
    if not comp.alpha_h_is_default:
        st.warning(
            f"⚠️ Custom horizontal tolerance applied (α = {comp.alpha_h:.2f}) for {comp.code}. "
            f"Code default for amplitude scaling is α = {ALPHA_DEFAULTS[comp.code]:.2f}. "
            "Engineer is responsible for confirming suitability."
        )
    if comp.suite_pass_v is not None and not comp.alpha_v_is_default:
        st.warning(
            f"⚠️ Custom vertical tolerance applied (α = {comp.alpha_v:.2f}) for {comp.code}. "
            f"Code default is α = {ALPHA_DEFAULTS[comp.code]:.2f}."
        )
    if comp.min_records_warning:
        min_r = {"ASCE 7-22": 11, "EC8-1": 3}[comp.code]
        st.warning(f"⚠️ {n_records} record sets uploaded. {comp.code} recommends ≥ {min_r} records.")

# ── Suite compliance status ───────────────────────────────────────────────────
st.markdown("### Compliance Summary")
_sf_method_label = (
    "Linear MSE single factor (ASCE 7-22 §16.2)"
    if scaling_metadata.scaling_method == "mse"
    else "Log-space geometric mean (NZS 1170.5)"
)
_sf_method_caption = (
    "k1 (shape fit) applied independently per record; k2 (suite correction) applied uniformly — "
    "both H1 and H2 of each pair share the same k1×k2 scalar."
    if scaling_metadata.scaling_method == "logspace"
    else "Single scalar applied to both H1 and H2 of each pair."
)
st.caption(f"SF derivation method: **{_sf_method_label}** — {_sf_method_caption}")
for comp in compliance_results:
    h_colour = "green" if comp.suite_pass_h else "red"
    h_status = "PASS" if comp.suite_pass_h else f"FAIL (max deficiency {comp.deficiency_h*100:.1f}% below α×target at T = {comp.worst_period_h:.3f} s)"
    st.markdown(f"**{comp.code} horizontal suite (α = {comp.alpha_h:.2f}):** :{h_colour}[{h_status}]")
    if comp.suite_pass_v is not None:
        v_colour = "green" if comp.suite_pass_v else "red"
        v_status = "PASS" if comp.suite_pass_v else f"FAIL (max deficiency {comp.deficiency_v*100:.1f}% below α×target at T = {comp.worst_period_v:.3f} s)"
        st.markdown(f"**{comp.code} vertical suite (α = {comp.alpha_v:.2f}):** :{v_colour}[{v_status}]")

# ── Scale factors table ───────────────────────────────────────────────────────
st.markdown("### Scale Factors")
st.caption(
    "Scale factors are dimensionless amplitude multipliers applied to the g-valued time series. "
    "Per-record flags below indicate whether an individual record falls below the target — "
    "these are informational only; suite mean compliance governs."
)
sf_table = []
_use_logspace = scaling_metadata.scaling_method == "logspace"

# ── TEMPORARY DEBUG — remove after confirming ─────────────────────────────────
st.info(
    f"DEBUG → scaling_metadata.scaling_method = `{scaling_metadata.scaling_method!r}` | "
    f"_use_logspace = `{_use_logspace}` | "
    f"sample sa_h2_unscaled is None: `{next(iter(scaling_results.values())).sa_h2_unscaled is None}`"
)
# ─────────────────────────────────────────────────────────────────────────────

def _pga(arr):
    return f"{float(np.max(np.abs(arr))):.4f}" if arr is not None else "—"

if _use_logspace:
    # One row per component (H1, H2, and optionally V) per record pair.
    # k1/k2 are the same for H1 and H2 within a pair (derived from combined spectrum).
    for rid, r in scaling_results.items():
        for comp_label, arr in [("H1", r.sa_h1_unscaled), ("H2", r.sa_h2_unscaled)]:
            if arr is None:
                continue
            sf_table.append({
                "Component": f"{rid} — {comp_label}",
                "k1 (shape fit)":    f"{r.sf_h_k1:.4f}",
                "k2 (suite corr.)":  f"×{r.sf_h_k2:.4f}",
                "SF = k1×k2":        f"{r.sf_h:.4f}",
                "Unscaled PGA (g)":  _pga(arr),
                "Scaled PGA (g)":    f"{r.sf_h * float(np.max(np.abs(arr))):.4f}",
            })
        if r.sf_v is not None and r.sa_v_unscaled is not None:
            sf_table.append({
                "Component": f"{rid} — V",
                "k1 (shape fit)":    f"{r.sf_v_k1:.4f}" if r.sf_v_k1 is not None else "—",
                "k2 (suite corr.)":  f"×{r.sf_v_k2:.4f}" if r.sf_v_k2 is not None else "—",
                "SF = k1×k2":        f"{r.sf_v:.4f}",
                "Unscaled PGA (g)":  _pga(r.sa_v_unscaled),
                "Scaled PGA (g)":    f"{r.sf_v * float(np.max(np.abs(r.sa_v_unscaled))):.4f}",
            })
else:
    # One row per ground motion pair. Single SF applied to both H1 and H2.
    for rid, r in scaling_results.items():
        sf_table.append({
            "Record ID":       rid,
            "Scale Factor (H)": f"{r.sf_h:.4f}",
            "Scale Factor (V)": f"{r.sf_v:.4f}" if r.sf_v else "—",
            "Unscaled PGA (g)": _pga(r.sa_h1_unscaled),
            "Scaled PGA (g)":   f"{r.sf_h * float(np.max(np.abs(r.sa_h1_unscaled))):.4f}" if r.sa_h1_unscaled is not None else "—",
        })

st.dataframe(pd.DataFrame(sf_table), use_container_width=True, hide_index=True)

# ── Spectral ratio table ──────────────────────────────────────────────────────
st.markdown("### Spectral Ratio Table — Sa(scaled) / Sa(target)")
st.caption(
    f"Individual and mean ratios at each period within the scaling range "
    f"[{params['t_min']} – {params['t_max']} s]. "
    f"Cells below the compliance threshold (α = {alpha_h_scaling:.2f}) are highlighted."
)

_mask_sr = (PERIOD_ARRAY >= params["t_min"]) & (PERIOD_ARRAY <= params["t_max"])
_periods_sr = PERIOD_ARRAY[_mask_sr]
_target_sr = sa_target_h_interp[_mask_sr]

def _fmt_ratios(sa_arr, target):
    ratios = np.where(target > 0, sa_arr / target, np.nan)
    return [f"{v:.3f}" if np.isfinite(v) else "—" for v in ratios]

_ratio_data: dict[str, list] = {"Period (s)": [f"{t:.3f}" for t in _periods_sr]}

if _use_logspace:
    # Collect all individual component spectra (H1 and H2 scaled separately)
    _comp_spectra: dict[str, np.ndarray] = {}
    for rid, r in scaling_results.items():
        if r.sa_h1_unscaled is not None:
            _comp_spectra[f"{rid} — H1"] = r.sf_h * r.sa_h1_unscaled[_mask_sr]
        if r.sa_h2_unscaled is not None:
            _comp_spectra[f"{rid} — H2"] = r.sf_h * r.sa_h2_unscaled[_mask_sr]
    _all_comp = np.vstack(list(_comp_spectra.values()))
    _mean_sr = np.mean(_all_comp, axis=0)
    _ratio_data["Suite Mean"] = _fmt_ratios(_mean_sr, _target_sr)
    for col_id, sa in _comp_spectra.items():
        _ratio_data[col_id] = _fmt_ratios(sa, _target_sr)
else:
    # One column per pair (combined spectrum)
    _all_scaled_sr = np.vstack([r.sa_combined_scaled[_mask_sr] for r in scaling_results.values()])
    _mean_sr = np.mean(_all_scaled_sr, axis=0)
    _ratio_data["Suite Mean"] = _fmt_ratios(_mean_sr, _target_sr)
    for rid, r in scaling_results.items():
        _ratio_data[rid] = _fmt_ratios(r.sa_combined_scaled[_mask_sr], _target_sr)

_ratio_df = pd.DataFrame(_ratio_data)

def _colour_suite_mean(val):
    try:
        v = float(str(val))
        if v < alpha_h_scaling:
            return "background-color: #FFCCCC; color: black"
        elif v < 1.0:
            return "background-color: #FFF3CC; color: black"
    except (TypeError, ValueError):
        pass
    return ""

try:
    _styled = _ratio_df.style.map(_colour_suite_mean, subset=["Suite Mean"])
except AttributeError:
    _styled = _ratio_df.style.applymap(_colour_suite_mean, subset=["Suite Mean"])
st.dataframe(_styled, use_container_width=True, hide_index=True)

# ── QA/QC Plots ───────────────────────────────────────────────────────────────
st.markdown("### QA/QC Plots")
alpha_plot = compliance_results[0].alpha_h
code_plot  = compliance_results[0].code

st.plotly_chart(plot_spectra_overlay(
    PERIOD_ARRAY, scaled_combined, sa_target_h_interp,
    params["t_min"], params["t_max"], alpha_plot,
), use_container_width=True)

st.plotly_chart(plot_spectra_overlay_zoomed(
    PERIOD_ARRAY, scaled_combined, sa_target_h_interp,
    params["t_min"], params["t_max"], alpha_plot,
), use_container_width=True)

st.plotly_chart(plot_deviation_ratio(
    PERIOD_ARRAY, scaled_combined, sa_target_h_interp,
    params["t_min"], params["t_max"], alpha_plot, code_plot,
), use_container_width=True)

st.plotly_chart(plot_deviation_ratio_zoomed(
    PERIOD_ARRAY, scaled_combined, sa_target_h_interp,
    params["t_min"], params["t_max"], alpha_plot, code_plot,
), use_container_width=True)

# ── Design Note ───────────────────────────────────────────────────────────────
st.markdown("### Design Note")
report_md = build_report(
    scaling_results=scaling_results,
    compliance_results=compliance_results,
    t_min=params["t_min"],
    t_max=params["t_max"],
    t_min_v=t_min_v_val,
    t_max_v=t_max_v_val,
    damping=params["damping"],
    combination_method=params["combination_method"],
    scaling_method=params.get("scaling_method", "mse"),
    has_vertical=has_vertical,
)
st.markdown(report_md)

# ── Excel download ─────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("### Download Results")
with st.spinner("Generating Excel output..."):
    try:
        excel_bytes = build_excel(
            scaling_results=scaling_results,
            compliance_results=compliance_results,
            report_md=report_md,
            periods=PERIOD_ARRAY,
            at2_records=grouped,
            sa_target_h=sa_target_h_interp,
            t_min=params["t_min"],
            t_max=params["t_max"],
        )
        st.download_button(
            "⬇️ Download results.xlsx",
            data=excel_bytes,
            file_name="gm_scaling_results.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as e:
        st.warning(f"Excel generation encountered an issue: {e}. Results are still available above.")
