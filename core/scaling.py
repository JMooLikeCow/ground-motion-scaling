"""
Amplitude scaling via closed-form MSE minimisation.
SF = sum(Sa_pair * Sa_target) / sum(Sa_pair^2)  over [T_min, T_max]
"""
from __future__ import annotations

import numpy as np
from dataclasses import dataclass


@dataclass
class ScalingResult:
    record_id: str
    sf_h: float
    sf_v: float | None
    sa_h1_unscaled: np.ndarray
    sa_h2_unscaled: np.ndarray | None
    sa_v_unscaled: np.ndarray | None
    sa_combined_unscaled: np.ndarray   # geomean or SRSS of H1/H2
    sa_combined_scaled: np.ndarray
    sa_v_scaled: np.ndarray | None


def compute_scale_factor(
    sa_record: np.ndarray,
    sa_target: np.ndarray,
    periods: np.ndarray,
    t_min: float,
    t_max: float,
) -> float:
    """
    Closed-form MSE scale factor over [t_min, t_max].
    SF = sum(Sa_r * Sa_t) / sum(Sa_r^2)
    """
    mask = (periods >= t_min) & (periods <= t_max)
    if not np.any(mask):
        raise ValueError(
            f"No periods found in range [{t_min}, {t_max}] s. "
            "Check T_min/T_max against the internal period array (0.01–10.0 s)."
        )

    sa_r = sa_record[mask]
    sa_t = sa_target[mask]

    denom = np.sum(sa_r ** 2)
    if denom < 1e-12:
        raise ValueError("Record spectrum is essentially zero — cannot compute scale factor.")

    return float(np.sum(sa_r * sa_t) / denom)


def scale_suite(
    spectra_h1: dict[str, np.ndarray],
    spectra_h2: dict[str, np.ndarray] | None,
    spectra_v: dict[str, np.ndarray] | None,
    sa_target_h: np.ndarray,
    sa_target_v: np.ndarray | None,
    periods: np.ndarray,
    t_min: float,
    t_max: float,
    t_min_v: float | None,
    t_max_v: float | None,
    combination_method: str = "geomean",  # 'geomean' or 'srss'
) -> dict[str, ScalingResult]:
    """
    Compute scale factors for all records in the suite.

    Parameters
    ----------
    spectra_h1 : {record_id: Sa array}
    spectra_h2 : {record_id: Sa array} or None (single component)
    spectra_v  : {record_id: Sa array} or None
    combination_method : 'geomean' or 'srss'

    Returns
    -------
    results : {record_id: ScalingResult}
    """
    from core.response_spectrum import geometric_mean_spectrum, srss_spectrum

    results = {}

    for rid, sa_h1 in spectra_h1.items():
        sa_h2 = spectra_h2.get(rid) if spectra_h2 else None
        sa_v = spectra_v.get(rid) if spectra_v else None

        # Combined horizontal spectrum
        if sa_h2 is not None:
            if combination_method == "srss":
                sa_combined = srss_spectrum(sa_h1, sa_h2)
            else:
                sa_combined = geometric_mean_spectrum(sa_h1, sa_h2)
        else:
            sa_combined = sa_h1.copy()

        sf_h = compute_scale_factor(sa_combined, sa_target_h, periods, t_min, t_max)
        sa_combined_scaled = sf_h * sa_combined

        # Vertical
        sf_v = None
        sa_v_scaled = None
        if sa_v is not None and sa_target_v is not None and t_min_v is not None and t_max_v is not None:
            sf_v = compute_scale_factor(sa_v, sa_target_v, periods, t_min_v, t_max_v)
            sa_v_scaled = sf_v * sa_v

        results[rid] = ScalingResult(
            record_id=rid,
            sf_h=sf_h,
            sf_v=sf_v,
            sa_h1_unscaled=sa_h1,
            sa_h2_unscaled=sa_h2,
            sa_v_unscaled=sa_v,
            sa_combined_unscaled=sa_combined,
            sa_combined_scaled=sa_combined_scaled,
            sa_v_scaled=sa_v_scaled,
        )

    return results
