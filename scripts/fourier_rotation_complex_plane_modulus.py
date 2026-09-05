"""Plot Laplace-vs-centered Gamma response in complex plane and modulus.

Run: python3 scripts/fourier_rotation_complex_plane_modulus.py
Dependencies: numpy, matplotlib.
"""

import argparse
import os
from pathlib import Path
import tempfile

os.environ.setdefault(
    "MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "no-gauss-matplotlib")
)
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def exact_mean(theta, s, t, phi):
    """E[W_{1,2}] for rotated independent pair.

    W = (exp(i s X1') - phi(s)) (exp(i t X2') - phi(t)),
    where X' = (X1 cos θ - X2 sin θ, X1 sin θ + X2 cos θ).
    """
    c, z = np.cos(theta), np.sin(theta)
    joint = phi(s * c + t * z) * phi(-s * z + t * c)
    marginal_1 = phi(s * c) * phi(-s * z)
    marginal_2 = phi(t * z) * phi(t * c)
    return joint - phi(t) * marginal_1 - phi(s) * marginal_2 + phi(s) * phi(t)


def main():
    parser = argparse.ArgumentParser(
        description="Complex-plane trajectory and modulus for Laplace vs Gamma."
    )
    parser.add_argument(
        "--output", type=Path, default=Path("experiments/fourier_rotation")
    )
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)

    s, t = 1.0, 2.0
    gamma_shape = 2.0
    angles = np.linspace(-0.2, 0.2, 161)

    def gamma_phi(u):
        return np.exp(-1j * np.sqrt(gamma_shape) * u) * (
            1 - 1j * u / np.sqrt(gamma_shape)
        ) ** (-gamma_shape)

    laws = {
        "Laplace": lambda u: 1.0 / (1.0 + u**2 / 2.0),
        "Gamma": gamma_phi,
    }

    population_curves = {}
    for name, phi in laws.items():
        population_curves[name] = exact_mean(angles, s, t, phi)

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.5))

    # Complex-plane trajectory
    ax_plane = axes[0]
    for name, color in (("Laplace", "#147d92"), ("Gamma", "#db6c36")):
        z = population_curves[name]
        ax_plane.plot(z.real, z.imag, color=color, lw=2.2, label=name)
        ax_plane.scatter([z.real[0]], [z.imag[0]], color=color, s=12, zorder=3)
    ax_plane.axhline(0, color="#94a3b8", lw=0.8)
    ax_plane.axvline(0, color="#94a3b8", lw=0.8)
    ax_plane.set_title("Complex-plane trajectory")
    ax_plane.set_xlabel(r"$\mathrm{Re}\,G(\theta)$")
    ax_plane.set_ylabel(r"$\mathrm{Im}\,G(\theta)$")
    ax_plane.set_aspect("equal", adjustable="datalim")
    ax_plane.grid(alpha=0.18)
    ax_plane.legend(loc="lower left", frameon=False)

    # Modulus
    ax_mod = axes[1]
    for name, color in (("Laplace", "#147d92"), ("Gamma", "#db6c36")):
        ax_mod.plot(
            angles,
            np.abs(population_curves[name]),
            color=color,
            lw=2.2,
            label=name,
        )
    ax_mod.axvline(0, color="#94a3b8", lw=0.8)
    ax_mod.set_title("Modulus |G(θ)|")
    ax_mod.set_xlabel(r"Rotation angle $\theta$ (radians)")
    ax_mod.set_ylabel(r"$|G(\theta)|$")
    ax_mod.grid(alpha=0.18)
    ax_mod.legend(loc="best", frameon=False)

    fig.suptitle(
        r"Laplace vs centered Gamma: complex trajectory and modulus",
        fontsize=14,
        y=0.98,
    )
    fig.text(
        0.5,
        0.005,
        "s = 1, t = 2 | variance = 1 | Gamma shape = 2",
        ha="center",
        fontsize=9,
        color="#475569",
    )
    fig.tight_layout()
    fig.subplots_adjust(bottom=0.12, top=0.90)

    output_path = args.output / "laplace_gamma_complex_plane_modulus.png"
    fig.savefig(output_path, dpi=180, facecolor="white")
    plt.close(fig)
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()
