"""
Parse PEER NGA AT2 ground motion files.
Returns time step (dt in seconds) and acceleration array (in g).
"""

import numpy as np
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class GroundMotionRecord:
    filename: str
    npts: int
    dt: float
    acceleration: np.ndarray  # units: g
    pga: float
    duration: float
    component: str  # 'H1', 'H2', or 'V'
    record_id: str  # derived from filename prefix


def parse_at2(file_bytes: bytes, filename: str) -> GroundMotionRecord:
    """
    Parse a PEER AT2 file from raw bytes.
    Raises ValueError with a descriptive message on parse failure.
    """
    try:
        text = file_bytes.decode("utf-8", errors="replace")
    except Exception as e:
        raise ValueError(f"Cannot decode file '{filename}': {e}")

    lines = text.splitlines()
    if len(lines) < 5:
        raise ValueError(f"File '{filename}' has fewer than 5 lines — not a valid AT2 file.")

    # Lines 0-2: description (free text) — skip
    # Line 3: contains NPTS and DT
    header_line = lines[3]
    npts, dt = _parse_header(header_line, filename)

    # Lines 4+: acceleration values
    accel_text = " ".join(lines[4:])
    tokens = accel_text.split()
    try:
        accel = np.array([float(t) for t in tokens if t.strip()])
    except ValueError as e:
        raise ValueError(f"Non-numeric acceleration data in '{filename}': {e}")

    if len(accel) < npts:
        raise ValueError(
            f"'{filename}': expected {npts} acceleration points, found {len(accel)}."
        )
    accel = accel[:npts]

    component = _infer_component(filename)
    record_id = _infer_record_id(filename)

    return GroundMotionRecord(
        filename=filename,
        npts=npts,
        dt=dt,
        acceleration=accel,
        pga=float(np.max(np.abs(accel))),
        duration=float((npts - 1) * dt),
        component=component,
        record_id=record_id,
    )


def _parse_header(line: str, filename: str):
    """Extract NPTS and DT from AT2 header line 4."""
    # Standard PEER format: NPTS=  4096, DT= .0050 SEC
    npts_match = re.search(r"NPTS\s*=\s*(\d+)", line, re.IGNORECASE)
    dt_match = re.search(r"DT\s*=\s*([0-9.eE+\-]+)", line, re.IGNORECASE)

    if not npts_match:
        raise ValueError(f"Cannot find NPTS in header of '{filename}'. Line: '{line}'")
    if not dt_match:
        raise ValueError(f"Cannot find DT in header of '{filename}'. Line: '{line}'")

    npts = int(npts_match.group(1))
    dt = float(dt_match.group(1))

    if npts <= 0:
        raise ValueError(f"NPTS must be positive in '{filename}', got {npts}.")
    if dt <= 0:
        raise ValueError(f"DT must be positive in '{filename}', got {dt}.")

    return npts, dt


def _infer_component(filename: str) -> str:
    """Infer H1, H2, or V from filename suffix convention."""
    name = filename.upper().replace(".AT2", "")
    if name.endswith("_H1") or name.endswith("-H1"):
        return "H1"
    if name.endswith("_H2") or name.endswith("-H2"):
        return "H2"
    if name.endswith("_V") or name.endswith("-V") or name.endswith("_UP") or name.endswith("_UD"):
        return "V"
    # Default: treat as H1 if ambiguous
    return "H1"


def _infer_record_id(filename: str) -> str:
    """Strip component suffix and extension to get record ID."""
    name = filename
    # Remove extension
    for ext in [".AT2", ".at2"]:
        name = name.replace(ext, "")
    # Remove component suffix
    for suffix in ["_H1", "_H2", "_V", "-H1", "-H2", "-V", "_UP", "_UD"]:
        if name.upper().endswith(suffix.upper()):
            name = name[: -len(suffix)]
            break
    return name


def group_records(records: list[GroundMotionRecord]) -> dict[str, dict[str, GroundMotionRecord]]:
    """
    Group individual component records by record_id.
    Returns dict: {record_id: {'H1': record, 'H2': record, 'V': record}}
    Components H2 and V are optional.
    """
    groups: dict[str, dict[str, GroundMotionRecord]] = {}
    for rec in records:
        if rec.record_id not in groups:
            groups[rec.record_id] = {}
        groups[rec.record_id][rec.component] = rec
    return groups
