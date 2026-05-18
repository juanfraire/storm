"""
Paper-ready plotting utilities for STORM campaign results.

The module reads saved JSON campaign sweeps and exports vector PDF figures
with IEEE-friendly dimensions. PNG previews are also written by default.
"""

import argparse
import json
import os
from collections import defaultdict
from contextlib import contextmanager

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


MODULE_DIR = os.path.dirname(__file__)
OUTPUT_DIR = os.path.join(MODULE_DIR, "output", "campaign")
PLOT_DIR = os.path.join(MODULE_DIR, "output", "figures")

IEEE_SINGLE_WIDTH = 3.5
IEEE_DOUBLE_WIDTH = 7.16
FIGURE_WIDTH_STRETCH = 1.25

COLORS = {
    "objective": "#1f2937",
    "capex": "#6b7280",
    "opex": "#374151",
    "pv": "#d97706",
    "bess": "#2563eb",
    "matp": "#059669",
    "mater": "#7c3aed",
    "mate": "#dc2626",
    "spot": "#0891b2",
    "case3": "#4f46e5",
    "case10": "#16a34a",
    "expected": "#1f2937",
    "cvar": "#b91c1c",
}

MARKERS = ["o", "s", "^", "D", "v", "P"]


def configure_style():
    """Apply compact IEEE-oriented Matplotlib defaults."""
    plt.rcParams.update({
        "figure.dpi": 150,
        "savefig.dpi": 450,
        "savefig.bbox": "tight",
        "font.family": "serif",
        "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
        "font.size": 8.0,
        "axes.titlesize": 8.5,
        "axes.labelsize": 8.0,
        "legend.fontsize": 7.0,
        "xtick.labelsize": 7.0,
        "ytick.labelsize": 7.0,
        "axes.linewidth": 0.65,
        "grid.linewidth": 0.35,
        "lines.linewidth": 1.45,
        "lines.markersize": 4.2,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })


def figure_size(width="single", ratio=0.72):
    """Return an IEEE single-column or double-column figure size."""
    base = IEEE_SINGLE_WIDTH if width == "single" else IEEE_DOUBLE_WIDTH
    return (base * FIGURE_WIDTH_STRETCH, base * ratio)


def load_results(name: str, input_dir: str = None) -> list:
    """Load a named JSON result file."""
    input_dir = input_dir or OUTPUT_DIR
    path = os.path.join(input_dir, f"{name}.json")
    if not os.path.exists(path):
        print(f"  Warning: {path} not found")
        return []
    with open(path) as f:
        return json.load(f)


def load_first(names, input_dir: str = None) -> list:
    """Load the first existing sweep from a list of candidate names."""
    input_dir = input_dir or OUTPUT_DIR
    for name in names:
        path = os.path.join(input_dir, f"{name}.json")
        if os.path.exists(path):
            return load_results(name, input_dir)
    print(f"  Warning: none of these sweeps found: {', '.join(names)}")
    return []


def result_value(row: dict, *keys, default=0.0):
    """Return the first non-empty value from a result row."""
    for key in keys:
        value = row.get(key)
        if value is not None:
            return value
    return default


def numeric_suffix(name: str, *prefixes: str) -> float:
    for prefix in prefixes:
        if name.startswith(prefix):
            return float(name.replace(prefix, ""))
    return float(name.rsplit("_", 1)[-1])


def annual_contract_gwh(row: dict, key: str) -> float:
    """Return annualized contract energy in GWh/year."""
    scale = result_value(row, "opex_scale_to_year", default=1.0) or 1.0
    return (result_value(row, key, default=0.0) * scale) / 1000.0


def objective_kusd(row: dict) -> float:
    return result_value(row, "objective", default=0.0) / 1000.0


def capex_kusd(row: dict) -> float:
    return result_value(row, "annualized_capex", default=0.0) / 1000.0


def opex_kusd(row: dict) -> float:
    return result_value(row, "expected_opex", default=0.0) / 1000.0


def expected_total_kusd(row: dict) -> float:
    return result_value(row, "expected_total_cost", "objective", default=0.0) / 1000.0


def cvar_total_kusd(row: dict) -> float:
    return result_value(row, "cvar_total_cost", default=result_value(row, "expected_total_cost", "objective", default=0.0)) / 1000.0


def pv_mwp(row: dict) -> float:
    return result_value(row, "C_PV", default=0.0) / 1000.0


def bess_mwh(row: dict) -> float:
    return result_value(row, "C_BESS", default=0.0) / 1000.0


def matp_mw(row: dict) -> float:
    return result_value(row, "contract_MATP_kw_avg", default=0.0) / 1000.0


def grouped_series(rows, x_getter, y_getter):
    """Return sorted x, mean, min, max, and counts for possible replicates."""
    buckets = defaultdict(list)
    for row in rows:
        x = float(x_getter(row))
        y = float(y_getter(row))
        if np.isfinite(x) and np.isfinite(y):
            buckets[x].append(y)
    xs = sorted(buckets)
    mean = np.array([np.mean(buckets[x]) for x in xs], dtype=float)
    ymin = np.array([np.min(buckets[x]) for x in xs], dtype=float)
    ymax = np.array([np.max(buckets[x]) for x in xs], dtype=float)
    count = np.array([len(buckets[x]) for x in xs], dtype=int)
    return np.array(xs, dtype=float), mean, ymin, ymax, count


def plot_grouped_line(ax, rows, x_getter, y_getter, label, color, marker="o",
                      linestyle="-", band=True, zorder=3):
    """Plot mean line and min/max envelope when repeated x values exist."""
    xs, mean, ymin, ymax, count = grouped_series(rows, x_getter, y_getter)
    if len(xs) == 0:
        return None
    line, = ax.plot(
        xs,
        mean,
        marker=marker,
        linestyle=linestyle,
        color=color,
        label=label,
        zorder=zorder,
    )
    if band and (np.any(count > 1) or np.any(np.abs(ymax - ymin) > 1e-9)):
        ax.fill_between(xs, ymin, ymax, color=color, alpha=0.16, linewidth=0, zorder=zorder - 1)
    return line


def prettify_axes(ax, xgrid=True):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(True, axis="y", alpha=0.35)
    if xgrid:
        ax.grid(True, axis="x", alpha=0.12)
    ax.tick_params(width=0.6, length=3)


def save_figure(fig, stem: str, output_dir: str = None, formats=("pdf", "png")):
    """Save a figure to one or more output formats."""
    output_dir = output_dir or PLOT_DIR
    os.makedirs(output_dir, exist_ok=True)
    for fmt in formats:
        path = os.path.join(output_dir, f"{stem}.{fmt}")
        kwargs = {"bbox_inches": "tight"}
        if fmt.lower() == "png":
            kwargs["dpi"] = 450
        fig.savefig(path, **kwargs)
    print(f"  Saved {stem} ({', '.join(formats)})")


def add_panel_label(ax, label):
    ax.text(
        0.0,
        1.02,
        label,
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontweight="bold",
    )


BASELINE_ORDER = [
    "gudi_full_service",
    "deterministic_ev",
    "stochastic_risk_neutral",
    "stochastic_cvar",
    "contracts_only",
    "der_only",
    "stochastic_no_degradation",
]

BASELINE_LABELS = {
    "gudi_full_service": "GUDI",
    "deterministic_ev": "Det. EV",
    "stochastic_risk_neutral": "Stoch.",
    "stochastic_cvar": "STORM",
    "contracts_only": "Contracts",
    "der_only": "DER",
    "stochastic_no_degradation": "No deg.",
}


def load_seed_baselines(input_dir: str = None) -> dict:
    """Return {seed: [baseline_rows]} for every ``seed_*/09_baselines.json``
    subdirectory under ``input_dir``, including the primary seed under
    ``input_dir/09_baselines.json`` if present.

    Used by :func:`plot_baseline_comparison` to overlay per-seed dispersion and
    compute statistics for the difference panel.
    """
    import glob
    input_dir = input_dir or OUTPUT_DIR
    seed_results: dict = {}
    primary = os.path.join(input_dir, "09_baselines.json")
    if os.path.exists(primary):
        with open(primary) as f:
            seed_results["primary"] = json.load(f)
    for seed_path in sorted(glob.glob(os.path.join(input_dir, "seed_*", "09_baselines.json"))):
        seed_name = os.path.basename(os.path.dirname(seed_path))  # e.g. "seed_2024"
        with open(seed_path) as f:
            seed_results[seed_name] = json.load(f)
    return seed_results


def _strategy_value(rows: list, strategy: str, getter) -> float:
    """Pick the row for ``strategy`` and apply ``getter``. Returns NaN if not found."""
    for r in rows:
        if r.get("strategy") == strategy:
            return float(getter(r))
    return float("nan")


def plot_baseline_comparison(results: list, output_dir: str = None, width="double",
                             formats=("pdf", "png"), seed_results: dict = None):
    """Plot baseline strategy comparison for the paper.

    When ``seed_results`` is provided as ``{seed_name: [rows]}``, per-seed dots
    are overlaid on the cost bars and a third panel shows the headline
    differences (CVaR expected-cost premium, OPEX-CVaR reduction, VSS) with
    error bars whose half-height is the across-seed standard deviation.
    """
    if not results:
        return

    order = {name: i for i, name in enumerate(BASELINE_ORDER)}
    results = sorted(results, key=lambda r: order.get(r.get("strategy", r.get("name", "")), 99))
    labels = [BASELINE_LABELS.get(r.get("strategy"), r.get("strategy_label", r.get("name", ""))) for r in results]
    strategies = [r.get("strategy") for r in results]
    x = np.arange(len(results))

    seed_rows = list((seed_results or {}).values())
    have_seeds = len(seed_rows) >= 2  # need >=2 seeds to draw bands

    if have_seeds:
        fig, axes = plt.subplots(
            1, 3, figsize=figure_size(width, 0.36),
            gridspec_kw={"width_ratios": [1.6, 1.4, 1.0]},
        )
    else:
        fig, axes = plt.subplots(1, 2, figsize=figure_size(width, 0.336))

    # --- Panel (a): cost bars + per-seed dots ---
    barw = 0.36
    axes[0].bar(x - barw / 2, [expected_total_kusd(r) for r in results], barw,
                color=COLORS["expected"], label="Expected", zorder=2)
    axes[0].bar(x + barw / 2, [cvar_total_kusd(r) for r in results], barw,
                color=COLORS["cvar"], label="CVaR$_{95\\%}$", zorder=2)
    if have_seeds:
        for strat, xi in zip(strategies, x):
            e_vals = [_strategy_value(rows, strat, expected_total_kusd) for rows in seed_rows]
            c_vals = [_strategy_value(rows, strat, cvar_total_kusd) for rows in seed_rows]
            e_vals = [v for v in e_vals if np.isfinite(v)]
            c_vals = [v for v in c_vals if np.isfinite(v)]
            if e_vals:
                axes[0].scatter([xi - barw / 2] * len(e_vals), e_vals,
                                s=4, color="black", alpha=0.55, zorder=4,
                                linewidths=0)
            if c_vals:
                axes[0].scatter([xi + barw / 2] * len(c_vals), c_vals,
                                s=4, color="black", alpha=0.55, zorder=4,
                                linewidths=0)
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(labels, rotation=25, ha="right")
    axes[0].set_ylabel("kUSD/y")
    axes[0].set_title("Baseline cost comparison")
    axes[0].legend(loc="upper right", frameon=False)
    prettify_axes(axes[0], xgrid=False)
    add_panel_label(axes[0], "(a)")

    # --- Panel (b): first-stage hedges ---
    width_bar = 0.23
    axes[1].bar(x - width_bar, [pv_mwp(r) for r in results], width_bar, color=COLORS["pv"], label="PV")
    axes[1].bar(x, [bess_mwh(r) for r in results], width_bar, color=COLORS["bess"], label="BESS")
    axes[1].bar(x + width_bar, [matp_mw(r) for r in results], width_bar, color=COLORS["matp"], label="MATP")
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(labels, rotation=25, ha="right")
    axes[1].set_ylabel("MWp / MWh / MW")
    axes[1].set_title("First-stage hedges")
    axes[1].legend(loc="upper right", frameon=False, ncol=3)
    prettify_axes(axes[1], xgrid=False)
    add_panel_label(axes[1], "(b)")

    # --- Panel (c): seed-band statistics for the three headline differences ---
    if have_seeds:
        def get_opex(rows, strat):
            return _strategy_value(rows, strat, lambda r: result_value(r, "expected_opex") / 1000.0)
        def get_cvar_opex(rows, strat):
            return _strategy_value(rows, strat, lambda r: result_value(r, "cvar_opex") / 1000.0)
        def get_etotal(rows, strat):
            return _strategy_value(rows, strat, expected_total_kusd)

        vss_vals       = [get_opex(rows, "deterministic_ev") - get_opex(rows, "stochastic_risk_neutral") for rows in seed_rows]
        cvar_prem_vals = [get_etotal(rows, "stochastic_cvar") - get_etotal(rows, "stochastic_risk_neutral") for rows in seed_rows]
        cvar_red_vals  = [get_cvar_opex(rows, "stochastic_risk_neutral") - get_cvar_opex(rows, "stochastic_cvar") for rows in seed_rows]

        diffs = [
            ("VSS", vss_vals, COLORS.get("objective", "#1f2937")),
            ("CVaR premium", cvar_prem_vals, COLORS["cvar"]),
            ("OPEX-CVaR red.", cvar_red_vals, COLORS["expected"]),
        ]
        diffs = [(lbl, [v for v in vals if np.isfinite(v)], c) for lbl, vals, c in diffs]

        labels_d = [d[0] for d in diffs]
        means_d  = np.array([float(np.mean(d[1])) for d in diffs])
        sds_d    = np.array([float(np.std(d[1], ddof=1)) if len(d[1]) >= 2 else 0.0 for d in diffs])
        colors_d = [d[2] for d in diffs]

        y = np.arange(len(diffs))
        axes[2].barh(y, means_d, xerr=sds_d, color=colors_d, edgecolor="black",
                     linewidth=0.4, capsize=2.5, error_kw={"elinewidth": 0.7, "capthick": 0.7})
        axes[2].axvline(0, color="black", linewidth=0.5, alpha=0.35, zorder=1)
        axes[2].set_yticks(y)
        axes[2].set_yticklabels(labels_d)
        axes[2].invert_yaxis()
        axes[2].set_xlabel("kUSD/y")
        axes[2].set_title(f"Seed bands (n={len(seed_rows)})")
        for yi, (mu, sd) in enumerate(zip(means_d, sds_d)):
            txt = f"{mu:.2f} ± {sd:.2f}" if sd > 0 else f"{mu:.2f}"
            ha = "left" if mu >= 0 else "right"
            xpos = mu + (sd + max(abs(means_d)) * 0.04) * (1 if mu >= 0 else -1)
            axes[2].annotate(txt, xy=(xpos, yi), va="center", ha=ha, fontsize=6.5)
        prettify_axes(axes[2], xgrid=True)
        add_panel_label(axes[2], "(c)")

    fig.tight_layout(pad=0.6)
    save_figure(fig, f"paper_baseline_comparison_{width}", output_dir, formats)
    plt.close(fig)


def plot_cvar_sensitivity(results: list, output_dir: str = None, width="single",
                          formats=("pdf", "png")):
    """Plot risk weight sensitivity."""
    if not results:
        return
    results = sorted(results, key=lambda r: result_value(r, "cvar_beta", default=numeric_suffix(r["name"])))
    x_get = lambda r: result_value(r, "cvar_beta", default=numeric_suffix(r["name"], "cvar_beta_", "cvar_"))

    fig, axes = plt.subplots(3, 1, figsize=figure_size(width, 1.10), sharex=True)

    plot_grouped_line(axes[0], results, x_get, objective_kusd, "Objective", COLORS["objective"], "o")
    axes[0].set_ylabel("kUSD/y")
    axes[0].set_title("Risk aversion sensitivity")
    prettify_axes(axes[0])
    add_panel_label(axes[0], "(a)")

    plot_grouped_line(axes[1], results, x_get, pv_mwp, "PV", COLORS["pv"], "s")
    plot_grouped_line(axes[1], results, x_get, bess_mwh, "BESS", COLORS["bess"], "^")
    axes[1].set_ylabel("MWp / MWh")
    axes[1].legend(loc="upper left", frameon=False, ncol=2)
    prettify_axes(axes[1])
    add_panel_label(axes[1], "(b)")

    plot_grouped_line(axes[2], results, x_get, matp_mw, "MATP", COLORS["matp"], "D")
    plot_grouped_line(
        axes[2],
        results,
        x_get,
        lambda r: annual_contract_gwh(r, "contract_MATE_mwh"),
        "MATE",
        COLORS["mate"],
        "o",
    )
    plot_grouped_line(
        axes[2],
        results,
        x_get,
        lambda r: annual_contract_gwh(r, "contract_MATER_mwh"),
        "MATER",
        COLORS["mater"],
        "s",
    )
    axes[2].set_ylabel("MW / GWh-y")
    axes[2].set_xlabel("CVaR weight $\\beta$")
    axes[2].legend(loc="best", frameon=False, ncol=3)
    prettify_axes(axes[2])
    add_panel_label(axes[2], "(c)")

    fig.tight_layout(pad=0.6)
    save_figure(fig, f"paper_cvar_sensitivity_{width}", output_dir, formats)
    plt.close(fig)


def plot_bess_cost_sensitivity(results: list, output_dir: str = None, width="single",
                               formats=("pdf", "png")):
    """Plot BESS capital-cost sensitivity."""
    if not results:
        return
    results = sorted(results, key=lambda r: result_value(r, "gamma_bess", default=numeric_suffix(r["name"])))
    x_get = lambda r: result_value(r, "gamma_bess", default=numeric_suffix(r["name"], "bess_cost_", "bess_"))

    fig, axes = plt.subplots(2, 1, figsize=figure_size(width, 0.82), sharex=True)

    plot_grouped_line(axes[0], results, x_get, objective_kusd, "Objective", COLORS["objective"], "o")
    axes[0].set_ylabel("kUSD/y")
    axes[0].set_title("BESS cost threshold")
    prettify_axes(axes[0])
    add_panel_label(axes[0], "(a)")

    plot_grouped_line(axes[1], results, x_get, bess_mwh, "BESS", COLORS["bess"], "^")
    plot_grouped_line(axes[1], results, x_get, pv_mwp, "PV", COLORS["pv"], "s")
    plot_grouped_line(axes[1], results, x_get, matp_mw, "MATP", COLORS["matp"], "D")
    axes[1].set_xlabel("BESS cost (USD/kWh)")
    axes[1].set_ylabel("MWp / MWh / MW")
    axes[1].legend(loc="best", frameon=False, ncol=3)
    prettify_axes(axes[1])
    add_panel_label(axes[1], "(b)")

    fig.tight_layout(pad=0.6)
    save_figure(fig, f"paper_bess_cost_sensitivity_{width}", output_dir, formats)
    plt.close(fig)


def plot_pv_cost_sensitivity(results: list, output_dir: str = None, width="single",
                             formats=("pdf", "png")):
    """Plot PV capital-cost sensitivity."""
    if not results:
        return
    results = sorted(results, key=lambda r: result_value(r, "gamma_pv", default=numeric_suffix(r["name"])))
    x_get = lambda r: result_value(r, "gamma_pv", default=numeric_suffix(r["name"], "pv_cost_"))

    fig, axes = plt.subplots(2, 1, figsize=figure_size(width, 0.82), sharex=True)

    plot_grouped_line(axes[0], results, x_get, objective_kusd, "Objective", COLORS["objective"], "o")
    axes[0].set_ylabel("kUSD/y")
    axes[0].set_title("PV cost sensitivity")
    prettify_axes(axes[0])
    add_panel_label(axes[0], "(a)")

    plot_grouped_line(axes[1], results, x_get, pv_mwp, "PV", COLORS["pv"], "s")
    plot_grouped_line(axes[1], results, x_get, bess_mwh, "BESS", COLORS["bess"], "^")
    plot_grouped_line(axes[1], results, x_get, matp_mw, "MATP", COLORS["matp"], "D")
    axes[1].set_xlabel("PV cost (USD/kWp)")
    axes[1].set_ylabel("MWp / MWh / MW")
    axes[1].legend(loc="best", frameon=False, ncol=3)
    prettify_axes(axes[1])
    add_panel_label(axes[1], "(b)")

    fig.tight_layout(pad=0.6)
    save_figure(fig, f"paper_pv_cost_sensitivity_{width}", output_dir, formats)
    plt.close(fig)


def plot_contract_switching(mater_results: list, mate_results: list, output_dir: str = None,
                            width="double", formats=("pdf", "png")):
    """Plot MATER/MATE price substitution."""
    if not mater_results and not mate_results:
        return

    fig, axes = plt.subplots(1, 2, figsize=figure_size(width, 0.336), sharey=True)

    if mater_results:
        mater_results = sorted(
            mater_results,
            key=lambda r: result_value(r, "contract_mater_price", default=numeric_suffix(r["name"])),
        )
        x_get = lambda r: result_value(
            r,
            "contract_mater_price",
            default=numeric_suffix(r["name"], "mater_price_", "mater_"),
        )
        _plot_contract_panel(axes[0], mater_results, x_get, "MATER price (USD/MWh)")
        add_panel_label(axes[0], "(a)")

    if mate_results:
        mate_results = sorted(
            mate_results,
            key=lambda r: result_value(r, "contract_mate_price", default=numeric_suffix(r["name"])),
        )
        x_get = lambda r: result_value(
            r,
            "contract_mate_price",
            default=numeric_suffix(r["name"], "mate_price_", "mat_price_"),
        )
        _plot_contract_panel(axes[1], mate_results, x_get, "MATE price (USD/MWh)")
        add_panel_label(axes[1], "(b)")

    axes[0].set_ylabel("Annual contract energy (GWh/y)")
    handles, labels = axes[1].get_legend_handles_labels()
    if handles:
        fig.legend(handles, labels, loc="upper center", frameon=False, ncol=3, bbox_to_anchor=(0.5, 1.03))
    fig.tight_layout(pad=0.6)
    save_figure(fig, f"paper_contract_switching_{width}", output_dir, formats)
    plt.close(fig)


def _plot_contract_panel(ax, rows, x_get, xlabel):
    plot_grouped_line(
        ax,
        rows,
        x_get,
        lambda r: annual_contract_gwh(r, "contract_MATER_mwh"),
        "MATER",
        COLORS["mater"],
        "s",
    )
    plot_grouped_line(
        ax,
        rows,
        x_get,
        lambda r: annual_contract_gwh(r, "contract_MATE_mwh"),
        "MATE",
        COLORS["mate"],
        "o",
    )
    ax.set_xlabel(xlabel)
    prettify_axes(ax)


def plot_ppad_sensitivity(results: list, output_dir: str = None, width="single",
                          formats=("pdf", "png")):
    """Plot PPAD residual spot-price sensitivity."""
    if not results:
        return
    results = sorted(results, key=lambda r: result_value(r, "ppad_spot_price", default=numeric_suffix(r["name"])))
    x_get = lambda r: result_value(r, "ppad_spot_price", default=numeric_suffix(r["name"], "ppad_spot_"))

    fig, axes = plt.subplots(2, 1, figsize=figure_size(width, 0.82), sharex=True)

    plot_grouped_line(axes[0], results, x_get, objective_kusd, "Objective", COLORS["objective"], "o")
    axes[0].set_ylabel("kUSD/y")
    axes[0].set_title("PPAD hedge activation")
    prettify_axes(axes[0])
    add_panel_label(axes[0], "(a)")

    plot_grouped_line(axes[1], results, x_get, matp_mw, "MATP", COLORS["matp"], "D")
    plot_grouped_line(axes[1], results, x_get, bess_mwh, "BESS", COLORS["bess"], "^")
    axes[1].set_xlabel("Residual PPAD price (USD/MWhrp)")
    axes[1].set_ylabel("MW / MWh")
    axes[1].legend(loc="best", frameon=False, ncol=2)
    prettify_axes(axes[1])
    add_panel_label(axes[1], "(b)")

    fig.tight_layout(pad=0.6)
    save_figure(fig, f"paper_ppad_sensitivity_{width}", output_dir, formats)
    plt.close(fig)


def plot_case_and_seasonal(case_results: list, seasonal_results: list, output_dir: str = None,
                           width="double", formats=("pdf", "png")):
    """Plot case comparison and seasonal-window sensitivities."""
    if not case_results and not seasonal_results:
        return

    fig, axes = plt.subplots(1, 2, figsize=figure_size(width, 0.336))

    if case_results:
        case_results = sorted(case_results, key=lambda r: r.get("active_case", r.get("name", "")))
        labels = [r.get("active_case", r.get("name", "")).replace("_", " ") for r in case_results]
        x = np.arange(len(labels))
        width_bar = 0.23
        axes[0].bar(x - width_bar, [pv_mwp(r) for r in case_results], width_bar, color=COLORS["pv"], label="PV")
        axes[0].bar(x, [bess_mwh(r) for r in case_results], width_bar, color=COLORS["bess"], label="BESS")
        axes[0].bar(x + width_bar, [matp_mw(r) for r in case_results], width_bar, color=COLORS["matp"], label="MATP")
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(labels)
        axes[0].set_ylabel("MWp / MWh / MW")
        axes[0].set_title("Case scaling")
        axes[0].legend(loc="upper right", frameon=False)
        prettify_axes(axes[0], xgrid=False)
        add_panel_label(axes[0], "(a)")

    if seasonal_results:
        order = ["summer", "fall", "winter", "spring"]
        seasonal_results = sorted(
            seasonal_results,
            key=lambda r: order.index(r["name"].split("_")[0]) if r["name"].split("_")[0] in order else 99,
        )
        labels = [r["name"].split("_")[0].title() for r in seasonal_results]
        x = np.arange(len(labels))
        axes[1].plot(x, [pv_mwp(r) for r in seasonal_results], marker="s", color=COLORS["pv"], label="PV")
        axes[1].plot(x, [bess_mwh(r) for r in seasonal_results], marker="^", color=COLORS["bess"], label="BESS")
        axes[1].plot(x, [matp_mw(r) for r in seasonal_results], marker="D", color=COLORS["matp"], label="MATP")
        axes[1].set_xticks(x)
        axes[1].set_xticklabels(labels)
        axes[1].set_ylabel("MWp / MWh / MW")
        axes[1].set_title("Seasonal windows")
        axes[1].legend(loc="upper right", frameon=False)
        prettify_axes(axes[1], xgrid=False)
        add_panel_label(axes[1], "(b)")

    fig.tight_layout(pad=0.6)
    save_figure(fig, f"paper_case_seasonal_{width}", output_dir, formats)
    plt.close(fig)


@contextmanager
def temporary_config(**updates):
    """Temporarily patch config values for scenario-envelope plots."""
    import config as cfg

    old = {key: getattr(cfg, key) for key in updates}
    try:
        for key, value in updates.items():
            setattr(cfg, key, value)
        yield cfg
    finally:
        for key, value in old.items():
            setattr(cfg, key, value)


def plot_scenario_envelopes(output_dir: str = None, width="double",
                            formats=("pdf", "png"), case="case_3",
                            days=7, scenarios=80, start_day=0):
    """Plot uncertainty envelopes for demand, spot price, and PV yield."""
    try:
        import config as cfg
        from scenario_gen import generate_scenarios
    except Exception as exc:
        print(f"  Warning: scenario envelope skipped: {exc}")
        return

    delta_t = cfg.DATA_DELTA_T
    horizon = days * int(round(24.0 / delta_t))
    start_interval = start_day * int(round(24.0 / delta_t))
    with temporary_config(DELTA_T=delta_t, T=horizon, NUM_SCENARIOS=scenarios):
        data = generate_scenarios(case=case, num_scenarios=scenarios, horizon=horizon, start_interval=start_interval)

    hours = np.arange(horizon) * delta_t / 24.0
    demand_kw = data["demand"] / delta_t
    spot = data["spot_price"]
    pv_factor = data["solar_yield"] / delta_t

    fig, axes = plt.subplots(3, 1, figsize=figure_size(width, 0.434), sharex=True)
    _plot_envelope(axes[0], hours, demand_kw, "Demand", "kW", COLORS["objective"])
    _plot_envelope(axes[1], hours, spot, "Spot price", "USD/MWh", COLORS["spot"])
    _plot_envelope(axes[2], hours, pv_factor, "PV yield", "kW/kWp", COLORS["pv"])
    axes[0].legend(loc="upper right", frameon=False, ncol=3)
    axes[2].set_xlabel("Day of representative week" if days == 7 else "Day of modeled horizon")
    for ax, label in zip(axes, ["(a)", "(b)", "(c)"]):
        prettify_axes(ax)
        add_panel_label(ax, label)
    fig.tight_layout(pad=0.6)
    save_figure(fig, f"paper_scenario_envelopes_{width}", output_dir, formats)
    plt.close(fig)


def _plot_envelope(ax, x, matrix, title, ylabel, color):
    p10, p50, p90 = np.percentile(matrix, [10, 50, 90], axis=0)
    ymin = np.min(matrix, axis=0)
    ymax = np.max(matrix, axis=0)
    ax.fill_between(x, ymin, ymax, color=color, alpha=0.08, linewidth=0, label="min-max")
    ax.fill_between(x, p10, p90, color=color, alpha=0.20, linewidth=0, label="P10-P90")
    ax.plot(x, p50, color=color, linewidth=1.15, label="median")
    ax.set_title(title)
    ax.set_ylabel(ylabel)


def plot_all(input_dir: str = None, output_dir: str = None, width="single",
             formats=("pdf", "png"), include_envelopes=True,
             envelope_days=7, envelope_scenarios=80, envelope_start_day=0):
    """Generate paper figures from available campaign data."""
    configure_style()
    input_dir = input_dir or OUTPUT_DIR
    output_dir = output_dir or PLOT_DIR
    os.makedirs(output_dir, exist_ok=True)

    print("Generating paper-ready campaign figures...")
    seed_baselines = load_seed_baselines(input_dir)
    if len(seed_baselines) >= 2:
        print(f"  Loaded {len(seed_baselines)} baseline seed(s): {sorted(seed_baselines)}")
    plot_baseline_comparison(
        load_first(["09_baselines", "baselines"], input_dir),
        output_dir, "double", formats,
        seed_results=seed_baselines if len(seed_baselines) >= 2 else None,
    )
    plot_cvar_sensitivity(load_first(["01_cvar_beta", "cvar_beta"], input_dir), output_dir, width, formats)
    plot_bess_cost_sensitivity(load_first(["02_bess_cost", "bess_cost"], input_dir), output_dir, width, formats)
    plot_pv_cost_sensitivity(load_first(["03_pv_cost", "pv_cost"], input_dir), output_dir, width, formats)
    plot_contract_switching(
        load_first(["04_mater_price", "03_mater_price", "mater_price"], input_dir),
        load_first(["05_mate_price", "mate_price", "mat_price"], input_dir),
        output_dir,
        "double",
        formats,
    )
    plot_ppad_sensitivity(load_first(["06_ppad_spot", "05_ppad_spot", "ppad_spot"], input_dir), output_dir, width, formats)
    plot_case_and_seasonal(
        load_first(["07_case_comparison", "06_case_comparison", "case_comparison"], input_dir),
        load_first(["08_seasonal_windows", "representative_weeks"], input_dir),
        output_dir,
        "double",
        formats,
    )
    if include_envelopes:
        plot_scenario_envelopes(
            output_dir,
            "double",
            formats,
            days=envelope_days,
            scenarios=envelope_scenarios,
            start_day=envelope_start_day,
        )
    print(f"All figures saved to {output_dir}")


def parse_args():
    parser = argparse.ArgumentParser(description="Generate STORM paper figures.")
    parser.add_argument("--input", default=OUTPUT_DIR, help="Directory containing campaign JSON files.")
    parser.add_argument("--output", default=PLOT_DIR, help="Directory for generated figures.")
    parser.add_argument("--width", choices=["single", "double"], default="single", help="Width for sensitivity figures.")
    parser.add_argument("--formats", default="pdf,png", help="Comma-separated output formats.")
    parser.add_argument("--no-envelopes", action="store_true", help="Skip scenario uncertainty envelope figure.")
    parser.add_argument("--envelope-days", type=int, default=7, help="Days to include in the scenario-envelope figure.")
    parser.add_argument("--envelope-scenarios", type=int, default=80, help="Scenarios to draw for the scenario-envelope figure.")
    parser.add_argument("--envelope-start-day", type=int, default=0, help="Start day for the scenario-envelope figure.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    fmts = tuple(fmt.strip() for fmt in args.formats.split(",") if fmt.strip())
    plot_all(
        args.input,
        args.output,
        args.width,
        fmts,
        include_envelopes=not args.no_envelopes,
        envelope_days=args.envelope_days,
        envelope_scenarios=args.envelope_scenarios,
        envelope_start_day=args.envelope_start_day,
    )
