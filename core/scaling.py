"""
Amplitude scaling via two-step process:
  Step 1 — per-record MSE minimisation against target over [T_min, T_max]
  Step 2 — suite correction: uniform upward adjustment to all SFs so that
            mean(SF_i * Sa_pair_i(T)) >= alpha * target(T) at every T in range.

The correction factor is:
    k_adj = max over T in [T_min, T_max] of ( alpha * target(T) / mean_scaled(T) )
Applied only if k_adj > 1 (suite is deficient).
"""
from __future__ import annotations

import numpy as np
from dataclasses import dataclass


@dataclass
class ScalingResult:
    record_id: str
    sf_h: float                          # final horizontal scale factor (after suite correction)
    sf_v: float | None                   # final vertical scale factor
    sf_h_individual: float               # step-1 MSE factor before suite correction
    sf_h_suite_correction: float         # k_adj applied (1.0 if no correction needed)
    sa_h1_unscaled: np.ndarray
    sa_h2_unscaled: np.ndarray | None
    sa_v_unscaled: np.ndarray | None
    sa_combined_unscaled: np.ndarray     # geomean or SRSS of H1/H2, unscaled
    sa_combined_scaled: np.ndarray       # final scaled combined spectrum


@dataclass
class SuiteScalingMetadata:
    combination_method: str
    suite_correction_h: float            # k_adj for horizontal (1.0 if no correction)
    suite_correction_v: float | None     # k_adj for vertical
    alpha_h: float                       # tolerance used for suite correction
    alpha_v: float | None


def _mse_scale_factor(
    sa_record: np.ndarray,
    sa_target: np.ndarray,
    periods: np.ndarray,
    t_min: float,
    t_max: float,
) -> float:
    """
    Closed-form MSE scale factor over [t_min, t_max].
    SF = sum(Sa_r * Sa_t) / sum(Sa_r^2)
    Minimises sum of squared residuals between SF*Sa_r and Sa_t.
    """
    mask = (periods >= t_min) & (periods <= t_max)
    if not np.any(mask):
        raise ValueError(
            f"No periods found in [{t_min}, {t_max}] s. "
            "Check T_min/T_max against the period array range (0.01–10.0 s)."
        )
    sa_r = sa_record[mask]
    sa_t = sa_target[mask]
    denom = np.sum(sa_r ** 2)
    if denom < 1e-14:
        raise ValueError("Record spectrum is essentially zero — cannot compute scale factor.")
    return float(np.sum(sa_r * sa_t) / denom)


def _suite_correction_factor(
    individual_sfs: dict[str, float],
    sa_combined: dict[str, np.ndarray],
    sa_target: np.ndarray,
    periods: np.ndarray,
    t_min: float,
    t_max: float,
    alpha: float,
) -> float:
    """
    Compute the suite-level correction factor k_adj such that after applying it,
    the suite mean >= alpha * target at every period in [T_min, T_max].

    k_adj = max( alpha * target(T) / mean_scaled(T) ) over T in range
    Returns 1.0 if the suite already passes (no upward correction needed).
    """
    mask = (periods >= t_min) & (periods <= t_max)
    # Suite mean of step-1 scaled spectra
    scaled_matrix = np.vstack([individual_sfs[rid] * sa_combined[rid] for rid in individual_sfs])
    mean_scaled = np.mean(scaled_matrix, axis=0)[mask]
    target_range = sa_target[mask]

    with np.errstate(divide="ignore", invalid="ignore"):
        deficiency = np.where(
            mean_scaled > 0,
            alpha * target_range / mean_scaled,
            1.0,
        )
    k_adj = float(np.max(deficiency))
    return max(1.0, k_adj)


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
    combination_method: str = "geomean",
    alpha_h: float = 1.0,
    alpha_v: float = 1.0,
) -> tuple[dict[str, ScalingResult], SuiteScalingMetadata]:
    """
    Two-step amplitude scaling for a suite of ground motion records.

    Returns
    -------
    results  : {record_id: ScalingResult}
    metadata : SuiteScalingMetadata
    """
    from core.response_spectrum import geometric_mean_spectrum, srss_spectrum

    # ── Step 1: per-record MSE scale factors ──────────────────────────────────
    sa_combined: dict[str, np.ndarray] = {}
    sf_h_individual: dict[str, float] = {}

    for rid, sa_h1 in spectra_h1.items():
        sa_h2 = spectra_h2.get(rid) if spectra_h2 else None
        if sa_h2 is not None:
            if combination_method == "srss":
                sa_comb = srss_spectrum(sa_h1, sa_h2)
            else:
                sa_comb = geometric_mean_spectrum(sa_h1, sa_h2)
        else:
            sa_comb = sa_h1.copy()
        sa_combined[rid] = sa_comb
        sf_h_individual[rid] = _mse_scale_factor(sa_comb, sa_target_h, periods, t_min, t_max)

    # ── Step 2: suite correction for horizontal ───────────────────────────────
    k_adj_h = _suite_correction_factor(
        sf_h_individual, sa_combined, sa_target_h,
        periods, t_min, t_max, alpha_h,
    )
    # Final horizontal SFs = individual SF * suite correction
    sf_h_final = {rid: sf * k_adj_h for rid, sf in sf_h_individual.items()}

    # ── Vertical (same two-step logic, independent) ───────────────────────────
    sf_v_individual: dict[str, float] = {}
    k_adj_v: float | None = None

    if spectra_v and sa_target_v is not None and t_min_v is not None and t_max_v is not None:
        for rid, sa_v in spectra_v.items():
            sf_v_individual[rid] = _mse_scale_factor(sa_v, sa_target_v, periods, t_min_v, t_max_v)

        k_adj_v = _suite_correction_factor(
            sf_v_individual, spectra_v, sa_target_v,
            periods, t_min_v, t_max_v, alpha_v,
        )
        sf_v_final = {rid: sf * k_adj_v for rid, sf in sf_v_individual.items()}
    else:
        sf_v_final = {}

    # ── Assemble results ──────────────────────────────────────────────────────
    results: dict[str, ScalingResult] = {}
    for rid in spectra_h1:
        sf_h = sf_h_final[rid]
        sf_v = sf_v_final.get(rid)
        sa_h2 = (spectra_h2.get(rid) if spectra_h2 else None)
        sa_v  = (spectra_v.get(rid)  if spectra_v  else None)

        results[rid] = ScalingResult(
            record_id=rid,
            sf_h=sf_h,
            sf_v=sf_v,
            sf_h_individual=sf_h_individual[rid],
            sf_h_suite_correction=k_adj_h,
            sa_h1_unscaled=spectra_h1[rid],
            sa_h2_unscaled=sa_h2,
            sa_v_unscaled=sa_v,
            sa_combined_unscaled=sa_combined[rid],
            sa_combined_scaled=sf_h * sa_combined[rid],
        )

    metadata = SuiteScalingMetadata(
        combination_method=combination_method,
        suite_correction_h=k_adj_h,
        suite_correction_v=k_adj_v,
        alpha_h=alpha_h,
        alpha_v=alpha_v if k_adj_v is not None else None,
    )

    return results, metadata
