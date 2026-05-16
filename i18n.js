/* ============================================================
   STORM — EN/ES (Argentina) i18n
   - auto-detects navigator.language on first visit (es-* → es)
   - persists user choice in localStorage
   - swaps innerHTML of every [data-i18n] element
   - exposes window.t(key) and window.setLang(lang)
   - dispatches `langchange` so chart code can re-render labels
   ============================================================ */
(() => {
  'use strict';

  const DICT = {
    en: {
      /* nav */
      'nav.model': 'Model',
      'nav.workflow': 'Workflow',
      'nav.code': 'Code',
      'nav.foundations': 'Foundations',
      'nav.results': 'Results',
      'nav.applications': 'Applications',
      'nav.engagement': 'Engagement',
      'nav.cta': 'Read the paper',

      /* hero */
      'hero.eyebrow': 'Two-stage stochastic MILP · CVaR-aware · MEM Resolución SE&nbsp;400/2025',
      'hero.h1': 'Optimization under<br /><span class="gradient">uncertainty</span> for<br />industrial energy systems.',
      'hero.lede': 'STORM is a computational framework that jointly designs the contracting portfolio and behind-the-meter generation and storage for large electricity users in the Argentine Wholesale Market (MEM) — pricing volume, power-adequacy, and tail risk as first-class decisions rather than after-the-fact accounting.',
      'hero.meta.1': 'MATER · MATE · MATP',
      'hero.meta.2': 'PV + BESS sizing',
      'hero.meta.3': '35,040 × Δt = 15 min',
      'hero.meta.4': 'CVaR<sub>α=0.95</sub>',
      'hero.meta.5': 'Gurobi 11',
      'hero.cta.read': 'Read the paper',
      'hero.cta.code': 'Explore the code',
      'hero.cta.explore': 'Explore the model',
      'hero.cta.workflow': 'View the architecture →',
      'hero.kpi1.label': 'Case 3 — full year',
      'hero.kpi1.value': '−33.3<span class="unit">% vs GUDI</span>',
      'hero.kpi2.label': 'Expected total cost',
      'hero.kpi2.value': '525.4<span class="unit">kUSD / year</span>',
      'hero.kpi3.label': 'First-stage PV hedge',
      'hero.kpi3.value': '2.29<span class="unit">MW<sub>p</sub></span>',
      'hero.kpi4.label': 'MIP gap reported',
      'hero.kpi4.value': '0.00<span class="unit">% · 44/44 runs</span>',

      /* model section */
      'model.eyebrow': 'The framework',
      'model.h2': 'A here-and-now portfolio, a wait-and-see dispatch.',
      'model.lede': 'STORM is a two-stage stochastic mixed-integer linear program. The first stage locks in monthly contract volumes <span class="mono cyan">Q<sup>E</sup><sub>k,m</sub></span>, power-adequacy coverage <span class="mono cyan">R<sup>P</sup><sub>m</sub></span>, and installed capacity <span class="mono cyan">C<sup>PV</sup>, C<sup>BESS</sup>, P<sup>BESS</sup></span> before uncertainty is revealed. The second stage dispatches energy, storage, and demand response per scenario across <strong>S</strong> realizations of demand, spot price, PV yield, and tariff parameters.',
      'model.fan.demand.title': 'Native demand',
      'model.fan.spot.title': 'Spot energy price',
      'model.fan.pv.title': 'PV yield',
      'model.fan.legend.median': 'median',
      'model.fan.legend.band': '10–90%',
      'model.fan.legend.minmax': 'min–max',
      'model.note': 'Inputs are stochastic objects, not point forecasts. First-stage variables cannot adapt to a particular realization — they must hedge across the full envelope.',

      /* MEM context */
      'mem.eyebrow': 'The Argentine MEM',
      'mem.h2': 'User cost is a stack, not a price.',
      'mem.lede': 'Under Resolución SE 400/2025 the procurement choice reopens for large industrial users. STORM models the cost stack the way the regulator records it — separating energy from power-adequacy, grid services, transport, distribution <em>peaje</em>, and local adders — so contracts and behind-the-meter assets are sized against the exposures they actually hedge.',
      'mem.stack.label': 'Approximate cost-stack — large industrial user (Case 3, 1.247 MW peak)',
      'mem.stack.source': 'CAMMESA DTE settlement components',
      'mem.stack.energy': 'Energy · 55%',
      'mem.stack.ppad': 'PPAD · 18%',
      'mem.stack.peaje': 'Peaje · 12%',
      'mem.stack.services': 'Services · 8%',
      'mem.stack.local': 'Local · 7%',
      'mem.legend.energy': 'Energy — MATER / MATE / spot',
      'mem.legend.power': 'Power adequacy — MATP / PPAD',
      'mem.legend.peaje': 'Distribution peaje',
      'mem.legend.services': 'Grid services + transport',
      'mem.legend.local': 'Local tariffs + taxes',
      'mem.card.mater.title': 'MATER',
      'mem.card.mater.desc': 'Renewable energy contract. Bilateral MWh from wind, PV, biomass — long duration, profile-fit, counterparty exposure.',
      'mem.card.mate.title': 'MATE',
      'mem.card.mate.desc': 'Energy contract with conventional, hydro, or renewable generators. Monthly take-or-pay / deliver-or-pay commitments.',
      'mem.card.matp.title': 'MATP',
      'mem.card.matp.desc': 'Power-adequacy hedge tied to CAMMESA peak-hour requirements. Priced per MW of reserved peak, not per MWh.',
      'mem.card.spot.title': 'Spot + PPAD',
      'mem.card.spot.desc': 'Residual energy and power settled after contracts and self-supply. PPAD activates only when peak-hour exposure becomes expensive.',

      /* workflow */
      'wf.eyebrow': 'Architecture',
      'wf.h2': 'A scenario fan in, an investment plan out.',
      'wf.lede': 'Inputs define an uncertainty envelope. First-stage decisions are fixed before uncertainty resolves. Second-stage recourse adapts the operation by scenario. The objective penalizes the conditional tail of OPEX via CVaR.',
      'wf.s1.label': 'Inputs',
      'wf.s1.title': 'Scenarios &amp; parameters',
      'wf.s1.v1': 'demand (kWh)',
      'wf.s1.v2': 'PV yield (kWh / kW<sub>p</sub>)',
      'wf.s1.v3': 'spot price',
      'wf.s1.v4': 'PPAD adder',
      'wf.s1.v5': 'annualized CAPEX',
      'wf.s1.v6': 'CVaR settings',
      'wf.s2.label': 'First stage · here-and-now',
      'wf.s2.title': 'Portfolio &amp; sizing',
      'wf.s2.v1': 'monthly MATER/MATE volume',
      'wf.s2.v2': 'MATP / PPAD coverage',
      'wf.s2.v3': 'PV capacity (kW<sub>p</sub>)',
      'wf.s2.v4': 'BESS energy (kWh)',
      'wf.s2.v5': 'BESS power (kW)',
      'wf.s2.v6': 'non-anticipativity',
      'wf.s3.label': 'Second stage · per scenario',
      'wf.s3.title': 'Dispatch &amp; recourse',
      'wf.s3.v1': 'spot energy purchase',
      'wf.s3.v2': 'contract energy allocation',
      'wf.s3.v3': 'BESS charge / SOC',
      'wf.s3.v4': 'demand reduction',
      'wf.s3.v5': 'residual PPAD',
      'wf.s3.v6': 'take-or-pay slack',
      'wf.s4.label': 'Objective',
      'wf.s4.title': 'Risk-aware optimum',
      'wf.s4.v1': 'annualized investment',
      'wf.s4.v2': 'expected operation cost',
      'wf.s4.v3': 'tail-risk penalty',
      'wf.s4.v4': 'β = 0 · risk-neutral',
      'wf.s4.v5': 'β &gt; 0 · risk-averse',

      /* code */
      'code.eyebrow': 'Implementation',
      'code.h2': 'Build the program. Solve the fan.',
      'code.lede': 'STORM is implemented in Python on top of Gurobi. The first-stage variables are declared outside the scenario loop so non-anticipativity is enforced structurally. The second stage indexes everything by <span class="mono cyan">(t, s)</span> over T = 35,040 intervals and S scenarios — solved at root with a reported MIP gap of zero in the headline campaign.',
      'code.output.title': 'CVaR risk-aversion sweep — Case 3',
      'code.output.badge': 'β ∈ [0, 2]',
      'code.output.pvLabel': 'PV @ β=2',
      'code.output.bessLabel': 'BESS @ β=2',
      'code.output.mateLabel': 'MATE energy',
      'code.output.pvDelta': '+65%',
      'code.output.bessUnit': 'MWh',
      'code.output.mateDelta': '−16%',
      'code.note': 'Source: full-year Case 3 campaign. Increasing β shifts the first-stage portfolio toward physical hedges (PV, BESS) and reduces MATE energy commitments and MATP coverage.',

      /* foundations */
      'found.eyebrow': 'Scientific foundation',
      'found.h2': 'CAPEX is deterministic. OPEX is a distribution.',
      'found.lede': 'The objective has three layers: annualized capital cost on first-stage assets, the expected operating cost across scenarios, and the conditional value-at-risk of the OPEX tail. CAPEX does not affect the ordering of scenarios — only the OPEX distribution enters the tail-risk term.',
      'found.eq1.label': 'Eq. 4 · Objective',
      'found.eq1.title': 'Annualized cost with CVaR penalty',
      'found.eq1.note': 'β controls risk aversion. β = 0 yields <span class="cyan">STORM-RN</span>, the risk-neutral expected-cost optimizer. Larger β shifts the portfolio toward conservative hedges — defining <span class="cyan">STORM-CVaR</span>.',
      'found.eq2.label': 'Eq. 5–6 · CVaR',
      'found.eq2.title': 'Tail expectation via auxiliary slacks',
      'found.eq2.note': 'Rockafellar–Uryasev representation. With α = 0.95 the term penalizes the worst 5% of scenario OPEX outcomes, independent of CAPEX.',
      'found.eq3.label': 'Eq. 7 · Energy balance',
      'found.eq3.title': 'Site equilibrium per interval, per scenario',
      'found.eq3.note': 'Supply from grid spot, MEM contracts, PV self-consumption, BESS discharge, and curtailed demand must equal native load plus charging energy at every (t, s).',
      'found.eq4.label': 'Eq. 11, 15 · BESS',
      'found.eq4.title': 'State-of-charge dynamics with SOC window',
      'found.eq4.note': 'Storage operating bounds are linear in the first-stage energy capacity. A linear discharge-throughput penalty captures the first-order economic cost of cycling.',
      'found.eq5.label': 'Eq. 17–18 · PPAD',
      'found.eq5.title': 'Power-adequacy exposure on peak intervals',
      'found.eq5.note': 'Chargeable peak power is the maximum grid import during the regulated peak-hour window. MATP coverage absorbs it; the remainder is paid at the residual PPAD rate.',
      'found.eq6.label': 'Eq. 8–9 · Take-or-pay',
      'found.eq6.title': 'Monthly contract commitment with TOP slack',
      'found.eq6.note': 'Unilateral departure from the monthly commitment is priced at the take-or-pay penalty c<sup>TOP</sup><sub>k</sub> · δ<sup>TOP</sup>. Setting c<sup>TOP</sup>=0 recovers the pure commitment-cost formulation.',

      /* results */
      'res.eyebrow': 'Numerical campaign · Case 3 · 365 days',
      'res.h2': 'The joint feasible set wins.',
      'res.lede': 'Evaluated on the same 12-scenario fan, STORM beats every single-channel ablation: contracts-only and DER-only are both materially worse than co-optimizing the two. CVaR-aware first-stage decisions trade a modest expected-cost premium for a measurably tighter tail.',
      'res.barCardTitle': 'Baseline comparison · annual cost',
      'res.barCardNote': 'kUSD / year · expected total cost (dark) and empirical CVaR<sub>95%</sub> (cyan band). Bars drawn from Table II of the paper.',
      'res.tableCardTitle': 'Strategy summary',
      'res.tableCardNote': 'Costs in kUSD/year. Capacities in MW<sub>p</sub> (PV) and MWh (BESS). MIP gap = 0% on all non-GUDI runs.',
      'res.th.strategy': 'Strategy',
      'res.row.gudi': 'GUDI full service',
      'res.row.detEV': 'Deterministic EV',
      'res.row.contracts': 'Contracts-only',
      'res.row.derOnly': 'DER-only',
      'res.row.noDeg': 'STORM-CVaR · no deg.',

      /* applications */
      'apps.eyebrow': 'Applications',
      'apps.h2': 'Where STORM-class decisions live.',
      'apps.lede': 'The same two-stage structure generalizes well beyond the Case 3 logistics center: any industrial-scale procurement decision exposed to layered regulatory cost stacks and operational uncertainty admits the same framing.',
      'apps.c1.title': 'Industrial procurement',
      'apps.c1.desc': 'Migration analysis from GUDI to GUMA / GUME for users with mixed schedules and seasonal load profiles.',
      'apps.c2.title': 'PV + BESS sizing',
      'apps.c2.desc': 'Joint sizing of behind-the-meter generation and storage against price, demand, and irradiance scenarios.',
      'apps.c3.title': 'Contract portfolio design',
      'apps.c3.desc': 'Optimal monthly volume across MATER, MATE, MATP — with take-or-pay structures explicit in the formulation.',
      'apps.c4.title': 'Tail-risk hedging',
      'apps.c4.desc': 'CVaR-aware first-stage decisions for buyers required to demonstrate cost-stability under regulatory volatility.',
      'apps.c5.title': 'Peak-shaving valuation',
      'apps.c5.desc': 'Quantify when BESS substitutes for MATP power coverage as a function of installed storage cost.',
      'apps.c6.title': 'Demand-response programs',
      'apps.c6.desc': 'Value voluntary load reduction under SE 379/2025 caps against full-year scenario distributions.',
      'apps.c7.title': 'Regulatory transition',
      'apps.c7.desc': 'Side-by-side baseline vs. post-Resolution scenarios — measure migration value beyond aggregate tariff numbers.',
      'apps.c8.title': 'Scenario-based planning',
      'apps.c8.desc': 'Plug in any source of structured uncertainty — hydrology, fuel, FSA transition path — without rewriting the model.',

      /* engagement */
      'eng.eyebrow': 'Engagement models',
      'eng.h2': 'Use STORM as a model, a workflow, or a managed decision service.',
      'eng.lede': 'STORM can be adopted at different levels of depth: from licensing the optimization model and integrating it with internal tools, to using the team as a technical partner for procurement studies, scenario design, and decision support.',
      'eng.c1.title': 'Model licensing',
      'eng.c1.desc': 'Access to the STORM formulation, scenario structure, data templates, and reproducible optimization workflow for internal studies and recurring analyses.',
      'eng.c2.title': 'Python integration',
      'eng.c2.desc': 'Integration with Python pipelines, notebooks, dashboards, APIs, Gurobi environments, and existing data workflows used by technical teams.',
      'eng.c3.title': 'Excel-first deployment',
      'eng.c3.desc': 'A practical spreadsheet interface for organizations that need structured inputs, auditable assumptions, and exportable results before adopting a full Python stack.',
      'eng.c4.title': 'Consulting studies',
      'eng.c4.desc': 'One-off or periodic studies for contract portfolios, PV+BESS sizing, GUDI/GUMA/GUME migration, PPAD exposure, and CVaR-based risk analysis.',
      'eng.c5.title': 'Managed decision support',
      'eng.c5.desc': 'Scenario updates, model runs, sensitivity analysis, and executive reporting delivered as a recurring analytical service for management teams.',
      'eng.c6.title': 'Executive + technical outputs',
      'eng.c6.desc': 'Decision memos, reproducible notebooks, Excel workbooks, scenario reports, investment recommendations, and technical appendices for auditability.',

      /* final CTA */
      'cta.h2': 'Engineering optimization <span class="gradient">under uncertainty.</span>',
      'cta.lede': 'A two-stage stochastic MILP for procurement and DER sizing under the Argentine MEM normalization process — open implementation, reproducible campaign, anonymized for review.',
      'cta.read': 'Read the scientific foundation',
      'cta.code': 'View the implementation',
      'cta.results': 'Inspect the campaign',
      'cta.engagement': 'Discuss adoption',

      /* footer */
      'foot.affiliation': 'Affiliation',
      'foot.stack': 'Solver / stack',
      'foot.indexTerms': 'Index Terms — Stochastic optimization · MILP · BESS · MEM · MATER · MATE · MATP · CVaR · large industrial users',
      'foot.copy': '© 2025 · Anonymized for double-blind review',

      /* chart text (rendered by app.js) */
      'chart.cost': 'cost · kUSD/y',
      'chart.capacity': 'capacity',
      'chart.beta': 'β  ·  CVaR weight',
      'chart.kusdYear': 'kUSD / year',
      'chart.median': 'MEDIAN',
      'chart.band': '10-90%',
      'chart.minmax': 'MIN-MAX',
      'chart.bar.gudi': 'GUDI',
      'chart.bar.detEV': 'Det. EV',
      'chart.bar.stormRN': 'STORM-RN',
      'chart.bar.stormCVaR': 'STORM-CVaR',
      'chart.bar.contracts': 'Contracts',
      'chart.bar.derOnly': 'DER-only',
      'chart.bar.noDeg': 'No-deg.',
    },

    es: {
      /* nav */
      'nav.model': 'Modelo',
      'nav.workflow': 'Arquitectura',
      'nav.code': 'Código',
      'nav.foundations': 'Fundamentos',
      'nav.results': 'Resultados',
      'nav.applications': 'Aplicaciones',
      'nav.engagement': 'Adopción',
      'nav.cta': 'Leer el paper',

      /* hero */
      'hero.eyebrow': 'MILP estocástico de dos etapas · con CVaR · MEM · Resolución SE&nbsp;400/2025',
      'hero.h1': 'Optimización bajo<br /><span class="gradient">incertidumbre</span> para<br />sistemas energéticos industriales.',
      'hero.lede': 'STORM es un marco computacional que diseña en forma conjunta el portafolio de contratación y la generación y almacenamiento detrás del medidor para Grandes Usuarios del Mercado Eléctrico Mayorista argentino (MEM). Modela volumen, potencia y riesgo de cola como decisiones centrales del problema, no como ajustes contables posteriores.',
      'hero.meta.1': 'MATER · MATE · MATP',
      'hero.meta.2': 'Dimensionamiento FV + BESS',
      'hero.meta.3': '35.040 × Δt = 15 min',
      'hero.meta.4': 'CVaR<sub>α=0,95</sub>',
      'hero.meta.5': 'Gurobi 11',
      'hero.cta.read': 'Leer el paper',
      'hero.cta.code': 'Explorar el código',
      'hero.cta.explore': 'Explorar el modelo',
      'hero.cta.workflow': 'Ver la arquitectura →',
      'hero.kpi1.label': 'Caso 3 — año completo',
      'hero.kpi1.value': '−33,3<span class="unit">% vs GUDI</span>',
      'hero.kpi2.label': 'Costo total esperado',
      'hero.kpi2.value': '525,4<span class="unit">kUSD / año</span>',
      'hero.kpi3.label': 'Cobertura FV de primera etapa',
      'hero.kpi3.value': '2,29<span class="unit">MW<sub>p</sub></span>',
      'hero.kpi4.label': 'MIP gap reportado',
      'hero.kpi4.value': '0,00<span class="unit">% · 44/44 corridas</span>',

      /* model section */
      'model.eyebrow': 'El modelo',
      'model.h2': 'Un portafolio que se decide antes; un despacho que se adapta después.',
      'model.lede': 'STORM es un programa lineal entero mixto estocástico de dos etapas. La primera etapa fija los volúmenes mensuales de contratos <span class="mono cyan">Q<sup>E</sup><sub>k,m</sub></span>, la cobertura de potencia <span class="mono cyan">R<sup>P</sup><sub>m</sub></span> y la capacidad instalada <span class="mono cyan">C<sup>FV</sup>, C<sup>BESS</sup>, P<sup>BESS</sup></span> antes de conocer qué escenario va a ocurrir. La segunda etapa despacha energía, almacenamiento y respuesta de demanda para cada una de las <strong>S</strong> realizaciones de demanda, precio spot, rendimiento FV y parámetros tarifarios.',
      'model.fan.demand.title': 'Demanda nativa',
      'model.fan.spot.title': 'Precio spot de energía',
      'model.fan.pv.title': 'Rendimiento FV',
      'model.fan.legend.median': 'mediana',
      'model.fan.legend.band': '10–90%',
      'model.fan.legend.minmax': 'mín–máx',
      'model.note': 'Las entradas son objetos estocásticos, no pronósticos puntuales. Las variables de primera etapa no pueden adaptarse a una realización particular: deben cubrir toda la envolvente de escenarios.',

      /* MEM context */
      'mem.eyebrow': 'El MEM argentino',
      'mem.h2': 'El costo del usuario es una pila de cargos, no un único precio.',
      'mem.lede': 'Con la Resolución SE 400/2025 se reabre la posibilidad de elegir cómo abastecerse para los Grandes Usuarios industriales. STORM modela la pila de costos tal como aparece en la liquidación: energía, potencia, servicios de red, transporte, <em>peaje</em> de distribución y cargos locales. Así, los contratos y los activos detrás del medidor se dimensionan contra las exposiciones que realmente cubren.',
      'mem.stack.label': 'Pila de costos aproximada — Gran Usuario industrial (Caso 3, pico de 1,247 MW)',
      'mem.stack.source': 'Componentes de liquidación DTE de CAMMESA',
      'mem.stack.energy': 'Energía · 55%',
      'mem.stack.ppad': 'PPAD · 18%',
      'mem.stack.peaje': 'Peaje · 12%',
      'mem.stack.services': 'Servicios · 8%',
      'mem.stack.local': 'Locales · 7%',
      'mem.legend.energy': 'Energía — MATER / MATE / spot',
      'mem.legend.power': 'Potencia — MATP / PPAD',
      'mem.legend.peaje': 'Peaje de distribución',
      'mem.legend.services': 'Servicios de red + transporte',
      'mem.legend.local': 'Tarifas locales + impuestos',
      'mem.card.mater.title': 'MATER',
      'mem.card.mater.desc': 'Contrato de energía renovable. MWh bilaterales de eólica, FV o biomasa: largo plazo, ajuste de perfil y exposición de contraparte.',
      'mem.card.mate.title': 'MATE',
      'mem.card.mate.desc': 'Contrato de energía con generadores convencionales, hidroeléctricos o renovables. Compromisos mensuales take-or-pay / deliver-or-pay.',
      'mem.card.matp.title': 'MATP',
      'mem.card.matp.desc': 'Cobertura de potencia asociada a los requisitos de hora pico de CAMMESA. Se paga por MW de potencia reservada, no por MWh.',
      'mem.card.spot.title': 'Spot + PPAD',
      'mem.card.spot.desc': 'Energía y potencia residuales liquidadas después de contratos y autoabastecimiento. El PPAD aparece cuando la exposición de potencia en hora pico queda descubierta.',

      /* workflow */
      'wf.eyebrow': 'Arquitectura',
      'wf.h2': 'Entra un abanico de escenarios; sale una decisión de inversión.',
      'wf.lede': 'Las entradas definen una envolvente de incertidumbre. Las decisiones de primera etapa se fijan antes de saber qué escenario va a ocurrir. La segunda etapa adapta la operación en cada escenario. El objetivo penaliza la cola del OPEX mediante CVaR.',
      'wf.s1.label': 'Entradas',
      'wf.s1.title': 'Escenarios y parámetros',
      'wf.s1.v1': 'demanda (kWh)',
      'wf.s1.v2': 'rendimiento FV (kWh / kW<sub>p</sub>)',
      'wf.s1.v3': 'precio spot',
      'wf.s1.v4': 'adicional PPAD',
      'wf.s1.v5': 'CAPEX anualizado',
      'wf.s1.v6': 'parámetros CVaR',
      'wf.s2.label': 'Primera etapa · aquí-y-ahora',
      'wf.s2.title': 'Portafolio y dimensionamiento',
      'wf.s2.v1': 'volumen mensual MATER/MATE',
      'wf.s2.v2': 'cobertura MATP / PPAD',
      'wf.s2.v3': 'capacidad FV (kW<sub>p</sub>)',
      'wf.s2.v4': 'energía BESS (kWh)',
      'wf.s2.v5': 'potencia BESS (kW)',
      'wf.s2.v6': 'no anticipatividad',
      'wf.s3.label': 'Segunda etapa · por escenario',
      
      'wf.s3.title': 'Despacho y ajuste operativo',
      'wf.s3.v1': 'compra de energía spot',
      'wf.s3.v2': 'asignación de energía de contratos',
      'wf.s3.v3': 'carga BESS / SOC',
      'wf.s3.v4': 'reducción de demanda',
      'wf.s3.v5': 'PPAD residual',
      'wf.s3.v6': 'holgura take-or-pay',
      'wf.s4.label': 'Objetivo',
      'wf.s4.title': 'Óptimo con aversión al riesgo',
      'wf.s4.v1': 'inversión anualizada',
      'wf.s4.v2': 'costo operativo esperado',
      'wf.s4.v3': 'penalidad de riesgo de cola',
      'wf.s4.v4': 'β = 0 · neutral al riesgo',
      'wf.s4.v5': 'β &gt; 0 · averso al riesgo',

      /* code */
      'code.eyebrow': 'Implementación',
      'code.h2': 'Construir el modelo. Resolver el abanico de escenarios.',
      'code.lede': 'STORM está implementado en Python sobre Gurobi. Las variables de primera etapa se declaran fuera del bucle de escenarios para imponer la no anticipatividad desde la estructura del modelo. La segunda etapa indexa las decisiones por <span class="mono cyan">(t, s)</span>, con T = 35.040 intervalos y S escenarios. En la campaña principal, las corridas reportadas cierran con MIP gap igual a cero.',
      'code.output.title': 'Barrido de aversión al riesgo CVaR — Caso 3',
      'code.output.badge': 'β ∈ [0, 2]',
      'code.output.pvLabel': 'FV @ β=2',
      'code.output.bessLabel': 'BESS @ β=2',
      'code.output.mateLabel': 'energía MATE',
      'code.output.pvDelta': '+65%',
      'code.output.bessUnit': 'MWh',
      'code.output.mateDelta': '−16%',
      'code.note': 'Fuente: campaña Caso 3 de año completo. Al aumentar β, el portafolio de primera etapa se desplaza hacia coberturas físicas (FV y BESS), mientras se reducen los compromisos de energía MATE y la cobertura MATP.',

      /* foundations */
      'found.eyebrow': 'Base científica',
      'found.h2': 'El CAPEX es determinístico; el OPEX es una distribución.',
      'found.lede': 'El objetivo tiene tres capas: costo de capital anualizado de los activos de primera etapa, costo operativo esperado a través de los escenarios y valor en riesgo condicional de la cola de OPEX. El CAPEX no altera el orden de los escenarios: solo la distribución del OPEX entra en el término de riesgo de cola.',
      'found.eq1.label': 'Ec. 4 · Objetivo',
      'found.eq1.title': 'Costo anualizado con penalidad CVaR',
      'found.eq1.note': 'β controla la aversión al riesgo. β = 0 produce <span class="cyan">STORM-RN</span>, el optimizador neutral al riesgo basado en costo esperado. Valores mayores de β desplazan el portafolio hacia coberturas más conservadoras, definiendo <span class="cyan">STORM-CVaR</span>.',
      'found.eq2.label': 'Ec. 5–6 · CVaR',
      'found.eq2.title': 'Expectativa de cola con holguras auxiliares',
      'found.eq2.note': 'Representación de Rockafellar–Uryasev. Con α = 0,95, el término penaliza el peor 5% de los resultados de OPEX por escenario, independientemente del CAPEX.',
      'found.eq3.label': 'Ec. 7 · Balance de energía',
      'found.eq3.title': 'Equilibrio del sitio por intervalo, por escenario',
      'found.eq3.note': 'El suministro proveniente del spot, los contratos MEM, el autoconsumo FV, la descarga de BESS y la demanda reducida debe igualar la carga nativa más la energía de carga en cada (t, s).',
      'found.eq4.label': 'Ec. 11, 15 · BESS',
      'found.eq4.title': 'Dinámica del estado de carga con ventana SOC',
      'found.eq4.note': 'Los límites operativos del almacenamiento son lineales en la capacidad de energía definida en primera etapa. Una penalidad lineal por throughput de descarga captura el costo económico de primer orden del ciclado.',
      'found.eq5.label': 'Ec. 17–18 · PPAD',
      'found.eq5.title': 'Exposición de potencia en intervalos pico',
      'found.eq5.note': 'La potencia pico facturable es la máxima importación desde la red durante la ventana regulada de hora pico. La cobertura MATP la absorbe; el remanente se paga a la tarifa residual PPAD.',
      'found.eq6.label': 'Ec. 8–9 · Take-or-pay',
      'found.eq6.title': 'Compromiso mensual de contrato con holgura TOP',
      'found.eq6.note': 'El desvío unilateral del compromiso mensual se penaliza con c<sup>TOP</sup><sub>k</sub> · δ<sup>TOP</sup>. Si se fija c<sup>TOP</sup>=0, se recupera la formulación pura de costo de compromiso.',

      /* results */
      'res.eyebrow': 'Campaña numérica · Caso 3 · 365 días',
      'res.h2': 'Gana la co-optimización.',
      'res.lede': 'Evaluado sobre el mismo abanico de 12 escenarios, STORM supera a las ablaciones de un solo canal: solo contratos y solo DER resultan claramente peores que co-optimizar ambos frentes. Las decisiones de primera etapa con CVaR pagan una prima moderada en costo esperado a cambio de una cola de riesgo más controlada.',
      'res.barCardTitle': 'Comparación de baselines · costo anual',
      'res.barCardNote': 'kUSD / año · costo total esperado (oscuro) y CVaR<sub>95%</sub> empírico (banda cian). Barras tomadas de la Tabla II del paper.',
      'res.tableCardTitle': 'Resumen de estrategias',
      'res.tableCardNote': 'Costos en kUSD/año. Capacidades en MW<sub>p</sub> (FV) y MWh (BESS). MIP gap = 0% en todas las corridas excepto GUDI.',
      'res.th.strategy': 'Estrategia',
      'res.row.gudi': 'GUDI servicio completo',
      'res.row.detEV': 'Determinístico EV',
      'res.row.contracts': 'Solo contratos',
      'res.row.derOnly': 'Solo DER',
      'res.row.noDeg': 'STORM-CVaR · sin deg.',

      /* applications */
      'apps.eyebrow': 'Aplicaciones',
      'apps.h2': 'Dónde aparecen las decisiones tipo STORM.',
      'apps.lede': 'La misma estructura de dos etapas generaliza más allá del centro logístico del Caso 3: cualquier decisión de abastecimiento a escala industrial expuesta a pilas de costos regulatorios e incertidumbre operativa admite el mismo encuadre.',
      'apps.c1.title': 'Abastecimiento industrial',
      'apps.c1.desc': 'Análisis de migración de GUDI a GUMA / GUME para usuarios con horarios mixtos y perfiles de carga estacionales.',
      'apps.c2.title': 'Dimensionamiento FV + BESS',
      'apps.c2.desc': 'Dimensionamiento conjunto de generación y almacenamiento detrás del medidor frente a escenarios de precio, demanda e irradiancia.',
      'apps.c3.title': 'Diseño de portafolio de contratos',
      'apps.c3.desc': 'Volumen mensual óptimo entre MATER, MATE y MATP, con estructuras take-or-pay explícitas en la formulación.',
      'apps.c4.title': 'Cobertura de riesgo de cola',
      'apps.c4.desc': 'Decisiones de primera etapa con CVaR para compradores que necesitan demostrar estabilidad de costos frente a volatilidad regulatoria.',
      'apps.c5.title': 'Valuación de peak-shaving',
      'apps.c5.desc': 'Cuantificar cuándo el BESS sustituye cobertura de potencia MATP en función del costo del almacenamiento instalado.',
      'apps.c6.title': 'Programas de respuesta de demanda',
      'apps.c6.desc': 'Valorar la reducción voluntaria de carga bajo los topes de la SE 379/2025 frente a distribuciones de escenarios de año completo.',
      'apps.c7.title': 'Transición regulatoria',
      'apps.c7.desc': 'Escenarios base vs. post-Resolución, lado a lado, para medir el valor de migración más allá de los números tarifarios agregados.',
      'apps.c8.title': 'Planificación por escenarios',
      'apps.c8.desc': 'Incorporar cualquier fuente de incertidumbre estructurada — hidrología, combustible, trayectoria de transición FSA — sin reescribir el modelo.',

      /* engagement */
      'eng.eyebrow': 'Modalidades de adopción',
      'eng.h2': 'Usar STORM como modelo, flujo de trabajo o servicio de decisión gestionado.',
      'eng.lede': 'STORM puede adoptarse con distintos niveles de profundidad: desde licenciar el modelo de optimización e integrarlo con herramientas internas, hasta trabajar con el equipo como socio técnico para estudios de abastecimiento, diseño de escenarios y soporte de decisión.',
      'eng.c1.title': 'Licencia del modelo',
      'eng.c1.desc': 'Acceso a la formulación STORM, estructura de escenarios, plantillas de datos y flujo de optimización reproducible para estudios internos y análisis recurrentes.',
      'eng.c2.title': 'Integración Python',
      'eng.c2.desc': 'Integración con pipelines Python, notebooks, dashboards, APIs, entornos Gurobi y flujos de datos existentes en equipos técnicos.',
      'eng.c3.title': 'Despliegue inicial en Excel',
      'eng.c3.desc': 'Una interfaz práctica en planillas para organizaciones que necesitan entradas estructuradas, supuestos auditables y resultados exportables antes de adoptar un stack completo en Python.',
      'eng.c4.title': 'Estudios de consultoría',
      'eng.c4.desc': 'Estudios puntuales o periódicos para portafolios de contratos, dimensionamiento FV+BESS, migración GUDI/GUMA/GUME, exposición PPAD y análisis de riesgo con CVaR.',
      'eng.c5.title': 'Soporte de decisión gestionado',
      'eng.c5.desc': 'Actualización de escenarios, corridas del modelo, análisis de sensibilidad y reportes ejecutivos entregados como servicio analítico recurrente para equipos de gestión.',
      'eng.c6.title': 'Salidas ejecutivas y técnicas',
      'eng.c6.desc': 'Memos de decisión, notebooks reproducibles, planillas Excel, reportes de escenarios, recomendaciones de inversión y anexos técnicos para trazabilidad y auditoría.',

      /* final CTA */
      'cta.h2': 'Optimización computacional <span class="gradient">bajo incertidumbre.</span>',
      'cta.lede': 'Un MILP estocástico de dos etapas para abastecimiento y dimensionamiento DER bajo el proceso de normalización del MEM argentino: implementación abierta, campaña reproducible y versión anonimizada para revisión.',
      'cta.read': 'Leer la base científica',
      'cta.code': 'Ver el código',
      'cta.results': 'Explorar la campaña',
      'cta.engagement': 'Conversar adopción',

      /* footer */
      'foot.affiliation': 'Afiliación',
      'foot.stack': 'Solver / entorno',
      'foot.indexTerms': 'Términos índice — Optimización estocástica · MILP · BESS · MEM · MATER · MATE · MATP · CVaR · Grandes Usuarios industriales',
      'foot.copy': '© 2025 · Versión anonimizada para revisión doble ciego',

      /* chart text */
      'chart.cost': 'costo · kUSD/a',
      'chart.capacity': 'capacidad',
      'chart.beta': 'β  ·  peso CVaR',
      'chart.kusdYear': 'kUSD / año',
      'chart.median': 'MEDIANA',
      'chart.band': '10-90%',
      'chart.minmax': 'MÍN-MÁX',
      'chart.bar.gudi': 'GUDI',
      'chart.bar.detEV': 'Det. EV',
      'chart.bar.stormRN': 'STORM-RN',
      'chart.bar.stormCVaR': 'STORM-CVaR',
      'chart.bar.contracts': 'Contratos',
      'chart.bar.derOnly': 'Solo DER',
      'chart.bar.noDeg': 'Sin deg.',
    },
  };

  const STORE_KEY = 'storm.lang';

  function detectLang() {
    try {
      const saved = localStorage.getItem(STORE_KEY);
      if (saved === 'en' || saved === 'es') return saved;
    } catch (_) { /* private mode etc. */ }
    const nav = (navigator.language || navigator.userLanguage || 'en').toLowerCase();
    return nav.startsWith('es') ? 'es' : 'en';
  }

  let currentLang = detectLang();

  function t(key) {
    const v = DICT[currentLang] && DICT[currentLang][key];
    if (v !== undefined) return v;
    const en = DICT.en[key];
    return en !== undefined ? en : key;
  }

  function applyTranslations() {
    document.documentElement.lang = currentLang;
    document.querySelectorAll('[data-i18n]').forEach(el => {
      const key = el.getAttribute('data-i18n');
      const val = t(key);
      // skip if the value is identical to current innerHTML to avoid spurious paints
      if (el.innerHTML !== val) el.innerHTML = val;
    });
    // toggle state
    document.querySelectorAll('[data-lang-btn]').forEach(btn => {
      btn.classList.toggle('is-active', btn.dataset.langBtn === currentLang);
      btn.setAttribute('aria-pressed', String(btn.dataset.langBtn === currentLang));
    });
  }

  function setLang(lang) {
    if (lang !== 'en' && lang !== 'es') return;
    if (lang === currentLang) return;
    currentLang = lang;
    try { localStorage.setItem(STORE_KEY, lang); } catch (_) {}
    applyTranslations();
    document.dispatchEvent(new CustomEvent('langchange', { detail: { lang } }));
  }

  // expose
  window.t = t;
  window.setLang = setLang;
  Object.defineProperty(window, 'currentLang', { get: () => currentLang });

  function wireToggle() {
    document.querySelectorAll('[data-lang-btn]').forEach(btn => {
      btn.addEventListener('click', e => {
        e.preventDefault();
        setLang(btn.dataset.langBtn);
      });
    });
  }

  function boot() {
    applyTranslations();
    wireToggle();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
