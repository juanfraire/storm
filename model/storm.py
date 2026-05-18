#!/usr/bin/env python3
"""STORM command-line interface.

Stochastic Trading and Optimization under Regulation for the Argentine
Wholesale Electricity Market (MEM). One entry point for solving single
instances, running campaign phases, and regenerating paper figures.

Examples
--------
    # 1-day smoke test (hourly, two scenarios) — validates the install
    python storm.py solve --days 1 --delta-t 1.0 --scenarios 2

    # Default case (Case 3, STORM-CVaR base run, full year, 12 scenarios)
    python storm.py solve

    # Case 10 risk-neutral on a 91-day window
    python storm.py solve --case case_10 --days 91 --beta 0

    # Full STORM campaign with the FSA and TOP-penalty extensions
    python storm.py campaign all

    # Multi-seed bands on the headline baselines
    python storm.py campaign base baselines --seeds 2024 2025 2026 2027 2028

    # Regenerate paper figures from a saved campaign directory
    python storm.py plot --input output/campaign_365 --output output/figures

    # Print configuration / case metadata
    python storm.py info
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import time
from typing import Optional

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import config as cfg  # noqa: E402


# ---------------------------------------------------------------------------
# solve
# ---------------------------------------------------------------------------

def cmd_solve(args: argparse.Namespace) -> int:
    """Solve a single STORM instance with the given parameters."""
    import run_server_campaign as base

    rc = base.RunConfig(
        name=args.name or f"{args.case}_{args.days}d_{args.scenarios}s",
        active_case=args.case,
        num_days=args.days,
        num_scenarios=args.scenarios,
        delta_t=args.delta_t,
        cvar_beta=args.beta,
        gamma_pv=args.gamma_pv,
        gamma_bess=args.gamma_bess,
        contract_mater_price=args.mater_price,
        contract_mate_price=args.mate_price,
        contract_matp_price=args.matp_price,
        ppad_spot_price=args.ppad_price,
        solver_timeout=args.timeout,
        mip_gap=args.gap,
        spot_energy_mean_usd_per_mwh=args.spot_mean,
        contract_top_penalty_usd_per_mwh=args.top_penalty,
        random_seed=args.seed,
    )

    result = base.run_single(rc)

    print()
    print(f"  objective         {result.get('objective')}")
    print(f"  mip_gap           {result.get('mip_gap')}")
    print(f"  status            {result.get('status')}")
    print(f"  C_PV (kWp)        {result.get('C_PV')}")
    print(f"  C_BESS (kWh)      {result.get('C_BESS')}")
    print(f"  P_BESS (kW)       {result.get('P_BESS')}")
    print(f"  MATER (MWh/y)     {result.get('contract_MATER_mwh')}")
    print(f"  MATE  (MWh/y)     {result.get('contract_MATE_mwh')}")
    print(f"  MATP  (kW avg)    {result.get('contract_MATP_kw_avg')}")
    print(f"  E[OPEX] (kUSD/y)  {(result.get('expected_opex') or 0) / 1000:.2f}")
    print(f"  E[total] (kUSD/y) {(result.get('expected_total_cost') or 0) / 1000:.2f}")
    print(f"  CVaR_OPEX (kUSD/y){(result.get('cvar_opex') or 0) / 1000:.2f}")

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"\n  Result saved to {args.output}")

    return 0 if result.get("status") in (2, "computed") else 1


# ---------------------------------------------------------------------------
# campaign
# ---------------------------------------------------------------------------

def cmd_campaign(args: argparse.Namespace) -> int:
    """Run one or more campaign phases (delegates to run_server_campaign_365)."""
    import run_server_campaign_365 as runner

    if args.output_dir:
        runner.OUT = os.path.abspath(args.output_dir)
        # base.OUT is set inside _run_phases_once; we just need to override
        # the module default that downstream helpers reach for.

    runner.run_campaign(
        phases=args.phases,
        seed=args.seed,
        seeds=args.seeds,
        skip_existing=args.skip_existing,
        output_dir=args.output_dir,
    )
    return 0


# ---------------------------------------------------------------------------
# plot
# ---------------------------------------------------------------------------

def cmd_plot(args: argparse.Namespace) -> int:
    """Generate paper figures from saved campaign JSONs."""
    import plot_campaign

    formats = tuple(f.strip() for f in args.formats.split(",") if f.strip())
    plot_campaign.plot_all(
        input_dir=args.input,
        output_dir=args.output,
        width=args.width,
        formats=formats,
        include_envelopes=not args.no_envelopes,
        envelope_days=args.envelope_days,
        envelope_scenarios=args.envelope_scenarios,
        envelope_start_day=args.envelope_start_day,
    )
    return 0


# ---------------------------------------------------------------------------
# info
# ---------------------------------------------------------------------------

def cmd_info(args: argparse.Namespace) -> int:
    """Print the active configuration and case metadata."""
    print(f"STORM v0  (config: {cfg.__file__})")
    print()
    print(f"  Active case:        {cfg.ACTIVE_CASE}")
    print(f"  Δt:                 {cfg.DELTA_T} h")
    print(f"  Horizon T:          {cfg.T} intervals")
    print(f"  Num scenarios:      {cfg.NUM_SCENARIOS}")
    print(f"  Random seed:        {cfg.RANDOM_SEED}")
    print()
    print(f"  CVaR α:             {cfg.CVAR_ALPHA}")
    print(f"  CVaR β (default):   {cfg.CVAR_BETA}")
    print()
    print("  Contract prices (USD/MWh or USD/MWhrp):")
    for k, v in cfg.CONTRACT_PRICES.items():
        print(f"    {k:6s} {v}")
    print(f"  TOP penalty (USD/MWh):  {cfg.CONTRACT_TOP_PENALTY_USD_PER_MWH}")
    print()
    print("  Cases:")
    for name, meta in cfg.CASE_METADATA.items():
        print(f"    {name:8s}  {meta['name']}  peak={meta['contracted_power_kw']:.0f} kW")
    print()
    print("  CAPEX (overnight):")
    print(f"    γ_PV    {cfg.GAMMA_PV} USD/kWp")
    print(f"    γ_BESS  {cfg.GAMMA_BESS} USD/kWh")
    print(f"    Annualized via capital recovery factor "
          f"(rate {cfg.DISCOUNT_RATE}, PV {cfg.PV_LIFE_YEARS}y, BESS {cfg.BESS_LIFE_YEARS}y)")
    return 0


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="storm",
        description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Run `python storm.py <command> --help` for command-specific options.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True, metavar="command")

    # solve
    sp = sub.add_parser("solve", help="Solve a single STORM instance.")
    sp.add_argument("--case", choices=["case_3", "case_10"], default="case_3")
    sp.add_argument("--days", type=int, default=365, help="Horizon length in days.")
    sp.add_argument("--delta-t", type=float, default=0.25, help="Interval length in hours.")
    sp.add_argument("--scenarios", type=int, default=12)
    sp.add_argument("--beta", type=float, default=0.5, help="CVaR weight (0 = STORM-RN).")
    sp.add_argument("--seed", type=int, default=None, help="Override the scenario seed.")
    sp.add_argument("--gamma-pv", type=float, default=cfg.GAMMA_PV, help="PV CAPEX (USD/kWp).")
    sp.add_argument("--gamma-bess", type=float, default=cfg.GAMMA_BESS, help="BESS CAPEX (USD/kWh).")
    sp.add_argument("--mater-price", type=float, default=cfg.CONTRACT_PRICES["MATER"])
    sp.add_argument("--mate-price", type=float, default=cfg.CONTRACT_PRICES["MATE"])
    sp.add_argument("--matp-price", type=float, default=cfg.CONTRACT_PRICES["MATP"])
    sp.add_argument("--ppad-price", type=float, default=cfg.PPAD_SPOT_USD_PER_MWHRP)
    sp.add_argument("--spot-mean", type=float, default=None,
                    help="Mean spot energy price (USD/MWh). Overrides config default.")
    sp.add_argument("--top-penalty", type=float, default=None,
                    help="Take-or-pay penalty (USD/MWh) applied to MATER and MATE.")
    sp.add_argument("--timeout", type=int, default=cfg.SOLVER_TIMEOUT)
    sp.add_argument("--gap", type=float, default=cfg.MIP_GAP, help="MIP-gap target.")
    sp.add_argument("--name", default=None, help="Run name (used in printed log).")
    sp.add_argument("--output", default=None, help="Save the full result row as JSON to this path.")
    sp.set_defaults(func=cmd_solve)

    # campaign
    sc = sub.add_parser(
        "campaign",
        help="Run one or more campaign phases (smoke, base, cvar, bess, pv, "
             "mater, mate, ppad, cases, seasonal, baselines, fsa, top, paper, all).",
    )
    sc.add_argument("phases", nargs="+",
                    help='Phase names. "paper" expands to the 37-run sensitivity '
                         'suite; "all" adds FSA and TOP-penalty sweeps.')
    sc.add_argument("--seed", type=int, default=None,
                    help="Single seed override; outputs go to <out>/seed_<seed>/.")
    sc.add_argument("--seeds", type=int, nargs="+", default=None,
                    help="Run each phase once per seed.")
    sc.add_argument("--skip-existing", action="store_true",
                    help="Skip a phase if its JSON output already exists.")
    sc.add_argument("--output-dir", default=None,
                    help="Override the campaign output directory.")
    sc.set_defaults(func=cmd_campaign)

    # plot
    spl = sub.add_parser("plot", help="Generate paper figures from saved campaign JSONs.")
    spl.add_argument("--input", default=None,
                     help="Directory with the campaign JSON files (defaults to output/campaign).")
    spl.add_argument("--output", default=None, help="Directory for generated figures.")
    spl.add_argument("--width", choices=["single", "double"], default="single",
                     help="Width preset for sensitivity figures.")
    spl.add_argument("--formats", default="pdf,png",
                     help="Comma-separated list of output formats.")
    spl.add_argument("--no-envelopes", action="store_true",
                     help="Skip the scenario-uncertainty envelope figure.")
    spl.add_argument("--envelope-days", type=int, default=7)
    spl.add_argument("--envelope-scenarios", type=int, default=80)
    spl.add_argument("--envelope-start-day", type=int, default=0)
    spl.set_defaults(func=cmd_plot)

    # info
    si = sub.add_parser("info", help="Print the active configuration.")
    si.set_defaults(func=cmd_info)

    return parser


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    t0 = time.time()
    rc = args.func(args)
    dt = time.time() - t0
    if dt > 5:
        print(f"\n[storm] command finished in {dt:.1f}s")
    return rc


if __name__ == "__main__":
    sys.exit(main())
