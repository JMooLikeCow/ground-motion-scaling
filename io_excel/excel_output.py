"""
Generate the output Excel workbook.
Sheets: SUMMARY, REPORT, RECORDS_LOG, plus one image sheet per plot.
"""

import io
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.drawing.image import Image as XLImage

from core.scaling import ScalingResult
from core.compliance import SuiteCompliance


_GREEN = "FF92D050"
_RED   = "FFFF0000"
_AMBER = "FFFFC000"
_BLUE_HDR = "FF4C72B0"
_WHITE = "FFFFFFFF"


def _hdr_style(ws, row, col, value, bg=_BLUE_HDR):
    cell = ws.cell(row=row, column=col, value=value)
    cell.font = Font(bold=True, color=_WHITE, size=10)
    cell.fill = PatternFill("solid", fgColor=bg)
    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    return cell


def _thin_border():
    s = Side(style="thin")
    return Border(left=s, right=s, top=s, bottom=s)


def build_excel(
    scaling_results: dict[str, ScalingResult],
    compliance_results: list[SuiteCompliance],
    report_md: str,
    figures: dict[str, go.Figure],
    periods: np.ndarray,
    at2_records: dict,
) -> bytes:
    """
    Build the output workbook and return as bytes for Streamlit download.

    figures: {'spectra': fig, 'sigma': fig, 'sf': fig, 'deviation': fig, 'th_<id>': fig}
    """
    wb = Workbook()
    wb.remove(wb.active)  # remove default sheet

    _write_summary(wb, scaling_results, compliance_results, periods)
    _write_report(wb, report_md)
    _write_records_log(wb, at2_records, scaling_results)
    _write_plots(wb, figures)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _write_summary(wb, scaling_results, compliance_results, periods):
    ws = wb.create_sheet("SUMMARY")
    ws.sheet_view.showGridLines = False

    # Title
    ws.merge_cells("A1:H1")
    c = ws["A1"]
    c.value = "GROUND MOTION SCALING — SUMMARY"
    c.font = Font(bold=True, size=13, color=_WHITE)
    c.fill = PatternFill("solid", fgColor=_BLUE_HDR)
    c.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 24

    # Scale factor table
    row = 3
    headers = ["Record ID", "SF (H)", "SF (V)", "Scaled PGA H1 (g)", "Scaled PGA V (g)"]
    for ci, h in enumerate(headers, 1):
        _hdr_style(ws, row, ci, h)

    row += 1
    for rid, r in scaling_results.items():
        ws.cell(row=row, column=1, value=rid)
        ws.cell(row=row, column=2, value=round(r.sf_h, 4))
        ws.cell(row=row, column=3, value=round(r.sf_v, 4) if r.sf_v else "N/A")
        pga_h = r.sf_h * float(np.max(np.abs(r.sa_h1_unscaled))) if r.sa_h1_unscaled is not None else "N/A"
        pga_v = r.sf_v * float(np.max(np.abs(r.sa_v_unscaled))) if r.sa_v_unscaled is not None and r.sf_v else "N/A"
        ws.cell(row=row, column=4, value=round(pga_h, 4) if isinstance(pga_h, float) else pga_h)
        ws.cell(row=row, column=5, value=round(pga_v, 4) if isinstance(pga_v, float) else pga_v)
        for ci in range(1, 6):
            ws.cell(row=row, column=ci).border = _thin_border()
        row += 1

    row += 1

    # Compliance table
    for comp in compliance_results:
        _hdr_style(ws, row, 1, f"Compliance — {comp.code}", bg="FF2E5E9B")
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=5)
        row += 1

        for label, pass_val, alpha in [
            ("Horizontal suite", comp.suite_pass_h, comp.alpha_h),
            ("Vertical suite", comp.suite_pass_v, comp.alpha_v),
        ]:
            if pass_val is None:
                continue
            ws.cell(row=row, column=1, value=f"{label} (α = {alpha:.2f})")
            cell = ws.cell(row=row, column=2, value="PASS" if pass_val else "FAIL")
            cell.font = Font(bold=True)
            cell.fill = PatternFill("solid", fgColor=_GREEN if pass_val else _RED)
            row += 1

        if comp.min_records_warning:
            min_r = {"ASCE 7-22": 11, "EC8-1": 3}[comp.code]
            ws.cell(row=row, column=1, value=f"⚠ Record count below {comp.code} minimum ({min_r})")
            ws.cell(row=row, column=1).font = Font(color="FFFF0000")
            row += 1

        row += 1

    for col in range(1, 9):
        ws.column_dimensions[get_column_letter(col)].width = 20


def _write_report(wb, report_md: str):
    ws = wb.create_sheet("REPORT")
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 120

    lines = report_md.split("\n")
    for i, line in enumerate(lines, 1):
        cell = ws.cell(row=i, column=1, value=line)
        if line.startswith("## "):
            cell.font = Font(bold=True, size=12, color=_WHITE)
            cell.fill = PatternFill("solid", fgColor=_BLUE_HDR)
        elif line.startswith("### "):
            cell.font = Font(bold=True, size=11)
        elif line.startswith("- **") or line.startswith("- "):
            cell.font = Font(size=10)
        cell.alignment = Alignment(wrap_text=True)


def _write_records_log(wb, at2_records, scaling_results):
    ws = wb.create_sheet("RECORDS_LOG")
    ws.sheet_view.showGridLines = False

    headers = ["Record ID", "Component", "Filename", "NPTS", "DT (s)", "Duration (s)", "Unscaled PGA (g)", "Scale Factor Applied"]
    for ci, h in enumerate(headers, 1):
        _hdr_style(ws, 1, ci, h)

    row = 2
    for rid, group in at2_records.items():
        sf_h = scaling_results[rid].sf_h if rid in scaling_results else None
        sf_v = scaling_results[rid].sf_v if rid in scaling_results else None
        for comp, rec in group.items():
            sf = sf_v if comp == "V" else sf_h
            ws.cell(row=row, column=1, value=rid)
            ws.cell(row=row, column=2, value=comp)
            ws.cell(row=row, column=3, value=rec.filename)
            ws.cell(row=row, column=4, value=rec.npts)
            ws.cell(row=row, column=5, value=rec.dt)
            ws.cell(row=row, column=6, value=round(rec.duration, 3))
            ws.cell(row=row, column=7, value=round(rec.pga, 5))
            ws.cell(row=row, column=8, value=round(sf, 4) if sf else "N/A")
            for ci in range(1, 9):
                ws.cell(row=row, column=ci).border = _thin_border()
            row += 1

    for col in range(1, 9):
        ws.column_dimensions[get_column_letter(col)].width = 22


def _write_plots(wb, figures: dict[str, go.Figure]):
    plot_sheet_names = {
        "spectra": "PLOT_SPECTRA",
        "sigma": "PLOT_SIGMA",
        "sf": "PLOT_SF",
        "deviation": "PLOT_DEV",
    }

    for key, sheet_name in plot_sheet_names.items():
        if key not in figures:
            continue
        fig = figures[key]
        ws = wb.create_sheet(sheet_name)
        _embed_figure(ws, fig)

    # Time history plots (one per record, all on one sheet)
    th_keys = sorted([k for k in figures if k.startswith("th_")])
    if th_keys:
        ws = wb.create_sheet("PLOT_TH")
        row_offset = 1
        for key in th_keys:
            fig = figures[key]
            img_bytes = fig.to_image(format="png", width=1000, height=500, scale=1.5)
            img_stream = io.BytesIO(img_bytes)
            img = XLImage(img_stream)
            img.anchor = f"A{row_offset}"
            ws.add_image(img)
            row_offset += 30


def _embed_figure(ws, fig: go.Figure):
    """Render Plotly figure as PNG and embed in worksheet."""
    try:
        img_bytes = fig.to_image(format="png", width=1200, height=700, scale=1.5)
        img_stream = io.BytesIO(img_bytes)
        img = XLImage(img_stream)
        img.anchor = "A1"
        ws.add_image(img)
    except Exception:
        ws["A1"] = "Plot could not be rendered. Install kaleido: pip install kaleido"
