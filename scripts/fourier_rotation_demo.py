"""Monte Carlo check of the centered two-frequency rotation detector.

Run: python3 scripts/fourier_rotation_demo.py
Dependencies: numpy, matplotlib. Output: experiments/fourier_rotation/.
Each observation is an independent pair (X1, X2); all laws have variance 1.
Gamma uses X = (Y - 2) / sqrt(2), where Y ~ Gamma(shape=2, scale=1).
"""

import argparse
import json
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
    """E W for (X1 cos(theta)-X2 sin(theta), X1 sin(theta)+X2 cos(theta))."""
    c, z = np.cos(theta), np.sin(theta)
    joint = phi(s * c + t * z) * phi(-s * z + t * c)
    marginal_1 = phi(s * c) * phi(-s * z)
    marginal_2 = phi(t * z) * phi(t * c)
    return joint - phi(t) * marginal_1 - phi(s) * marginal_2 + phi(s) * phi(t)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20260904)
    parser.add_argument("--output", type=Path, default=Path("experiments/fourier_rotation"))
    args = parser.parse_args()
    if args.pairs < 2:
        parser.error("--pairs must be at least 2")
    args.output.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(args.seed)
    s, t = 1.0, 2.0
    angles = np.linspace(-0.2, 0.2, 161)
    gamma_shape = 2.0

    def gamma_phi(u):
        return np.exp(-1j * np.sqrt(gamma_shape) * u) * (
            1 - 1j * u / np.sqrt(gamma_shape)
        ) ** (-gamma_shape)

    laws = {
        "Laplace": (
            lambda u: 1.0 / (1.0 + u**2 / 2.0),
            lambda u: -u / (1.0 + u**2 / 2.0) ** 2,
            lambda: rng.laplace(scale=1 / np.sqrt(2), size=(args.pairs, 2)),
        ),
        "Gaussian": (
            lambda u: np.exp(-u**2 / 2.0),
            lambda u: -u * np.exp(-u**2 / 2.0),
            lambda: rng.normal(size=(args.pairs, 2)),
        ),
        "Gamma": (
            gamma_phi,
            lambda u: -u * gamma_phi(u) / (1 - 1j * u / np.sqrt(gamma_shape)),
            lambda: (rng.gamma(shape=gamma_shape, size=(args.pairs, 2)) - gamma_shape)
            / np.sqrt(gamma_shape),
        ),
    }
    fig, axes = plt.subplots(2, len(laws), figsize=(6 * len(laws), 8),
                             sharex=True, sharey=True)
    summary = {"pairs_per_law": args.pairs, "seed": args.seed, "s": s, "t": t}
    extent = 0.0
    population_curves = {}

    for column, (name, (phi, dphi, sample)) in enumerate(laws.items()):
        x, y = sample().T

        def features(theta):
            c, z = np.cos(theta), np.sin(theta)
            return (np.exp(1j * s * (c * x - z * y)) - phi(s)) * (
                np.exp(1j * t * (z * x + c * y)) - phi(t)
            )

        # Reuse the same pairs at every angle. Center using the TRUE phi;
        # do not subtract the empirical intercept or recenter the samples.
        values = np.array([features(theta) for theta in angles])
        means = values.mean(axis=1)
        standard_errors = np.array([
            values.real.std(axis=1, ddof=1), values.imag.std(axis=1, ddof=1)
        ]) / np.sqrt(args.pairs)
        theoretical = exact_mean(angles, s, t, phi)
        population_curves[name] = theoretical
        response = t * dphi(s) * phi(t) - s * phi(s) * dphi(t)

        # Differentiate each sampled W at zero, rather than fitting a line
        # across a finite interval where the population curve is nonlinear.
        ex, ey = np.exp(1j * s * x), np.exp(1j * t * y)
        derivative_samples = (
            -1j * s * y * ex * (ey - phi(t))
            + 1j * t * x * ey * (ex - phi(s))
        )
        slope = derivative_samples.mean()
        slope_se = np.array([
            derivative_samples.real.std(ddof=1), derivative_samples.imag.std(ddof=1)
        ]) / np.sqrt(args.pairs)
        intercept = features(0).mean()
        step = 1e-5
        empirical_fd = (features(step).mean() - features(-step).mean()) / (2 * step)
        theoretical_fd = (
            exact_mean(step, s, t, phi) - exact_mean(-step, s, t, phi)
        ) / (2 * step)

        summary[name] = {
            "theoretical_slope": [float(np.real(response)), float(np.imag(response))],
            "theoretical_slope_modulus": float(abs(response)),
            "theoretical_slope_phase_degrees": (
                float(np.degrees(np.angle(response))) if abs(response) > 1e-12 else None
            ),
            "empirical_intercept": [float(intercept.real), float(intercept.imag)],
            "empirical_slope": [float(slope.real), float(slope.imag)],
            "empirical_slope_modulus": float(abs(slope)),
            "empirical_slope_phase_degrees": float(np.degrees(np.angle(slope))),
            "slope_standard_error": slope_se.tolist(),
            "empirical_derivative_check_error": float(abs(empirical_fd - slope)),
            "theoretical_derivative_check_error": float(abs(theoretical_fd - response)),
            "max_abs_theoretical_mean": float(np.max(np.abs(theoretical))),
        }
        if name == "Gamma":
            summary[name]["shape"] = gamma_shape
            summary[name]["standardization"] = "X = (Y - shape) / sqrt(shape), Y ~ Gamma(shape, 1)"
        print(f"\n{name}: {args.pairs:,} independent pairs; variance = 1")
        print(f"  Theory: G(0) = 0, G'(0) = "
              f"{np.real(response):+.9f} {np.imag(response):+.9f}j")
        print(f"  Sample G(0): {intercept.real:+.6f} {intercept.imag:+.6f}j")
        print(f"  Sample slope, real: {slope.real:+.6f} +/- {1.96 * slope_se[0]:.6f} (95%)")
        print(f"  Sample slope, imag: {slope.imag:+.6f} +/- {1.96 * slope_se[1]:.6f} (95%)")
        print(f"  Derivative checks: sample {abs(empirical_fd - slope):.2e}, "
              f"theory {abs(theoretical_fd - response):.2e}")

        np.savetxt(
            args.output / f"{name.lower()}_curve.csv",
            np.column_stack((angles, means.real, means.imag, *standard_errors,
                             np.real(theoretical), np.imag(theoretical))),
            delimiter=",",
            header="theta,empirical_real,empirical_imag,se_real,se_imag,theoretical_real,theoretical_imag",
            comments="",
        )
        for row, component in enumerate((np.real, np.imag)):
            ax = axes[row, column]
            estimate, se = component(means), standard_errors[row]
            ax.fill_between(angles, estimate - 1.96 * se, estimate + 1.96 * se,
                            color="#147d92", alpha=0.16)
            ax.plot(angles, estimate, color="#147d92", lw=1.8, label="Sample mean")
            ax.plot(angles, component(theoretical), color="#17212b", lw=2,
                    label="Exact population mean")
            ax.plot(angles, component(response) * angles, color="#db6c36", lw=1.8,
                    ls="--", label="Population tangent at zero")
            ax.axvline(0, color="#bbc2c8", lw=0.8)
            ax.grid(alpha=0.18)
            label = "Gamma (shape=2)" if name == "Gamma" else name
            ax.set_title(f"{label} | {'real' if row == 0 else 'imaginary'} part")
            ax.set_xlabel(r"Rotation angle $\theta$ (radians)")
            ax.set_ylabel(r"Mean of $W_{1,2}$")
            ax.text(0.03, 0.05,
                    f"Theory slope: {component(response):+.6f}\n"
                    f"Sample slope: {component(slope):+.6f} "
                    f"+/- {1.96 * slope_se[row]:.6f} (95%)",
                    transform=ax.transAxes, fontsize=9,
                    bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.85})
            extent = max(extent, float(np.max(np.abs(estimate) + 1.96 * se)),
                         float(np.max(np.abs(theoretical))))

    # Identical axis scales make the Gaussian/non-Gaussian comparison fair.
    axes[0, 0].set_ylim(-1.15 * extent, 1.15 * extent)
    fig.suptitle("Two-frequency rotation detector", fontsize=19, y=0.98)
    fig.text(0.5, 0.932, f"s = 1, t = 2 | {args.pairs:,} independent pairs per law | "
             "all laws centered with variance 1", ha="center", fontsize=11)
    fig.legend(*axes[0, 0].get_legend_handles_labels(), loc="upper center",
               bbox_to_anchor=(0.5, 0.91), ncol=3, frameon=False)
    fig.text(0.5, 0.035,
             "Shading: pointwise 95% Monte Carlo intervals (not simultaneous bands).\n"
             "Same samples at every angle; the empirical zero-angle value is not forced to zero.",
             ha="center", fontsize=9, color="#475569")
    fig.subplots_adjust(top=0.81, bottom=0.14, hspace=0.30, wspace=0.18)
    plot_path = args.output / "fourier_rotation.png"
    fig.savefig(plot_path, dpi=180, facecolor="white")
    plt.close(fig)
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"\nPlot: {plot_path}")

    # Compare the full population response, distinct from its derivative at zero.
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharex=True)
    comparisons = [
        ("Real part", np.real, r"$\mathrm{Re}\,G(\theta)$"),
        ("Imaginary part", np.imag, r"$\mathrm{Im}\,G(\theta)$"),
        ("Modulus", np.abs, r"$|G(\theta)|$"),
        ("Phase (principal value)", lambda z: np.degrees(np.angle(z)), "Phase (degrees)"),
    ]
    for ax, (title, component, ylabel) in zip(axes.flat, comparisons):
        for name, color in (("Laplace", "#147d92"), ("Gamma", "#db6c36")):
            curve = population_curves[name]
            plotted = component(curve)
            if title.startswith("Phase"):
                # G(0) = 0: its phase is undefined, not zero.
                plotted = np.where(np.abs(curve) > 1e-12, plotted, np.nan)
            ax.plot(angles, plotted, lw=2, color=color, label=name)
        ax.set_title(title)
        ax.set_xlabel(r"Rotation angle $\theta$ (radians)")
        ax.set_ylabel(ylabel)
        ax.axvline(0, color="#bbc2c8", lw=0.8)
        ax.grid(alpha=0.2)
    axes[1, 1].set_yticks([-180, -90, 0, 90, 180])
    axes[1, 1].set_ylim(-190, 190)
    fig.suptitle("Laplace vs. centered Gamma: complex rotation response", fontsize=17, y=0.98)
    fig.text(0.5, 0.932, "Exact population curves | s = 1, t = 2 | variance = 1 | Gamma shape = 2",
             ha="center", fontsize=11)
    fig.legend(*axes[0, 0].get_legend_handles_labels(), loc="upper center",
               bbox_to_anchor=(0.5, 0.91), ncol=2, frameon=False)
    fig.text(0.5, 0.03,
             "Equal derivative moduli at zero do not imply equal moduli at finite angles.\n"
             "The phase of G(0) is undefined; positive and negative angles are plotted separately.",
             ha="center", fontsize=9, color="#475569")
    fig.subplots_adjust(top=0.81, bottom=0.14, hspace=0.32, wspace=0.24)
    comparison_path = args.output / "laplace_gamma_comparison.png"
    fig.savefig(comparison_path, dpi=180, facecolor="white")
    plt.close(fig)
    print(f"Comparison: {comparison_path}")


if __name__ == "__main__":
    main()
