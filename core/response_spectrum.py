"""
Elastic response spectrum via Newmark-beta average acceleration (beta=0.25, gamma=0.5).
Formulation follows Chopra 'Dynamics of Structures' Ch.5 step-by-step method.
Returns pseudo-spectral acceleration Sa(T) in g.
"""
from __future__ import annotations

import numpy as np


PERIOD_ARRAY: np.ndarray = np.logspace(np.log10(0.01), np.log10(10.0), 100)


def compute_response_spectrum(
    accel: np.ndarray,
    dt: float,
    damping: float = 0.05,
    periods: np.ndarray = PERIOD_ARRAY,
) -> np.ndarray:
    """
    Compute Sa(T) for a single acceleration time series.

    Parameters
    ----------
    accel   : ground acceleration (g)
    dt      : time step (s)
    damping : fraction (e.g. 0.05 for 5%)
    periods : oscillator periods (s)

    Returns
    -------
    sa : pseudo-spectral acceleration (g)
    """
    ag = accel * 9.80665      # g → m/s²
    n  = len(ag)
    sa = np.empty(len(periods))

    beta  = 0.25
    gamma = 0.5

    for i, T in enumerate(periods):
        omega = 2.0 * np.pi / T
        c     = 2.0 * damping * omega     # per unit mass
        k     = omega ** 2                # per unit mass

        # Effective stiffness (Chopra Eq. 5.4.6)
        k_eff = k + gamma / (beta * dt) * c + 1.0 / (beta * dt**2)

        # Coefficients for effective force (Chopra Eq. 5.4.8)
        a1 = 1.0 / (beta * dt**2)
        a2 = 1.0 / (beta * dt)
        a3 = 1.0 / (2.0 * beta) - 1.0

        u, v = 0.0, 0.0
        a    = -ag[0]     # from eq. of motion at t=0

        sd = 0.0

        for j in range(1, n):
            # Effective force (Chopra Eq. 5.4.7)
            p_eff = -ag[j] + a1 * u + a2 * v + a3 * a

            # New displacement
            u_new = p_eff / k_eff

            # New acceleration (Chopra Eq. 5.4.10)
            a_new = (u_new - u) / (beta * dt**2) - v / (beta * dt) - a3 * a

            # New velocity (Chopra Eq. 5.4.11)
            v_new = v + dt * ((1.0 - gamma) * a + gamma * a_new)

            u, v, a = u_new, v_new, a_new

            au = abs(u)
            if au > sd:
                sd = au

        sa[i] = omega**2 * sd / 9.80665    # pseudo-Sa in g

    return sa


def geometric_mean_spectrum(sa_h1: np.ndarray, sa_h2: np.ndarray) -> np.ndarray:
    return np.sqrt(sa_h1 * sa_h2)


def srss_spectrum(sa_h1: np.ndarray, sa_h2: np.ndarray) -> np.ndarray:
    return np.sqrt(sa_h1**2 + sa_h2**2)
