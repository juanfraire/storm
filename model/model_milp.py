"""
Gurobi MILP model for STORM.

This implementation mirrors the revised paper formulation:
- First stage: PV, BESS, monthly MATER/MATE energy, monthly MATP/PPAD power.
- Second stage: spot energy, contract allocation, PV self-consumption, BESS,
  demand response, and residual PPAD exposure per scenario.
- Objective: annualized CAPEX + expected OPEX + CVaR.
"""

from typing import Dict, Iterable, List, Optional

import numpy as np
import gurobipy as gp
from gurobipy import GRB

import config as cfg
from scenario_gen import generate_scenarios


class StochasticProcurementMILP:
    """Two-stage stochastic MILP for MEM procurement and DER sizing."""

    def __init__(
        self,
        scenarios: Optional[Dict[str, np.ndarray]] = None,
        fixed_first_stage: Optional[Dict] = None,
        disabled_assets: Optional[Iterable[str]] = None,
        model_name: str = "STORM",
    ):
        self.scenarios = scenarios if scenarios is not None else generate_scenarios()
        self.S = int(self.scenarios["demand"].shape[0])
        self.T = int(self.scenarios["demand"].shape[1])
        self.month_boundaries = _month_boundaries_for_horizon(self.T)
        self.num_months = len(self.month_boundaries) - 1
        self.horizon_hours = max(self.T * cfg.DELTA_T, 1e-9)
        self.opex_scale = (
            cfg.YEAR_HOURS / self.horizon_hours
            if cfg.SCALE_OPEX_TO_YEAR else 1.0
        )

        self.model: Optional[gp.Model] = None
        self.first_stage_vars: Dict = {}
        self.second_stage_vars: Dict = {}
        self.cvar_vars: Dict = {}
        self.opex_expr: Dict[int, gp.LinExpr] = {}
        self.capex_expr: Optional[gp.LinExpr] = None
        self.fixed_first_stage = fixed_first_stage or {}
        self.disabled_assets = {str(a).lower() for a in (disabled_assets or [])}
        self.model_name = model_name

    def build(self) -> gp.Model:
        """Build the MILP."""
        m = gp.Model(self.model_name)
        m.Params.TimeLimit = cfg.SOLVER_TIMEOUT
        m.Params.MIPGap = cfg.MIP_GAP
        m.Params.Threads = cfg.THREADS
        m.Params.OutputFlag = 1 if cfg.SOLVER_OUTPUT else 0

        demand = _scenario_array(self.scenarios, "demand", "demand_kwh")
        spot_price = _scenario_array(self.scenarios, "spot_price", "spot_price_usd_per_mwh")
        grid_adder = _scenario_array(self.scenarios, "grid_adder", "grid_adder_usd_per_mwh")
        solar_yield = _scenario_array(self.scenarios, "solar_yield", "solar_yield_kwh_per_kwp", "solar_ghi")

        # =========================================================
        # FIRST-STAGE VARIABLES
        # =========================================================
        C_pv = m.addVar(lb=0, ub=cfg.MAX_PV_KWP, name="C_PV")
        C_bess = m.addVar(lb=0, ub=cfg.MAX_BESS_KWH, name="C_BESS")
        P_bess = m.addVar(lb=0, ub=cfg.MAX_BESS_KW, name="P_BESS")
        m.addConstr(P_bess <= cfg.BESS_MAX_C_RATE * C_bess, name="bess_c_rate")

        q_energy = {}
        for k in cfg.ENERGY_CONTRACT_TYPES:
            q_energy[k] = {}
            for m_idx in range(self.num_months):
                hours = _month_hours(self.month_boundaries, m_idx)
                ub = cfg.CONTRACT_MAX_KW[k] * hours
                q_energy[k][m_idx] = m.addVar(lb=0, ub=ub, name=f"Q_{k}_m{m_idx}")

        r_matp = {}
        for m_idx in range(self.num_months):
            r_matp[m_idx] = m.addVar(lb=0, ub=cfg.MATP_MAX_KW, name=f"R_MATP_m{m_idx}")

        # Legacy aggregate contract variables for old runner/plot code. Energy
        # contracts are exposed as average kW over the modeled horizon; MATP is
        # exposed as average monthly kW.
        horizon_hours = max(self.T * cfg.DELTA_T, 1e-9)
        monthly_avg = 1.0 / max(self.num_months, 1)
        contract_legacy = {
            "MATER": _MonthlyVarProxy(q_energy["MATER"], scale=1.0 / horizon_hours),
            "MATE": _MonthlyVarProxy(q_energy["MATE"], scale=1.0 / horizon_hours),
            "MAT": _MonthlyVarProxy(q_energy["MATE"], scale=1.0 / horizon_hours),
            "MATP": _MonthlyVarProxy(r_matp, scale=monthly_avg),
        }

        self.first_stage_vars = {
            "C_PV": C_pv,
            "C_BESS": C_bess,
            "P_BESS": P_bess,
            "Q_energy": q_energy,
            "R_MATP": r_matp,
            "contract": contract_legacy,
        }
        self._apply_first_stage_strategy_constraints(m, C_pv, C_bess, P_bess, q_energy, r_matp)

        # =========================================================
        # SECOND-STAGE VARIABLES
        # =========================================================
        e_spot = {}
        e_con = {}
        dev_under = {}
        e_grid = {}
        e_pv = {}
        e_ch = {}
        e_dis = {}
        e_bess = {}
        d_red = {}
        phi_deg = {}
        r_ppad = {}
        r_spot_p = {}
        y_ch = {}
        v_dr = {}

        for s in range(self.S):
            e_spot[s] = m.addVars(self.T, lb=0, name=f"e_spot_s{s}")
            e_grid[s] = m.addVars(self.T, lb=0, name=f"e_grid_s{s}")
            e_pv[s] = m.addVars(self.T, lb=0, name=f"e_pv_s{s}")
            e_ch[s] = m.addVars(self.T, lb=0, name=f"e_ch_s{s}")
            e_dis[s] = m.addVars(self.T, lb=0, name=f"e_dis_s{s}")
            e_bess[s] = m.addVars(self.T, lb=0, name=f"E_bess_s{s}")
            d_red[s] = m.addVars(self.T, lb=0, name=f"d_red_s{s}")
            phi_deg[s] = m.addVars(self.T, lb=0, name=f"phi_deg_s{s}")
            y_ch[s] = (
                m.addVars(self.T, vtype=GRB.BINARY, name=f"y_ch_s{s}")
                if cfg.USE_BESS_BINARY else None
            )
            v_dr[s] = (
                m.addVars(self.T, vtype=GRB.BINARY, name=f"v_dr_s{s}")
                if cfg.USE_DR_EVENT_BINARY else None
            )

            e_con[s] = {}
            dev_under[s] = {}
            for k in cfg.ENERGY_CONTRACT_TYPES:
                e_con[s][k] = m.addVars(self.T, lb=0, name=f"e_con_{k}_s{s}")
                dev_under[s][k] = m.addVars(self.num_months, lb=0, name=f"dev_under_{k}_s{s}")

            r_ppad[s] = {}
            r_spot_p[s] = {}
            for m_idx in range(self.num_months):
                r_ppad[s][m_idx] = m.addVar(lb=0, name=f"r_ppad_s{s}_m{m_idx}")
                r_spot_p[s][m_idx] = m.addVar(lb=0, name=f"r_spotP_s{s}_m{m_idx}")

        self.second_stage_vars = {
            "e_spot": e_spot,
            "e_con": e_con,
            "dev_under": dev_under,
            "e_grid": e_grid,
            "e_pv": e_pv,
            "e_ch": e_ch,
            "e_dis": e_dis,
            "E_bess": e_bess,
            "d_red": d_red,
            "phi_deg": phi_deg,
            "r_ppad": r_ppad,
            "r_spotP": r_spot_p,
            "y": y_ch,
            "v_dr": v_dr,
        }

        # =========================================================
        # OBJECTIVE
        # =========================================================
        annual_pv = cfg.PV_CRF * cfg.GAMMA_PV
        annual_bess_kwh = cfg.BESS_CRF * cfg.GAMMA_BESS
        annual_bess_kw = cfg.BESS_CRF * cfg.GAMMA_P_BESS

        capex = annual_pv * C_pv + annual_bess_kwh * C_bess + annual_bess_kw * P_bess
        self.capex_expr = capex

        eta = m.addVar(lb=-GRB.INFINITY, name="CVaR_eta")
        zeta = m.addVars(self.S, lb=0, name="CVaR_zeta")
        self.cvar_vars = {"eta": eta, "zeta": zeta}

        opex_sum = gp.LinExpr()
        self.opex_expr = {}
        for s in range(self.S):
            opex_s = self._scenario_opex_expr(
                s, spot_price, grid_adder, q_energy, r_matp,
                e_spot, e_grid, e_dis, d_red, phi_deg, r_spot_p, dev_under,
            )
            opex_s = self.opex_scale * opex_s
            self.opex_expr[s] = opex_s
            opex_sum += opex_s

        expected_opex = opex_sum / self.S
        cvar = eta + (1.0 / ((1.0 - cfg.CVAR_ALPHA) * self.S)) * gp.quicksum(zeta[s] for s in range(self.S))
        m.setObjective(capex + expected_opex + cfg.CVAR_BETA * cvar, GRB.MINIMIZE)

        # =========================================================
        # CONSTRAINTS
        # =========================================================
        for s in range(self.S):
            for t in range(self.T):
                m.addConstr(
                    e_grid[s][t]
                    == e_spot[s][t] + gp.quicksum(e_con[s][k][t] for k in cfg.ENERGY_CONTRACT_TYPES),
                    name=f"grid_def_s{s}_t{t}",
                )

                m.addConstr(
                    e_grid[s][t] + e_pv[s][t] + e_dis[s][t] + d_red[s][t]
                    == demand[s, t] + e_ch[s][t],
                    name=f"balance_s{s}_t{t}",
                )

                m.addConstr(
                    e_pv[s][t] <= cfg.ETA_PV * solar_yield[s, t] * C_pv,
                    name=f"pv_limit_s{s}_t{t}",
                )

                if t == 0:
                    m.addConstr(
                        e_bess[s][t]
                        == cfg.SOC_INIT * C_bess + cfg.ETA_CH * e_ch[s][t] - e_dis[s][t] / cfg.ETA_DIS,
                        name=f"bess_init_s{s}",
                    )
                else:
                    m.addConstr(
                        e_bess[s][t]
                        == e_bess[s][t - 1] + cfg.ETA_CH * e_ch[s][t] - e_dis[s][t] / cfg.ETA_DIS,
                        name=f"bess_dyn_s{s}_t{t}",
                    )

                m.addConstr(e_bess[s][t] >= cfg.SOC_MIN * C_bess, name=f"soc_min_s{s}_t{t}")
                m.addConstr(e_bess[s][t] <= cfg.SOC_MAX * C_bess, name=f"soc_max_s{s}_t{t}")

                m.addConstr(e_ch[s][t] <= P_bess * cfg.DELTA_T, name=f"ch_power_s{s}_t{t}")
                m.addConstr(e_dis[s][t] <= P_bess * cfg.DELTA_T, name=f"dis_power_s{s}_t{t}")
                if cfg.USE_BESS_BINARY:
                    m.addConstr(e_ch[s][t] <= y_ch[s][t] * cfg.MAX_BESS_KW * cfg.DELTA_T, name=f"ch_mode_s{s}_t{t}")
                    m.addConstr(
                        e_dis[s][t] <= (1 - y_ch[s][t]) * cfg.MAX_BESS_KW * cfg.DELTA_T,
                        name=f"dis_mode_s{s}_t{t}",
                    )

                m.addConstr(d_red[s][t] <= cfg.DR_MAX_FRACTION * demand[s, t], name=f"dr_frac_s{s}_t{t}")
                if cfg.USE_DR_EVENT_BINARY:
                    m.addConstr(
                        d_red[s][t] <= cfg.DR_MAX_POWER_KW * cfg.DELTA_T * v_dr[s][t],
                        name=f"dr_event_s{s}_t{t}",
                    )

                # Linear degradation proxy: throughput plus SOC-window guardrails.
                # SOC bounds enforce the main operating window; phi keeps the
                # degradation cost explicit in result accounting.
                m.addConstr(phi_deg[s][t] >= e_dis[s][t], name=f"deg_proxy_s{s}_t{t}")

            # No free terminal depletion of installed storage.
            if self.T > 0:
                m.addConstr(e_bess[s][self.T - 1] >= cfg.SOC_INIT * C_bess, name=f"bess_terminal_s{s}")

            if cfg.USE_DR_EVENT_BINARY:
                max_intervals = int(round(cfg.DR_MAX_HOURS_PER_YEAR / cfg.DELTA_T))
                m.addConstr(gp.quicksum(v_dr[s][t] for t in range(self.T)) <= max_intervals, name=f"dr_annual_cap_s{s}")

            for m_idx in range(self.num_months):
                start, end = self.month_boundaries[m_idx], self.month_boundaries[m_idx + 1]

                for k in cfg.ENERGY_CONTRACT_TYPES:
                    allocated = gp.quicksum(e_con[s][k][t] for t in range(start, end))
                    m.addConstr(
                        allocated <= q_energy[k][m_idx],
                        name=f"contract_cover_{k}_s{s}_m{m_idx}",
                    )
                    m.addConstr(
                        allocated + dev_under[s][k][m_idx] >= q_energy[k][m_idx],
                        name=f"contract_top_{k}_s{s}_m{m_idx}",
                    )

                peak_intervals = _ppad_peak_intervals(start, end)
                if not peak_intervals:
                    peak_intervals = list(range(start, end))

                for t in peak_intervals:
                    m.addConstr(
                        r_ppad[s][m_idx] >= e_grid[s][t] / cfg.DELTA_T,
                        name=f"ppad_req_s{s}_m{m_idx}_t{t}",
                    )

                m.addConstr(
                    r_spot_p[s][m_idx] >= r_ppad[s][m_idx] - r_matp[m_idx],
                    name=f"ppad_residual_s{s}_m{m_idx}",
                )

            m.addConstr(self.opex_expr[s] - eta <= zeta[s], name=f"cvar_s{s}")

        self.model = m
        return m

    def _apply_first_stage_strategy_constraints(
        self,
        m: gp.Model,
        C_pv: gp.Var,
        C_bess: gp.Var,
        P_bess: gp.Var,
        q_energy: Dict[str, Dict[int, gp.Var]],
        r_matp: Dict[int, gp.Var],
    ) -> None:
        """Apply baseline-strategy restrictions to here-and-now decisions."""
        disabled = self.disabled_assets

        if "pv" in disabled or "der" in disabled:
            m.addConstr(C_pv == 0, name="strategy_disable_pv")
        if "bess" in disabled or "storage" in disabled or "der" in disabled:
            m.addConstr(C_bess == 0, name="strategy_disable_bess_energy")
            m.addConstr(P_bess == 0, name="strategy_disable_bess_power")
        if "energy_contracts" in disabled or "contracts" in disabled:
            for k in cfg.ENERGY_CONTRACT_TYPES:
                for m_idx, var in q_energy[k].items():
                    m.addConstr(var == 0, name=f"strategy_disable_{k}_m{m_idx}")
        for k in cfg.ENERGY_CONTRACT_TYPES:
            if k.lower() in disabled:
                for m_idx, var in q_energy[k].items():
                    m.addConstr(var == 0, name=f"strategy_disable_{k}_m{m_idx}")
        if "matp" in disabled or "power_contracts" in disabled or "contracts" in disabled:
            for m_idx, var in r_matp.items():
                m.addConstr(var == 0, name=f"strategy_disable_matp_m{m_idx}")

        fixed = self.fixed_first_stage
        if not fixed:
            return

        self._fix_scalar(m, C_pv, fixed, "C_PV")
        self._fix_scalar(m, C_bess, fixed, "C_BESS")
        self._fix_scalar(m, P_bess, fixed, "P_BESS")

        for k in cfg.ENERGY_CONTRACT_TYPES:
            values = (
                fixed.get("Q_energy", {}).get(k)
                if isinstance(fixed.get("Q_energy"), dict)
                else None
            )
            if values is None:
                values = fixed.get(f"Q_{k}_monthly_kwh", fixed.get(f"contract_{k}_monthly_kwh"))
            if values is None:
                values = fixed.get(f"contract_{k}_kwh")
            self._fix_monthly(m, q_energy[k], values, f"fix_{k}")

        values = (
            fixed.get("R_MATP")
            if "R_MATP" in fixed
            else fixed.get("R_MATP_monthly_kw", fixed.get("contract_MATP_monthly_kw"))
        )
        if values is None:
            values = fixed.get("contract_MATP_kw_avg")
        self._fix_monthly(m, r_matp, values, "fix_MATP")

    @staticmethod
    def _fix_scalar(m: gp.Model, var: gp.Var, fixed: Dict, key: str) -> None:
        if key in fixed and fixed[key] is not None:
            m.addConstr(var == float(fixed[key]), name=f"fix_{key}")

    def _fix_monthly(self, m: gp.Model, monthly_vars: Dict[int, gp.Var], values, name: str) -> None:
        if values is None:
            return
        if isinstance(values, dict):
            for m_idx, var in monthly_vars.items():
                value = values.get(m_idx, values.get(str(m_idx)))
                if value is not None:
                    m.addConstr(var == float(value), name=f"{name}_m{m_idx}")
            return
        if isinstance(values, (list, tuple, np.ndarray)):
            for m_idx, var in monthly_vars.items():
                if m_idx < len(values) and values[m_idx] is not None:
                    m.addConstr(var == float(values[m_idx]), name=f"{name}_m{m_idx}")
            return
        # A scalar fixes every modeled month to the same value. This is most
        # useful for MATP average-kW baselines.
        for m_idx, var in monthly_vars.items():
            m.addConstr(var == float(values), name=f"{name}_m{m_idx}")

    def _scenario_opex_expr(
        self,
        s: int,
        spot_price: np.ndarray,
        grid_adder: np.ndarray,
        q_energy: Dict[str, Dict[int, gp.Var]],
        r_matp: Dict[int, gp.Var],
        e_spot: Dict[int, gp.tupledict],
        e_grid: Dict[int, gp.tupledict],
        e_dis: Dict[int, gp.tupledict],
        d_red: Dict[int, gp.tupledict],
        phi_deg: Dict[int, gp.tupledict],
        r_spot_p: Dict[int, Dict[int, gp.Var]],
        dev_under: Dict[int, Dict[str, gp.tupledict]],
    ) -> gp.LinExpr:
        expr = gp.LinExpr()

        top_penalty = getattr(cfg, "CONTRACT_TOP_PENALTY_USD_PER_MWH", {})
        # Tiny coefficient on dev_under that costs ~1 USD/year at the worst-case
        # observed Q, but breaks the LP degeneracy created when the top penalty
        # is zero (multiple equivalent first-stage decisions for some CVaR
        # weights, e.g. beta=0.25 in our 365-day campaign).
        symmetry_break_usd_per_mwh = getattr(
            cfg, "CONTRACT_DEV_SYMMETRY_BREAK_USD_PER_MWH", 0.01
        )

        for m_idx in range(self.num_months):
            peak_hours = _modeled_peak_hours(self.month_boundaries, m_idx)
            kp = _ppad_kp(m_idx)
            matp_usd_per_kw_month = cfg.CONTRACT_PRICES["MATP"] * kp * peak_hours / 1000.0
            ppad_spot_usd_per_kw_month = cfg.PPAD_SPOT_USD_PER_MWHRP * kp * peak_hours / 1000.0

            for k in cfg.ENERGY_CONTRACT_TYPES:
                expr += cfg.CONTRACT_PRICES[k] / 1000.0 * q_energy[k][m_idx]
                top_k = top_penalty.get(k, 0.0) + symmetry_break_usd_per_mwh
                expr += top_k / 1000.0 * dev_under[s][k][m_idx]
            expr += matp_usd_per_kw_month * r_matp[m_idx]
            expr += ppad_spot_usd_per_kw_month * r_spot_p[s][m_idx]

        for t in range(self.T):
            expr += spot_price[s, t] / 1000.0 * e_spot[s][t]
            expr += grid_adder[s, t] / 1000.0 * e_grid[s][t]
            expr += cfg.C_DEG * phi_deg[s][t]
            expr += cfg.DR_COST * d_red[s][t]

        return expr

    def solve(self) -> Dict:
        """Solve the model and return a result summary."""
        if self.model is None:
            self.build()

        self.model.optimize()

        if self.model.Status == GRB.INFEASIBLE:
            self.model.computeIIS()
            self.model.write("infeasible.ilp")
            raise RuntimeError("Model is infeasible. IIS written to infeasible.ilp")

        if self.model.SolCount == 0:
            return {
                "status": self.model.Status,
                "objective": None,
                "mip_gap": None,
                "solve_time": self.model.Runtime,
            }

        return self._extract_results()

    def _extract_results(self) -> Dict:
        m = self.model
        C_pv = self.first_stage_vars["C_PV"].X
        C_bess = self.first_stage_vars["C_BESS"].X
        P_bess = self.first_stage_vars["P_BESS"].X
        q_energy = self.first_stage_vars["Q_energy"]
        r_matp = self.first_stage_vars["R_MATP"]

        total_q = {
            k: sum(q_energy[k][m_idx].X for m_idx in range(self.num_months))
            for k in cfg.ENERGY_CONTRACT_TYPES
        }
        monthly_q = {
            k: [q_energy[k][m_idx].X for m_idx in range(self.num_months)]
            for k in cfg.ENERGY_CONTRACT_TYPES
        }
        monthly_r_matp = [r_matp[m_idx].X for m_idx in range(self.num_months)]
        avg_r_matp = sum(r_matp[m_idx].X for m_idx in range(self.num_months)) / max(self.num_months, 1)

        capex_value = self.capex_expr.getValue() if self.capex_expr is not None else None
        opex_values = [self.opex_expr[s].getValue() for s in range(self.S)]
        expected_opex = float(np.mean(opex_values)) if opex_values else None
        cvar_opex = _empirical_cvar(opex_values, cfg.CVAR_ALPHA)
        var_opex = _empirical_var(opex_values, cfg.CVAR_ALPHA)

        e_spot = self.second_stage_vars["e_spot"]
        e_grid = self.second_stage_vars["e_grid"]
        e_pv = self.second_stage_vars["e_pv"]
        e_dis = self.second_stage_vars["e_dis"]
        e_ch = self.second_stage_vars["e_ch"]
        d_red = self.second_stage_vars["d_red"]
        r_ppad = self.second_stage_vars["r_ppad"]
        r_spot_p = self.second_stage_vars["r_spotP"]
        e_con = self.second_stage_vars["e_con"]

        def expected_energy_mwh(var_by_s) -> float:
            if not var_by_s:
                return 0.0
            values = [sum(var_by_s[s][t].X for t in range(self.T)) for s in range(self.S)]
            return float(np.mean(values) * self.opex_scale / 1000.0)

        spot_mwh = expected_energy_mwh(e_spot)
        grid_mwh = expected_energy_mwh(e_grid)
        pv_mwh = expected_energy_mwh(e_pv)
        bess_dis_mwh = expected_energy_mwh(e_dis)
        bess_ch_mwh = expected_energy_mwh(e_ch)
        dr_mwh = expected_energy_mwh(d_red)
        contract_alloc_mwh = {}
        for k in cfg.ENERGY_CONTRACT_TYPES:
            values = [
                sum(e_con[s][k][t].X for t in range(self.T))
                for s in range(self.S)
            ]
            contract_alloc_mwh[k] = float(np.mean(values) * self.opex_scale / 1000.0)

        dev_under_var = self.second_stage_vars.get("dev_under", {})
        contract_dev_under_mwh = {}
        contract_top_penalty_usd_y = {}
        top_penalty_cfg = getattr(cfg, "CONTRACT_TOP_PENALTY_USD_PER_MWH", {})
        for k in cfg.ENERGY_CONTRACT_TYPES:
            if not dev_under_var:
                contract_dev_under_mwh[k] = 0.0
                contract_top_penalty_usd_y[k] = 0.0
                continue
            per_scenario = [
                sum(dev_under_var[s][k][m_idx].X for m_idx in range(self.num_months))
                for s in range(self.S)
            ]
            mean_dev_kwh = float(np.mean(per_scenario)) if per_scenario else 0.0
            contract_dev_under_mwh[k] = mean_dev_kwh * self.opex_scale / 1000.0
            top_k = float(top_penalty_cfg.get(k, 0.0))
            contract_top_penalty_usd_y[k] = top_k * contract_dev_under_mwh[k]

        peak_import_values = []
        residual_ppad_values = []
        for s in range(self.S):
            if self.num_months:
                peak_import_values.append(max(r_ppad[s][m_idx].X for m_idx in range(self.num_months)))
                residual_ppad_values.append(max(r_spot_p[s][m_idx].X for m_idx in range(self.num_months)))
        peak_import_kw = float(np.mean(peak_import_values)) if peak_import_values else 0.0
        residual_ppad_kw = float(np.mean(residual_ppad_values)) if residual_ppad_values else 0.0

        results = {
            "status": m.Status,
            "case": self.scenarios.get("case", cfg.ACTIVE_CASE),
            "start_interval": self.scenarios.get("start_interval", cfg.START_INTERVAL),
            "objective": m.ObjVal,
            "mip_gap": m.MIPGap if m.IsMIP else 0.0,
            "solve_time": m.Runtime,
            "num_vars": m.NumVars,
            "num_constrs": m.NumConstrs,
            "opex_scale_to_year": self.opex_scale,
            "annualized_capex": capex_value,
            "expected_opex": expected_opex,
            "expected_total_cost": (capex_value or 0.0) + (expected_opex or 0.0),
            "var_opex": var_opex,
            "cvar_opex": cvar_opex,
            "var_total_cost": (capex_value or 0.0) + (var_opex or 0.0),
            "cvar_total_cost": (capex_value or 0.0) + (cvar_opex or 0.0),
            "opex_scenario_values": [float(v) for v in opex_values],
            "cvar_eta": self.cvar_vars["eta"].X,
            "C_PV": C_pv,
            "C_BESS": C_bess,
            "P_BESS": P_bess,
            "Q_MATER_monthly_kwh": monthly_q.get("MATER", []),
            "Q_MATE_monthly_kwh": monthly_q.get("MATE", []),
            "R_MATP_monthly_kw": monthly_r_matp,
            "contract_MATER_kwh": total_q.get("MATER", 0.0),
            "contract_MATE_kwh": total_q.get("MATE", 0.0),
            "contract_MATER_mwh": total_q.get("MATER", 0.0) / 1000.0,
            "contract_MATE_mwh": total_q.get("MATE", 0.0) / 1000.0,
            "contract_MATP_kw_avg": avg_r_matp,
            "spot_mwh_y": spot_mwh,
            "grid_import_mwh_y": grid_mwh,
            "pv_self_consumption_mwh_y": pv_mwh,
            "bess_discharge_mwh_y": bess_dis_mwh,
            "bess_charge_mwh_y": bess_ch_mwh,
            "demand_reduction_mwh_y": dr_mwh,
            "contract_MATER_alloc_mwh_y": contract_alloc_mwh.get("MATER", 0.0),
            "contract_MATE_alloc_mwh_y": contract_alloc_mwh.get("MATE", 0.0),
            "contract_MATER_dev_under_mwh_y": contract_dev_under_mwh.get("MATER", 0.0),
            "contract_MATE_dev_under_mwh_y": contract_dev_under_mwh.get("MATE", 0.0),
            "contract_MATER_top_penalty_usd_y": contract_top_penalty_usd_y.get("MATER", 0.0),
            "contract_MATE_top_penalty_usd_y": contract_top_penalty_usd_y.get("MATE", 0.0),
            "contract_top_penalty_usd_per_mwh_MATER": float(top_penalty_cfg.get("MATER", 0.0)),
            "contract_top_penalty_usd_per_mwh_MATE": float(top_penalty_cfg.get("MATE", 0.0)),
            "peak_import_kw": peak_import_kw,
            "residual_ppad_kw": residual_ppad_kw,
            # Legacy result aliases.
            "contract_MATER": total_q.get("MATER", 0.0) / max(self.T * cfg.DELTA_T, 1e-9),
            "contract_MAT": total_q.get("MATE", 0.0) / max(self.T * cfg.DELTA_T, 1e-9),
            "contract_MATE": total_q.get("MATE", 0.0) / max(self.T * cfg.DELTA_T, 1e-9),
            "contract_MATP": avg_r_matp,
        }

        return results


class _MonthlyVarProxy:
    """Legacy helper exposing .X as a scaled aggregate of monthly variables."""

    def __init__(self, monthly_vars: Dict[int, gp.Var], scale: float = 1.0):
        self.monthly_vars = monthly_vars
        self.scale = scale

    @property
    def X(self) -> float:
        if not self.monthly_vars:
            return 0.0
        return self.scale * sum(v.X for v in self.monthly_vars.values())


def _scenario_array(scenarios: Dict[str, np.ndarray], *keys: str) -> np.ndarray:
    for key in keys:
        if key in scenarios:
            return scenarios[key]
    raise KeyError(f"Missing scenario array. Tried keys: {keys}")


def _month_boundaries_for_horizon(T: int) -> List[int]:
    boundaries = [b for b in cfg.MONTH_BOUNDARIES if b <= T]
    if not boundaries or boundaries[0] != 0:
        boundaries.insert(0, 0)
    if boundaries[-1] != T:
        boundaries.append(T)
    return boundaries


def _month_hours(boundaries: List[int], month_idx: int) -> float:
    return (boundaries[month_idx + 1] - boundaries[month_idx]) * cfg.DELTA_T


def _ppad_peak_intervals(start: int, end: int) -> List[int]:
    intervals_per_hour = int(round(1.0 / cfg.DELTA_T))
    peak = []
    for t in range(start, end):
        hour = (t // intervals_per_hour) % 24
        if hour in cfg.PPAD_PEAK_HOURS:
            peak.append(t)
    return peak


def _modeled_peak_hours(boundaries: List[int], month_idx: int) -> float:
    start, end = boundaries[month_idx], boundaries[month_idx + 1]
    return max(len(_ppad_peak_intervals(start, end)) * cfg.DELTA_T, cfg.DELTA_T)


def _ppad_kp(month_idx: int) -> float:
    # Month indices are zero-based. Argentina summer/winter reliability
    # windows in the UCEMA material: Dec-Mar and Jun-Aug.
    month = ((month_idx + cfg.MONTH_OFFSET) % 12) + 1
    if month in {1, 2, 3, 6, 7, 8, 12}:
        return cfg.PPAD_KP_SUMMER_WINTER
    return cfg.PPAD_KP_SHOULDER


def _empirical_var(values: List[float], alpha: float) -> float:
    if not values:
        return 0.0
    arr = np.sort(np.asarray(values, dtype=np.float64))
    idx = int(np.ceil(alpha * len(arr))) - 1
    idx = min(max(idx, 0), len(arr) - 1)
    return float(arr[idx])


def _empirical_cvar(values: List[float], alpha: float) -> float:
    if not values:
        return 0.0
    arr = np.sort(np.asarray(values, dtype=np.float64))
    tail_count = max(1, int(np.ceil((1.0 - alpha) * len(arr))))
    return float(np.mean(arr[-tail_count:]))


if __name__ == "__main__":
    print("Building STORM model...")
    milp = StochasticProcurementMILP()
    milp.build()
    milp.model.update()
    print(f"Model built: {milp.model.NumVars} variables, {milp.model.NumConstrs} constraints")
    print("Solving...")
    results = milp.solve()
    print(f"Objective: {results['objective']}")
    print(f"C_PV: {results.get('C_PV', 0):.1f} kWp")
    print(f"C_BESS: {results.get('C_BESS', 0):.1f} kWh")
    print(f"P_BESS: {results.get('P_BESS', 0):.1f} kW")
    print(f"MATER: {results.get('contract_MATER_mwh', 0):.1f} MWh")
    print(f"MATE: {results.get('contract_MATE_mwh', 0):.1f} MWh")
    print(f"MATP: {results.get('contract_MATP_kw_avg', 0):.1f} kW")
