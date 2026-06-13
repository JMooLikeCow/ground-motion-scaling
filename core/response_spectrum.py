"""
Elastic response spectrum via Newmark-beta average acceleration (beta=0.25, gamma=0.5).
Formulation: Chopra "Dynamics of Structures" 4th Ed., Section 5.4, Eqs 5.4.6–5.4.11.
Returns pseudo-spectral acceleration Sa(T) in g.
"""
from __future__ import annotations

import numpy as np


PERIOD_ARRAY: np.ndarray = np.concatenate([
    np.linspace(0.01, 0.10, 10, endpoint=False),
    np.linspace(0.10, 0.50, 20, endpoint=False),
    np.linspace(0.50, 3.00, 50, endpoint=False),
    np.linspace(3.00, 10.0, 20),
])  # 100 points, denser in the engineering range 0.1–3.0 s


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
    ag = accel * 9.80665       # g → m/s²
    n  = len(ag)
    xi = damping
    sa = np.empty(len(periods))

    beta  = 0.25
    gamma = 0.5

    for i, T in enumerate(periods):
        omega  = 2.0 * np.pi / T
        c      = 2.0 * xi * omega     # damping coefficient per unit mass
        k      = omega ** 2           # stiffness per unit mass

        # Effective stiffness — Chopra Eq. 5.4.6
        k_eff = k + gamma / (beta * dt) * c + 1.0 / (beta * dt**2)

        # Effective force coefficients — Chopra Eq. 5.4.8
        # BUG FIX: a1 and a2 must include the damping coupling terms
        a1 = 1.0 / (beta * dt**2) + gamma * c / (beta * dt)
        a2 = 1.0 / (beta * dt)   + (gamma / beta - 1.0) * c
        a3 = 1.0 / (2.0 * beta)  - 1.0
        # Note: for gamma=0.5, the dt*c term in a3 = dt*(gamma/(2*beta)-1)*c = 0

        u, v = 0.0, 0.0
        a    = -ag[0]      # initial SDOF acceleration from equilibrium

        sd = 0.0

        for j in range(1, n):
            # Effective force at step j — Chopra Eq. 5.4.7
            p_eff = -ag[j] + a1 * u + a2 * v + a3 * a

            # Displacement — Chopra Eq. 5.4.9
            u_new = p_eff / k_eff

            # Acceleration — Chopra Eq. 5.4.10
            a_new = (u_new - u) / (beta * dt**2) - v / (beta * dt) - a3 * a

            # Velocity — Chopra Eq. 5.4.11
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
