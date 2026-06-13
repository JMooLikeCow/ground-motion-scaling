"""
Parse the Mode A Excel input template.
Returns parameters, target spectra, and the records manifest.
"""
from __future__ import annotations

import io
import numpy as np
import pandas as pd
from dataclasses import dataclass


@dataclass
class ExcelInputs:
    t_min: float
    t_max: float
    t_min_v: float | None
    t_max_v: float | None
    damping: float
    code: str
    combination_method: str
    alpha_h: float | None
    alpha_v: float | None
    sa_target_h: tuple[np.ndarray, np.ndarray]  # (periods, Sa)
    sa_target_v: tuple[np.ndarray, np.ndarray] | None
    records_manifest: list[dict]  # [{'id': ..., 'H1': filename, 'H2': filename, 'V': filename}]


def parse_excel_template(file_bytes: bytes) -> ExcelInputs:
    """Parse the uploaded Excel input template."""
    buf = io.BytesIO(file_bytes)

    try:
        params_df = pd.read_excel(buf, sheet_name="PARAMETERS", header=None, index_col=0)
    except Exception as e:
        raise ValueError(f"Cannot read PARAMETERS sheet: {e}")

    def get_param(key, default=None, required=True):
        try:
            val = params_df.loc[key, 1]
            return val if not pd.isna(val) else default
        except KeyError:
            if required:
                raise ValueError(f"Missing required parameter '{key}' in PARAMETERS sheet.")
            return default

    t_min = float(get_param("T_min"))
    t_max = float(get_param("T_max"))
    t_min_v = _optional_float(get_param("T_min_V", required=False))
    t_max_v = _optional_float(get_param("T_max_V", required=False))
    damping = float(get_param("Damping_pct", default=5.0, required=False)) / 100.0
    code = str(get_param("Code", default="ASCE 7-22", required=False)).strip()
    combination_method = str(get_param("SF_Method", default="geomean", required=False)).strip().lower()
    alpha_h = _optional_float(get_param("Alpha_H", required=False))
    alpha_v = _optional_float(get_param("Alpha_V", required=False))

    # Target spectrum sheets
    buf.seek(0)
    sa_target_h = _read_spectrum_sheet(buf, "TARGET_SPECTRUM_H")
    buf.seek(0)
    try:
        sa_target_v = _read_spectrum_sheet(buf, "TARGET_SPECTRUM_V")
    except Exception:
        sa_target_v = None

    # Records manifest
    buf.seek(0)
    try:
        rec_df = pd.read_excel(buf, sheet_name="RECORDS")
    except Exception as e:
        raise ValueError(f"Cannot read RECORDS sheet: {e}")

    records_manifest = []
    for _, row in rec_df.iterrows():
        entry = {
            "id": str(row.get("Record_ID", row.iloc[0])).strip(),
            "H1": str(row.get("H1_filename", row.iloc[1])).strip() if len(row) > 1 else None,
            "H2": str(row.get("H2_filename", row.iloc[2])).strip() if len(row) > 2 else None,
            "V": str(row.get("V_filename", row.iloc[3])).strip() if len(row) > 3 else None,
        }
        # Treat 'nan' strings as None
        for k in ["H1", "H2", "V"]:
            if entry[k] in ("nan", "None", ""):
                entry[k] = None
        records_manifest.append(entry)

    return ExcelInputs(
        t_min=t_min, t_max=t_max, t_min_v=t_min_v, t_max_v=t_max_v,
        damping=damping, code=code, combination_method=combination_method,
        alpha_h=alpha_h, alpha_v=alpha_v,
        sa_target_h=sa_target_h, sa_target_v=sa_target_v,
        records_manifest=records_manifest,
    )


def _read_spectrum_sheet(buf, sheet_name: str) -> tuple[np.ndarray, np.ndarray]:
    df = pd.read_excel(buf, sheet_name=sheet_name)
    df = df.dropna(how="all")
    if df.shape[1] < 2:
        raise ValueError(f"Sheet '{sheet_name}' must have at least 2 columns (Period, Sa).")
    periods = df.iloc[:, 0].values.astype(float)
    sa = df.iloc[:, 1].values.astype(float)
    if np.any(periods <= 0):
        raise ValueError(f"Period values in '{sheet_name}' must be positive.")
    if np.any(sa < 0):
        raise ValueError(f"Sa values in '{sheet_name}' must be non-negative.")
    return periods, sa


def _optional_float(val) -> float | None:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def create_input_template() -> bytes:
    """Generate a blank Excel input template for download."""
    wb_buf = io.BytesIO()

    with pd.ExcelWriter(wb_buf, engine="openpyxl") as writer:
        # PARAMETERS sheet
        params = pd.DataFrame([
            ["T_min", 0.20, "Lower bound of horizontal scaling period range (s)"],
            ["T_max", 3.00, "Upper bound of horizontal scaling period range (s)"],
            ["T_min_V", "", "Lower bound of vertical scaling period range (s) — leave blank if no vertical"],
            ["T_max_V", "", "Upper bound of vertical scaling period range (s) — leave blank if no vertical"],
            ["Damping_pct", 5.0, "Viscous damping ratio (%) — typically 5"],
            ["Code", "ASCE 7-22", "Compliance code: 'ASCE 7-22' or 'EC8-1' or 'Both'"],
            ["SF_Method", "geomean", "Horizontal combination: 'geomean' or 'srss'"],
            ["Alpha_H", "", "Horizontal spectral tolerance (leave blank for code default: ASCE=1.00, EC8=0.90)"],
            ["Alpha_V", "", "Vertical spectral tolerance (leave blank for code default)"],
        ], columns=["Parameter", "Value", "Notes"])
        params.to_excel(writer, sheet_name="PARAMETERS", index=False)

        # TARGET_SPECTRUM_H
        pd.DataFrame({"Period_s": [0.01, 0.1, 0.2, 0.5, 1.0, 2.0, 3.0, 4.0],
                       "Sa_g": ["", "", "", "", "", "", "", ""]}).to_excel(
            writer, sheet_name="TARGET_SPECTRUM_H", index=False)

        # TARGET_SPECTRUM_V
        pd.DataFrame({"Period_s": [0.01, 0.1, 0.2, 0.5, 1.0],
                       "Sa_g": ["", "", "", "", ""]}).to_excel(
            writer, sheet_name="TARGET_SPECTRUM_V", index=False)

        # RECORDS
        pd.DataFrame({
            "Record_ID": ["RSN123", "RSN456"],
            "H1_filename": ["RSN123_H1.AT2", "RSN456_H1.AT2"],
            "H2_filename": ["RSN123_H2.AT2", "RSN456_H2.AT2"],
            "V_filename": ["RSN123_V.AT2", ""],
        }).to_excel(writer, sheet_name="RECORDS", index=False)

    return wb_buf.getvalue()
