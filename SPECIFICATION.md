# Ground Motion Scaling Tool — Technical Specification

**Version**: 0.1 (Pre-build review draft)  
**Date**: 2026-06-13  
**Purpose**: Specification for review prior to development. Covers all functional, technical, and interface requirements.

---

## 1. Project Overview

A web-based ground motion scaling tool for use in seismic engineering, supporting nonlinear response history analysis (NRHA) in accordance with ASCE 7-22 and Eurocode 8 Part 1 (EN 1998-1). The tool accepts raw ground motion records in PEER AT2 format, applies amplitude scaling against a user-supplied target spectrum, checks code compliance, produces interactive graphical QA/QC outputs, and generates both an on-screen summary and a downloadable Excel output file.

---

## 2. Platform & Deployment

| Item | Decision |
|---|---|
| Framework | Python — Streamlit web application |
| Access | Browser-based (Chrome, Edge, Firefox) — no local installation required beyond Python |
| Hosting | Streamlit Community Cloud (free tier) or firm-hosted server |
| Local run | `streamlit run app.py` at `localhost:8501` if self-hosted |
| Dependencies | Python 3.10+, streamlit, numpy, scipy, pandas, plotly, openpyxl, xlsxwriter |

---

## 3. Input Modes

The tool supports two mutually exclusive input modes, selectable at the top of the interface.

### 3.1 Mode A — Excel Input Template

The user downloads a pre-formatted Excel template from the tool, fills it in, and uploads it as a single file. AT2 ground motion files are uploaded separately as a batch (zip or multi-file drag-and-drop).

**Template structure:**

| Sheet | Contents |
|---|---|
| `PARAMETERS` | T_min, T_max (horizontal); T_min_V, T_max_V (vertical, optional); damping ratio (%); code selection; horizontal SF method (geomean / SRSS) |
| `TARGET_SPECTRUM_H` | Two columns: Period (s), Sa (g) — horizontal target |
| `TARGET_SPECTRUM_V` | Two columns: Period (s), Sa (g) — vertical target (optional) |
| `RECORDS` | Columns: Record ID, H1 filename, H2 filename, V filename (optional) |

### 3.2 Mode B — Direct Browser Input

All inputs entered directly in the Streamlit interface:

- Drag-and-drop AT2 files (batch, multi-file)
- Paste target spectrum table directly into a text input box (tab or comma-separated: Period, Sa)
- Parameter fields: T_min, T_max, T_min_V, T_max_V, damping ratio, code, SF method
- Separate paste box for vertical target spectrum (appears only if vertical files are detected or user enables it)

---

## 4. Ground Motion Input Format

### 4.1 File Format

PEER NGA AT2 native format. Standard AT2 structure:

```
Line 1: Description / event name (free text)
Line 2: Description (free text)
Line 3: Description including NPTS and DT keywords
Line 4: NPTS= XXXX, DT= X.XXXX SEC
Lines 5+: Acceleration values (g), space-separated, 5 values per row
```

The parser extracts: number of points (NPTS), time step (DT), and the full acceleration time series in units of g.

### 4.2 Component Convention

Records are grouped into sets. Each set may contain:
- **H1** — horizontal component 1 (required)
- **H2** — horizontal component 2 (required for pair-based scaling)
- **V** — vertical component (optional)

Filename convention for automatic pairing (Mode B):
- `RSN123_H1.AT2` / `RSN123_H2.AT2` / `RSN123_V.AT2`
- Common prefix before `_H1`, `_H2`, `_V` suffix used for matching

In Mode A, pairing is defined explicitly in the `RECORDS` sheet.

### 4.3 Units

All AT2 files are assumed to be in units of **g** (gravitational acceleration), consistent with PEER NGA convention. The tool will display a clear warning label confirming assumed units and prompt the user to verify.

### 4.4 Batch Input

Multiple record sets (minimum 7 recommended per ASCE 7-22 §16.2.2) may be uploaded simultaneously. The tool processes all sets in a single run.

---

## 5. Target Spectrum Input

- User-supplied only — the tool does **not** compute code spectra internally
- Horizontal and vertical target spectra are provided as separate two-column tables: Period (s) and Sa (g)
- Accepted via paste (Mode B) or Excel template sheet (Mode A)
- The tool interpolates the target spectrum onto its internal period array using log-linear interpolation in the period domain
- The target spectrum is plotted immediately upon input for visual confirmation before scaling is run

---

## 6. Scaling Parameters

| Parameter | Description | Default |
|---|---|---|
| T_min | Lower bound of scaling period range — horizontal (s) | User input |
| T_max | Upper bound of scaling period range — horizontal (s) | User input |
| T_min_V | Lower bound — vertical (s) | User input |
| T_max_V | Upper bound — vertical (s) | User input |
| Damping ratio | Viscous damping for response spectrum computation (%) | 5% |
| Code | Compliance standard to apply | User selects |
| SF method | Horizontal pair combination method | User selects |
| Spectral tolerance (horizontal) | Allowable ratio by which the suite mean may fall below the target (see Section 6.1) | Code-dependent default |
| Spectral tolerance (vertical) | Same as above, applied to vertical suite compliance | Code-dependent default |

**Note on period range**: The period range is defined directly by the user (T_min, T_max). The tool does not auto-compute code-derived ranges (e.g. 0.2T₁ to 1.5T₁) because the applicable range varies by standard and project type (new buildings per ASCE 7, existing buildings per ASCE 41, etc.). The engineer is responsible for inputting the appropriate range.

### 6.1 Spectral Tolerance Parameter

The spectral tolerance defines the minimum permissible ratio of the suite mean spectrum to the target spectrum at any period within the scaling range. It controls how closely the scaled suite must track the target and directly drives the pass/fail compliance check.

**Expression:**
```
mean( SF_i × Sa_pair_i(T) ) ≥ α × Sa_target(T)   for all T ∈ [T_min, T_max]
```

where **α** is the spectral tolerance ratio (dimensionless, 0 < α ≤ 1.0).

**Code-default values:**

| Standard | Default α | Basis |
|---|---|---|
| ASCE 7-22 | 1.00 | §16.2.3: mean shall not fall below target |
| EC8-1 | 0.90 | §3.2.3.1.2: mean shall not fall below 90% of target |

**User override:**
The user may enter a custom α value in the parameter inputs. This allows:
- **Stricter than code** (α > code default, e.g. α = 1.05): for projects where the engineer wishes to ensure the mean exceeds the target by a margin
- **Relaxed from code** (α < code default): for cases where an alternative compliance basis is being applied (e.g. site-specific approval, project-specific criteria)

When a custom α is entered that differs from the code default, the tool displays a prominent warning:

> ⚠️ Custom spectral tolerance (α = X.XX) applied. This deviates from the [ASCE 7-22 / EC8-1] code default of α = X.XX. The engineer is responsible for ensuring this is appropriate for the project.

The tolerance α applies independently to horizontal and vertical compliance checks. Separate α values may be set for each.

---

## 7. Response Spectrum Computation

- Method: Newmark-β integration (average acceleration method: β = 0.25, γ = 0.5)
- Period array: 100 logarithmically-spaced points from 0.01 s to 10.0 s (fixed, not user-configurable)
- Computed for each individual component (H1, H2, V separately)
- Combined horizontal spectrum computed per the user-selected method (see Section 8)
- Damping ratio applied uniformly across all periods

---

## 8. Amplitude Scaling

### 8.1 Horizontal Scale Factor

The horizontal pair combined spectrum is computed as:

**Option A — Geometric Mean (geomean):**
```
Sa_pair(T) = sqrt( Sa_H1(T) × Sa_H2(T) )
```

**Option B — SRSS:**
```
Sa_pair(T) = sqrt( Sa_H1(T)² + Sa_H2(T)² )
```

The user selects which method applies. ASCE 7-22 §16.2.3 references the SRSS combination; geometric mean is an approximation widely used in practice. Both H1 and H2 receive the **same scalar scale factor** — they are never scaled independently.

### 8.2 Scale Factor Computation

A single scalar scale factor SF is found for each record set by minimising the mean squared error (MSE) between the scaled combined spectrum and the target spectrum over the period range [T_min, T_max]:

```
SF = argmin { Σ [ SF × Sa_pair(Tᵢ) - Sa_target(Tᵢ) ]² }
         over all Tᵢ ∈ [T_min, T_max]
```

Closed-form solution:
```
SF = Σ [ Sa_pair(Tᵢ) × Sa_target(Tᵢ) ] / Σ [ Sa_pair(Tᵢ)² ]
```

### 8.3 Vertical Scale Factor

The vertical component is scaled **independently** from the horizontal pair. A separate scale factor SF_V is computed by the same MSE minimisation method, using:
- The vertical component spectrum Sa_V(T)
- The vertical target spectrum
- The vertical period range [T_min_V, T_max_V]

There is no requirement that SF_V matches SF_H. Vertical scaling is only performed if vertical AT2 files are provided.

---

## 9. Code Compliance Checks

The user selects one or both standards. Compliance checks are applied after scaling.

### 9.1 ASCE 7-22 §16.2.3

**Suite-level check (horizontal):**
```
mean( SF_i × Sa_pair_i(T) ) ≥ α_H × Sa_target(T)   for all T ∈ [T_min, T_max]
```
Default α_H = 1.00 (mean shall not fall below target). User-overridable per Section 6.1.

**Per-record flag:**
Each record is flagged based on whether its individual scaled spectrum falls below the target. Per ASCE 7-22, the binding requirement is the suite mean — individual records may fall below the target. The per-record flag is informational, not a hard pass/fail criterion under the code, but is displayed for engineering judgement.

**Suite pass/fail:**
PASS if the mean spectrum meets or exceeds α_H × target at all periods in the scaling range. FAIL otherwise, with the period of maximum deficiency and the deficiency magnitude (as a percentage below α × target) reported.

**Minimum records:**
A warning is issued if fewer than 11 record sets are provided (ASCE 7-22 §16.2.2 requires a minimum of 11 when using the mean response for design).

### 9.2 Eurocode 8 Part 1 — EN 1998-1 §3.2.3.1

**Suite-level check:**
```
mean( SF_i × Sa_pair_i(T) ) ≥ α_H × Sa_target(T)   for all T ∈ [T_min, T_max]
```
Default α_H = 0.90 (mean shall not fall below 90% of target). User-overridable per Section 6.1.

Note: The period range [0.2T₁, 2T₁] is a code default. Since the tool accepts user-defined T_min/T_max, the user is responsible for setting these in accordance with EC8-1 for the structure under consideration.

**Per-record flag:** Same approach as ASCE 7-22 — informational.

**Minimum records:** Warning issued if fewer than 3 records provided (EC8-1 minimum for mean response use).

### 9.3 Compliance Output

For each standard selected, the tool outputs:

| Output | Description |
|---|---|
| Suite PASS / FAIL | Overall suite compliance against α × target |
| α applied | Tolerance value used (code default or user override, clearly labelled) |
| Deficiency magnitude | If FAIL: maximum percentage by which mean falls below α × target |
| Worst period | Period at which maximum deficiency occurs |
| Per-record flag | Whether each individual record falls below target (informational) |
| Tolerance warning | Displayed when user α deviates from the code default |

---

## 10. QA/QC Graphical Outputs

Five interactive plots produced using Plotly, rendered in the Streamlit interface. All plots are also exported as static images embedded in the output Excel file.

### Plot 1 — Response Spectra Overlay
- Individual scaled spectra of all records (semi-transparent lines, coloured by record)
- Mean spectrum of suite (bold solid line)
- Target spectrum (dashed red line)
- Vertical dashed lines at T_min and T_max
- Period range [T_min, T_max] shaded
- Legend toggleable per record

### Plot 2 — Mean ± 1σ Band
- Mean spectrum (bold)
- Shaded band: mean ± one standard deviation
- Target spectrum overlaid
- Scaling range shaded

### Plot 3 — Scale Factor Bar Chart
- One bar per record set, labelled with record ID
- Horizontal reference line at suite mean SF
- Separate bars for SF_H and SF_V if vertical is included
- Colour coding: no pass/fail on SF chart (SF alone is not a compliance indicator)

### Plot 4 — Deviation Ratio Plot
- Y-axis: mean Sa (scaled) / Sa target at each period
- Horizontal reference lines at 1.0 (target) and 0.9 (EC8-1 threshold)
- Scaling range [T_min, T_max] shaded
- Clearly shows where suite mean exceeds or falls short of target

### Plot 5 — Time History Plots
- Acceleration vs time for each record component
- Pre-scaling (grey) and post-scaling (coloured) overlaid on same axis
- Record selector dropdown — one record displayed at a time
- Separate panels for H1, H2, and V (if present)
- PGA annotated on plot

---

## 11. Design Note / Report Output

A structured bullet-point summary rendered as formatted Markdown in the Streamlit interface. The same content is written to the `REPORT` sheet of the output Excel file.

**Sections:**

1. **Project Input Summary**
   - Number of record sets uploaded
   - Components present (H1/H2 only, or H1/H2/V)
   - File format confirmed (PEER AT2)
   - Assumed units (g)
   - PGA range of unscaled records (min, max, mean)
   - Record duration range (min, max)

2. **Target Spectrum Summary**
   - Horizontal: peak Sa, period of peak, number of data points provided
   - Vertical: same (if applicable)

3. **Scaling Parameters**
   - Scaling method: amplitude scaling
   - Horizontal combination method: geomean / SRSS
   - Period range (horizontal): T_min to T_max
   - Period range (vertical): T_min_V to T_max_V (if applicable)
   - Damping ratio
   - Compliance standard(s) selected

4. **Scale Factor Results**
   - Table: Record ID | SF_H | SF_V | Scaled PGA H (g) | Scaled PGA V (g)
   - Suite mean SF_H, suite mean SF_V
   - Min and max SF_H across suite

5. **Compliance Results**
   - Per standard selected:
     - Suite result: PASS or FAIL
     - If FAIL: deficiency magnitude and period location
     - Per-record compliance flag (informational)

6. **Key Spectral Statistics**
   - Mean Sa at T_min, T_max
   - Period of peak mean Sa
   - Mean / target ratio at T_min, T_max, and worst period

---

## 12. Output Modes

### 12.1 Streamlit Screen Output

Displayed on the same page as inputs after "Run Scaling" is clicked:
- Compliance summary table
- All 5 interactive Plotly charts
- Design note (formatted Markdown)
- Download buttons

### 12.2 Excel Output File

Auto-generated on every run. Always available for download via a button in the Streamlit interface. Structure:

| Sheet | Contents |
|---|---|
| `SUMMARY` | Scale factors, compliance results, key statistics |
| `REPORT` | Bullet-point design note (same as screen output) |
| `PLOT_SPECTRA` | Spectra overlay chart (static image) |
| `PLOT_SIGMA` | Mean ± 1σ chart |
| `PLOT_SF` | Scale factor bar chart |
| `PLOT_DEV` | Deviation ratio chart |
| `PLOT_TH` | Time history plots (one per record) |
| `RECORDS_LOG` | Record provenance: filename, NPTS, DT, duration, unscaled PGA |

---

## 13. Project File Structure

```
ground-motion-scaling/
│
├── app.py                        # Streamlit entry point and page layout
│
├── core/
│   ├── at2_parser.py             # Parse PEER AT2 files → (dt, accel array in g)
│   ├── response_spectrum.py      # Newmark-β integration → Sa(T) array
│   ├── scaling.py                # MSE minimisation → scale factors
│   └── compliance.py             # ASCE 7-22 and EC8-1 pass/fail logic
│
├── ui/
│   ├── upload.py                 # File upload widgets and format guidance
│   ├── target_spectrum.py        # Target spectrum input and preview
│   ├── parameters.py             # Parameter input fields
│   ├── plots.py                  # All 5 Plotly chart functions
│   └── report.py                 # Bullet-point summary renderer
│
├── io/
│   ├── excel_input.py            # Parse Excel input template (Mode A)
│   └── excel_output.py           # Generate output Excel workbook
│
├── templates/
│   └── input_template.xlsx       # Pre-formatted Excel input template (Mode A)
│
└── requirements.txt
```

---

## 14. Open Items / Assumptions Pending Confirmation

| # | Item | Current Assumption |
|---|---|---|
| 1 | Horizontal pair SF method | Both geomean and SRSS available — user selects |
| 2 | Vertical component | Optional; independent SF; separate vertical target spectrum required |
| 3 | Per-record pass/fail definition | Informational flag only; suite mean is the binding compliance criterion |
| 4 | ASCE 7-22 minimum record count | Warning at <11 records; tool does not block execution |
| 5 | EC8-1 minimum record count | Warning at <3 records |
| 6 | Period array | Fixed: 100 log-spaced points, 0.01–10.0 s |
| 7 | AT2 units | Assumed g; user-confirmed via UI warning |
| 8 | Response spectrum method | Newmark-β (average acceleration) |
| 9 | Spectral tolerance α (ASCE 7-22) | Default 1.00; user-overridable with warning |
| 10 | Spectral tolerance α (EC8-1) | Default 0.90; user-overridable with warning |
| 11 | Separate α for vertical compliance | Yes — horizontal and vertical tolerances set independently |

---

*End of specification. Version 0.1 — subject to revision following QA/QC review.*
