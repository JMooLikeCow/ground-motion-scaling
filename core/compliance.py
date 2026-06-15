"""
Code compliance checks for ASCE 7-22 and EC8-2 (Eurocode 8, 2nd generation).
Pass/fail is determined by: mean(scaled spectra) >= alpha * target
where alpha is user-controllable (default per code).

EC8-2 (Annex D) adds a second criterion: no individual record's combined scaled
spectrum may fall below 50% of the target over the period range of interest.
"""
from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field


ALPHA_DEFAULTS = {
    "ASCE 7-22": 0.90,
    "EC8-2": 0.95,
}

MIN_RECORDS = {
    "ASCE 7-22": 11,
    "EC8-2": 3,
}

# Per-code individual-record floor: no single record's combined scaled spectrum
# may fall below this fraction of the target over the period range of interest.
# EC8 2nd generation (Annex D) requires each record >= 50% of target.
INDIVIDUAL_FLOOR = {
    "EC8-2": 0.50,
}


@dataclass
class RecordCompliance:
    record_id: str
    below_target_h: bool      # individual record < target at any period in range (informational)
    below_target_v: bool | None
    min_ratio_h: float        # min(Sa_scaled / Sa_target) over range
    min_ratio_v: float | None


@dataclass
class SuiteCompliance:
    code: str
    alpha_h: float
    alpha_v: float
    alpha_h_is_default: bool
    alpha_v_is_default: bool

    suite_pass_h: bool
    suite_pass_v: bool | None

    deficiency_h: float       # max((alpha*target - mean) / (alpha*target)) over range, 0 if pass
    deficiency_v: float | None
    worst_period_h: float     # period of maximum deficiency
    worst_period_v: float | None

    mean_ratio_h: np.ndarray  # mean(scaled) / target at every period
    mean_ratio_v: np.ndarray | None

    record_results: list[RecordCompliance]
    n_records: int
    min_records_warning: bool

    # Individual-record floor criterion (EC8-2 Annex D): each record's combined
    # scaled spectrum must stay >= individual_floor * target over the range.
    individual_floor: float | None = None      # e.g. 0.50, or None if code has no floor
    floor_pass: bool | None = None             # True/False, or None if no floor applies
    floor_violations: list[str] = field(default_factory=list)  # record IDs breaching the floor
    worst_floor_ratio: float | None = None     # min(Sa_record/target) across all records & periods


def check_compliance(
    scaled_combined: dict[str, np.ndarray],   # {record_id: scaled combined Sa}
    scaled_v: dict[str, np.ndarray] | None,   # {record_id: scaled V Sa} or None
    sa_target_h: np.ndarray,
    sa_target_v: np.ndarray | None,
    periods: np.ndarray,
    t_min: float,
    t_max: float,
    t_min_v: float | None,
    t_max_v: float | None,
    code: str,
    alpha_h: float | None = None,
    alpha_v: float | None = None,
) -> SuiteCompliance:
    """
    Run compliance check for a given code standard.

    alpha_h / alpha_v: if None, use code default.
    """
    default_alpha = ALPHA_DEFAULTS[code]
    alpha_h = alpha_h if alpha_h is not None else default_alpha
    alpha_v = alpha_v if alpha_v is not None else default_alpha
    alpha_h_is_default = np.isclose(alpha_h, default_alpha)
    alpha_v_is_default = np.isclose(alpha_v, default_alpha)

    n_records = len(scaled_combined)
    min_rec = MIN_RECORDS[code]
    min_records_warning = n_records < min_rec

    # Horizontal period mask
    mask_h = (periods >= t_min) & (periods <= t_max)
    periods_h = periods[mask_h]

    # Stack all scaled spectra
    matrix_h = np.vstack([sa[mask_h] for sa in scaled_combined.values()])
    mean_h = np.mean(matrix_h, axis=0)
    target_h_range = sa_target_h[mask_h]

    # Ratio: mean / target
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio_h_range = np.where(target_h_range > 0, mean_h / target_h_range, np.inf)

    # Full-period ratio for plot output
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio_h_full = np.where(sa_target_h > 0, np.mean(
            np.vstack(list(scaled_combined.values())), axis=0
        ) / sa_target_h, np.inf)

    deficiency_h = max(0.0, float(np.max(alpha_h - ratio_h_range)))
    worst_idx_h = int(np.argmin(ratio_h_range))
    worst_period_h = float(periods_h[worst_idx_h])
    suite_pass_h = bool(np.all(ratio_h_range >= alpha_h))

    # Individual-record floor criterion (EC8-2 Annex D): each record's combined
    # scaled spectrum must remain >= floor * target across the range.
    individual_floor = INDIVIDUAL_FLOOR.get(code)
    floor_violations: list[str] = []
    worst_floor_ratio: float | None = None

    # Per-record horizontal flags
    record_results = []
    for rid, sa_sc in scaled_combined.items():
        r_h = sa_sc[mask_h] / np.where(target_h_range > 0, target_h_range, np.inf)
        below_h = bool(np.any(r_h < alpha_h))
        rec_min_ratio = float(np.min(r_h))
        record_results.append(RecordCompliance(
            record_id=rid,
            below_target_h=below_h,
            below_target_v=None,
            min_ratio_h=rec_min_ratio,
            min_ratio_v=None,
        ))
        if individual_floor is not None:
            worst_floor_ratio = rec_min_ratio if worst_floor_ratio is None else min(worst_floor_ratio, rec_min_ratio)
            if rec_min_ratio < individual_floor:
                floor_violations.append(rid)

    floor_pass = None if individual_floor is None else (len(floor_violations) == 0)

    # Vertical compliance
    suite_pass_v = None
    deficiency_v = None
    worst_period_v = None
    mean_ratio_v = None

    if scaled_v and sa_target_v is not None and t_min_v is not None and t_max_v is not None:
        mask_v = (periods >= t_min_v) & (periods <= t_max_v)
        periods_v = periods[mask_v]
        matrix_v = np.vstack([sa[mask_v] for sa in scaled_v.values()])
        mean_v = np.mean(matrix_v, axis=0)
        target_v_range = sa_target_v[mask_v]

        with np.errstate(divide="ignore", invalid="ignore"):
            ratio_v_range = np.where(target_v_range > 0, mean_v / target_v_range, np.inf)

        with np.errstate(divide="ignore", invalid="ignore"):
            mean_ratio_v = np.where(
                sa_target_v > 0,
                np.mean(np.vstack(list(scaled_v.values())), axis=0) / sa_target_v,
                np.inf,
            )

        deficiency_v = max(0.0, float(np.max(alpha_v - ratio_v_range)))
        worst_idx_v = int(np.argmin(ratio_v_range))
        worst_period_v = float(periods_v[worst_idx_v])
        suite_pass_v = bool(np.all(ratio_v_range >= alpha_v))

        # Per-record vertical flag
        for i, (rid, sa_v_sc) in enumerate(scaled_v.items()):
            r_v = sa_v_sc[mask_v] / np.where(target_v_range > 0, target_v_range, np.inf)
            record_results[i].below_target_v = bool(np.any(r_v < alpha_v))
            record_results[i].min_ratio_v = float(np.min(r_v))

    return SuiteCompliance(
        code=code,
        alpha_h=alpha_h,
        alpha_v=alpha_v,
        alpha_h_is_default=alpha_h_is_default,
        alpha_v_is_default=alpha_v_is_default,
        suite_pass_h=suite_pass_h,
        suite_pass_v=suite_pass_v,
        deficiency_h=deficiency_h,
        deficiency_v=deficiency_v,
        worst_period_h=worst_period_h,
        worst_period_v=worst_period_v,
        mean_ratio_h=ratio_h_full,
        mean_ratio_v=mean_ratio_v,
        record_results=record_results,
        n_records=n_records,
        min_records_warning=min_records_warning,
        individual_floor=individual_floor,
        floor_pass=floor_pass,
        floor_violations=floor_violations,
        worst_floor_ratio=worst_floor_ratio,
    )
