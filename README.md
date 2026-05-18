# STORM

**Stochastic Trading and Optimization under Regulation** for the Argentine
Wholesale Electricity Market (MEM). A two-stage stochastic MILP for
electricity procurement and behind-the-meter DER sizing under the
post-Resolution SE 400/2025 contracting structure.

This repository hosts two parts:

| Path | What it contains |
|------|------------------|
| `index.html`, `app.js`, `i18n.js`, `styles.css`, `assets/` | Project website (deployed via GitHub Pages). |
| [`model/`](model/) | Python implementation of the STORM MILP, scenario generator, baseline-strategy suite, campaign infrastructure, and paper-figure scripts. |

## Quick start with the model

```bash
cd model
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Validate the install (1 day, hourly, 2 scenarios — solves in seconds)
python storm.py solve --days 1 --delta-t 1.0 --scenarios 2

# Show the active configuration
python storm.py info
```

A Gurobi license is required for the full-year campaign; the bundled
size-limited license fits only the `smoke` phase. See
[`model/README.md`](model/README.md) for the complete usage guide,
configuration overview, and paper-reproduction recipe.

## Citation

If you use STORM, please cite:

```
J. A. Fraire, O. A. Oviedo, and G. Martínez Carreras,
"Stochastic Trading and Optimization under Regulation for the Argentine
 Electricity Market," 2026.
```

## Acknowledgments

Demand profiles, contract-price references, and PPAD/MEM cost assumptions
in this repository are derived from the UCEMA *Diplomatura en Gestión y
Compra de Energía Eléctrica*:
<https://ucema.edu.ar/educacion-ejecutiva/gestion-compra-energia-electrica>.
