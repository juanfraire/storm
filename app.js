/* ============================================================
   STORM — landing page interactions
   Hero flow-field, scenario fans, CVaR chart, results bars, KaTeX
   ============================================================ */
(() => {
  'use strict';

  /* ────────────────────────── small utilities ───────────────────────── */
  const TAU = Math.PI * 2;
  const lerp = (a, b, t) => a + (b - a) * t;
  const clamp = (x, lo, hi) => Math.max(lo, Math.min(hi, x));
  const ns = 'http://www.w3.org/2000/svg';
  const el = (n, a = {}) => {
    const e = document.createElementNS(ns, n);
    for (const k in a) e.setAttribute(k, a[k]);
    return e;
  };
  // i18n lookup — falls back to the key if i18n.js hasn't loaded yet
  const tr = (k) => (typeof window.t === 'function' ? window.t(k) : k);
  function clearSvg(id) {
    const svg = document.getElementById(id);
    if (svg) while (svg.firstChild) svg.removeChild(svg.firstChild);
  }

  // deterministic PRNG (mulberry32) — same seed → same scenario fan
  function rng(seed) {
    let t = seed >>> 0;
    return () => {
      t = (t + 0x6D2B79F5) >>> 0;
      let x = t;
      x = Math.imul(x ^ (x >>> 15), x | 1);
      x ^= x + Math.imul(x ^ (x >>> 7), x | 61);
      return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
    };
  }

  // 1D value noise — smooth interpolation between random control points
  function noise1D(seed, controlPoints = 16) {
    const r = rng(seed);
    const v = Array.from({ length: controlPoints + 1 }, () => r());
    return (t) => {
      const x = t * controlPoints;
      const i = Math.floor(x);
      const f = x - i;
      const sm = f * f * (3 - 2 * f);
      const a = v[i % controlPoints];
      const b = v[(i + 1) % controlPoints];
      return lerp(a, b, sm);
    };
  }

  // simple 2D-ish pseudo perlin (sum of sines for vector field — cheap and good enough)
  function flow(x, y, t) {
    const a = Math.sin(x * 0.7 + t * 0.3) + Math.cos(y * 0.6 - t * 0.2);
    const b = Math.cos(x * 0.4 - t * 0.25) + Math.sin(y * 0.9 + t * 0.18);
    return Math.atan2(b, a);
  }

  /* ────────────────────────── HERO CANVAS ─────────────────────────── */
  function initHeroCanvas() {
    const canvas = document.getElementById('hero-canvas');
    if (!canvas) return;

    // respect reduced-motion preferences
    const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (prefersReduced) {
      // static fill — avoids burn-in and respects user preference
      const ctx = canvas.getContext('2d', { alpha: true });
      canvas.classList.add('reduced-motion');
      // will be filled by resize
      return;
    }

    const ctx = canvas.getContext('2d', { alpha: true });
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    let W = 0, H = 0;
    let particles = [];
    const N = 220;
    let running = false;
    let rafId = null;

    function resize() {
      const r = canvas.getBoundingClientRect();
      W = r.width; H = r.height;
      canvas.width = W * dpr;
      canvas.height = H * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      seedParticles();
    }

    function seedParticles() {
      particles = [];
      for (let i = 0; i < N; i++) {
        particles.push({
          x: Math.random() * W,
          y: Math.random() * H,
          vx: 0, vy: 0,
          life: Math.random() * 200,
          hue: i % 3,
        });
      }
    }

    const palette = [
      'rgba(91, 212, 255, ',  // cyan
      'rgba(79, 139, 255, ',  // azure
      'rgba(181, 140, 255, ', // violet
    ];

    let t = 0;
    function step() {
      if (!running) return;
      // fade previous frame — creates trails
      ctx.fillStyle = 'rgba(5, 8, 16, 0.10)';
      ctx.fillRect(0, 0, W, H);

      t += 0.005;

      for (const p of particles) {
        // map screen coordinates to flow domain
        const fx = p.x / W * 6;
        const fy = p.y / H * 4;
        const a = flow(fx, fy, t);
        p.vx = lerp(p.vx, Math.cos(a) * 0.6, 0.18);
        p.vy = lerp(p.vy, Math.sin(a) * 0.6, 0.18);
        p.x += p.vx;
        p.y += p.vy;
        p.life -= 1;

        // respawn off-screen or aged-out particles at random positions
        if (p.x < -10 || p.x > W + 10 || p.y < -10 || p.y > H + 10 || p.life <= 0) {
          p.x = Math.random() * W;
          p.y = Math.random() * H;
          p.life = 200 + Math.random() * 200;
          p.vx = 0; p.vy = 0;
        }

        const fade = clamp(p.life / 200, 0, 1) * 0.55;
        ctx.fillStyle = palette[p.hue] + fade.toFixed(3) + ')';
        ctx.beginPath();
        ctx.arc(p.x, p.y, 1.2, 0, TAU);
        ctx.fill();
      }
      rafId = requestAnimationFrame(step);
    }

    // pause when off-screen
    const visObs = new IntersectionObserver((entries) => {
      const entry = entries[0];
      if (entry.isIntersecting) {
        running = true;
        rafId = requestAnimationFrame(step);
      } else {
        running = false;
        if (rafId) cancelAnimationFrame(rafId);
      }
    }, { threshold: 0.05 });
    visObs.observe(canvas);

    const onResize = () => resize();
    window.addEventListener('resize', onResize, { passive: true });
    resize();
    running = true;
    rafId = requestAnimationFrame(step);
  }

  /* ────────────────────────── SCENARIO FANS ───────────────────────── */
  // Generate a stochastic ensemble that resembles paper Fig. 4
  // - demand: industrial diurnal profile + weekday/weekend modulation
  // - spot:   daily price band with peak hours
  // - pv:     daylight bell capped at ~0.55 kWh/kWp
  function buildEnsemble(kind, T = 168, S = 16, seed = 2026) {
    // T = 7 days at hourly resolution for visual clarity (paper uses 15-min)
    const scenarios = Array.from({ length: S }, (_, s) => {
      const rs = rng(seed + s * 7919);
      const out = new Float32Array(T);
      const dailyJitter = noise1D(seed * 13 + s, 8);
      for (let i = 0; i < T; i++) {
        const day = Math.floor(i / 24);
        const hour = i % 24;
        const dow = day % 7;
        const weekday = (dow < 5) ? 1.0 : 0.55;
        let v = 0;
        if (kind === 'demand') {
          // industrial weekday: ramp 6-9, steady 9-18, evening 18-22, low overnight
          const shape = 0.5
            + 0.25 * Math.cos((hour - 14) / 24 * TAU)   // afternoon peak
            + 0.18 * Math.exp(-Math.pow((hour - 11) / 6, 2));
          v = (500 + shape * 600 * weekday) * (0.92 + 0.10 * dailyJitter(day / 7) + 0.08 * (rs() - 0.5));
          v = clamp(v, 350, 1080);
        } else if (kind === 'spot') {
          // daily price: morning shoulder, evening peak band 18-22
          const peak = 0.55 * Math.exp(-Math.pow((hour - 20) / 2.4, 2));
          const morn = 0.20 * Math.exp(-Math.pow((hour - 9) / 3.2, 2));
          const base = 44 + 30 * (peak + morn) + 6 * dailyJitter(day / 7 + s * 0.13);
          v = base + 6 * (rs() - 0.5);
          v = clamp(v, 38, 78);
        } else { // pv
          // daylight bell, kWh/kWp ~ 0..0.6 with cloud noise
          const sun = Math.max(0, Math.sin(((hour - 6) / 12) * Math.PI));
          const cloud = 0.85 + 0.30 * dailyJitter(day / 7 + s * 0.21) - 0.20 * (rs() - 0.5);
          v = sun * 0.6 * clamp(cloud, 0.2, 1.0);
          v = clamp(v, 0, 0.62);
        }
        out[i] = v;
      }
      return out;
    });

    // compute pointwise percentiles
    const T_ = scenarios[0].length;
    const med = new Float32Array(T_);
    const p10 = new Float32Array(T_);
    const p90 = new Float32Array(T_);
    const mn = new Float32Array(T_);
    const mx = new Float32Array(T_);
    for (let i = 0; i < T_; i++) {
      const col = scenarios.map(s => s[i]).sort((a, b) => a - b);
      med[i] = col[Math.floor(col.length / 2)];
      p10[i] = col[Math.floor(col.length * 0.10)];
      p90[i] = col[Math.floor(col.length * 0.90)];
      mn[i] = col[0]; mx[i] = col[col.length - 1];
    }
    return { scenarios, med, p10, p90, mn, mx };
  }

  function renderFan(svgId, kind, palette) {
    const svg = document.getElementById(svgId);
    if (!svg) return;
    const T = 168;
    const ens = buildEnsemble(kind, T, 16, 2026 + (kind === 'spot' ? 11 : kind === 'pv' ? 23 : 0));
    const W = 400, H = 180, padL = 28, padR = 8, padT = 12, padB = 22;
    const innerW = W - padL - padR;
    const innerH = H - padT - padB;

    // y-domain from min/max
    let yMin = Infinity, yMax = -Infinity;
    for (let i = 0; i < T; i++) {
      yMin = Math.min(yMin, ens.mn[i]);
      yMax = Math.max(yMax, ens.mx[i]);
    }
    // pad
    yMax = yMax + (yMax - yMin) * 0.08;
    yMin = Math.max(0, yMin - (yMax - yMin) * 0.05);

    const xS = i => padL + (i / (T - 1)) * innerW;
    const yS = v => padT + innerH - ((v - yMin) / (yMax - yMin)) * innerH;

    // gridlines
    for (let k = 0; k < 4; k++) {
      const y = padT + (k / 3) * innerH;
      svg.appendChild(el('line', {
        x1: padL, x2: padL + innerW, y1: y, y2: y,
        stroke: '#1A2238', 'stroke-dasharray': '2 4', 'stroke-width': '0.5',
      }));
    }

    // y-axis ticks
    for (let k = 0; k <= 3; k++) {
      const v = lerp(yMin, yMax, 1 - k / 3);
      const y = padT + (k / 3) * innerH;
      const txt = el('text', {
        x: padL - 6, y: y + 3, fill: '#6A7488',
        'font-family': 'JetBrains Mono, monospace', 'font-size': 9, 'text-anchor': 'end',
      });
      txt.textContent = (kind === 'pv') ? v.toFixed(2) : Math.round(v);
      svg.appendChild(txt);
    }

    // x-axis ticks (days)
    for (let d = 0; d <= 7; d++) {
      const x = padL + (d * 24 / (T - 1)) * innerW;
      svg.appendChild(el('line', {
        x1: x, x2: x, y1: padT + innerH, y2: padT + innerH + 3,
        stroke: '#2A3656', 'stroke-width': '0.5',
      }));
      if (d % 1 === 0 && d > 0) {
        const txt = el('text', {
          x: x, y: H - 6, fill: '#6A7488',
          'font-family': 'JetBrains Mono, monospace', 'font-size': 9, 'text-anchor': 'middle',
        });
        txt.textContent = 'd' + d;
        svg.appendChild(txt);
      }
    }

    // outer min-max envelope (very faint)
    // NB: input arrays are Float32Arrays — convert to plain Array so .map() doesn't coerce strings back to Float32 (→ NaN)
    const pathPts = (arr) => Array.from(arr).map((v, i) => `${xS(i)},${yS(v)}`).join(' ');
    const envOuter = el('polygon', {
      points: pathPts(ens.mx) + ' ' + Array.from(ens.mn).reverse().map((v, i) => `${xS(T - 1 - i)},${yS(v)}`).join(' '),
      fill: palette.envOuter,
      opacity: '0.18',
    });
    svg.appendChild(envOuter);

    // p10-p90 band
    const envInner = el('polygon', {
      points: pathPts(ens.p90) + ' ' + Array.from(ens.p10).reverse().map((v, i) => `${xS(T - 1 - i)},${yS(v)}`).join(' '),
      fill: palette.envInner,
      opacity: '0.32',
    });
    svg.appendChild(envInner);

    // thin scenario traces
    ens.scenarios.forEach((sc, idx) => {
      const d = Array.from(sc).map((v, i) => `${i === 0 ? 'M' : 'L'}${xS(i)},${yS(v)}`).join(' ');
      svg.appendChild(el('path', {
        d, fill: 'none', stroke: palette.trace,
        'stroke-width': '0.5', opacity: '0.18',
      }));
    });

    // median line — bold
    const medD = Array.from(ens.med).map((v, i) => `${i === 0 ? 'M' : 'L'}${xS(i)},${yS(v)}`).join(' ');
    const medPath = el('path', {
      d: medD, fill: 'none', stroke: palette.median,
      'stroke-width': '1.6', 'stroke-linecap': 'round',
    });
    medPath.setAttribute('stroke-dasharray', '1500');
    medPath.setAttribute('stroke-dashoffset', '1500');
    svg.appendChild(medPath);
    // animate dash
    requestAnimationFrame(() => {
      medPath.style.transition = 'stroke-dashoffset 2.6s cubic-bezier(0.4, 0, 0.2, 1)';
      medPath.style.strokeDashoffset = '0';
    });

    // border
    svg.appendChild(el('rect', {
      x: padL, y: padT, width: innerW, height: innerH,
      fill: 'none', stroke: '#1A2238', 'stroke-width': '0.5',
    }));
  }

  /* ────────────────────────── CVaR sweep chart ───────────────────── */
  function renderCVaRChart() {
    const svg = document.getElementById('cvar-chart');
    if (!svg) return;
    // data from paper Fig 6 (Case 3 full-year): total cost (kUSD/y) vs β
    // and PV (MWp), BESS (MWh) capacity vs β
    const beta = [0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0];
    const cost = [520.4, 522.5, 525.4, 535.1, 565.8, 762.3, 1227.4];
    const pv = [1.86, 2.08, 2.29, 2.50, 2.70, 2.92, 3.06];
    const bessMWh = [0.000, 0.000, 0.000, 0.05, 0.12, 0.28, 0.40];

    const W = 420, H = 240, padL = 44, padR = 44, padT = 22, padB = 32;
    const innerW = W - padL - padR;
    const innerH = H - padT - padB;

    // dual-axis: left = cost, right = capacity
    const xMin = 0, xMax = 2;
    const yMinL = 500, yMaxL = 1250;
    const yMinR = 0, yMaxR = 3.5;
    const xS = v => padL + ((v - xMin) / (xMax - xMin)) * innerW;
    const yL = v => padT + innerH - ((v - yMinL) / (yMaxL - yMinL)) * innerH;
    const yR = v => padT + innerH - ((v - yMinR) / (yMaxR - yMinR)) * innerH;

    // grid
    for (let k = 0; k <= 4; k++) {
      const y = padT + (k / 4) * innerH;
      svg.appendChild(el('line', {
        x1: padL, x2: padL + innerW, y1: y, y2: y,
        stroke: '#1A2238', 'stroke-dasharray': '2 4', 'stroke-width': '0.5',
      }));
    }
    // y left ticks (cost)
    for (let k = 0; k <= 4; k++) {
      const v = lerp(yMinL, yMaxL, 1 - k / 4);
      const y = padT + (k / 4) * innerH;
      const t = el('text', {
        x: padL - 6, y: y + 3, fill: '#6A7488',
        'font-family': 'JetBrains Mono, monospace', 'font-size': 9, 'text-anchor': 'end',
      });
      t.textContent = Math.round(v);
      svg.appendChild(t);
    }
    // y right ticks (capacity)
    for (let k = 0; k <= 4; k++) {
      const v = lerp(yMinR, yMaxR, 1 - k / 4);
      const y = padT + (k / 4) * innerH;
      const t = el('text', {
        x: padL + innerW + 6, y: y + 3, fill: '#6A7488',
        'font-family': 'JetBrains Mono, monospace', 'font-size': 9, 'text-anchor': 'start',
      });
      t.textContent = v.toFixed(1);
      svg.appendChild(t);
    }
    // x ticks
    for (const b of beta) {
      const x = xS(b);
      svg.appendChild(el('line', {
        x1: x, x2: x, y1: padT + innerH, y2: padT + innerH + 3,
        stroke: '#2A3656', 'stroke-width': '0.5',
      }));
      const t = el('text', {
        x: x, y: H - 12, fill: '#6A7488',
        'font-family': 'JetBrains Mono, monospace', 'font-size': 9, 'text-anchor': 'middle',
      });
      t.textContent = b;
      svg.appendChild(t);
    }
    // axis labels
    const lbl = (x, y, txt, color, anchor = 'start') => {
      const t = el('text', {
        x, y, fill: color || '#A0AABF',
        'font-family': 'JetBrains Mono, monospace', 'font-size': 10,
        'text-anchor': anchor,
      });
      t.textContent = txt;
      svg.appendChild(t);
    };
    lbl(padL - 4, padT - 8, tr('chart.cost'), '#5BD4FF');
    lbl(padL + innerW, padT - 8, tr('chart.capacity'), '#FFB454', 'end');
    lbl(W / 2, H - 2, tr('chart.beta'), null, 'middle');

    // cost curve
    const costD = cost.map((v, i) => `${i === 0 ? 'M' : 'L'}${xS(beta[i])},${yL(v)}`).join(' ');
    svg.appendChild(el('path', {
      d: costD, fill: 'none', stroke: '#5BD4FF', 'stroke-width': '2',
      'stroke-linejoin': 'round',
    }));
    // shaded area under cost — subtle
    const areaD = `M${xS(beta[0])},${padT + innerH} ` +
      cost.map((v, i) => `L${xS(beta[i])},${yL(v)}`).join(' ') +
      ` L${xS(beta[beta.length - 1])},${padT + innerH} Z`;
    svg.appendChild(el('path', {
      d: areaD, fill: 'rgba(91, 212, 255, 0.08)', stroke: 'none',
    }));
    // PV curve
    const pvD = pv.map((v, i) => `${i === 0 ? 'M' : 'L'}${xS(beta[i])},${yR(v)}`).join(' ');
    svg.appendChild(el('path', {
      d: pvD, fill: 'none', stroke: '#FFB454', 'stroke-width': '1.5',
      'stroke-dasharray': '4 3',
    }));
    // BESS curve
    const bessD = bessMWh.map((v, i) => `${i === 0 ? 'M' : 'L'}${xS(beta[i])},${yR(v)}`).join(' ');
    svg.appendChild(el('path', {
      d: bessD, fill: 'none', stroke: '#B58CFF', 'stroke-width': '1.5',
      'stroke-dasharray': '1 3',
    }));

    // points
    cost.forEach((v, i) => svg.appendChild(el('circle', {
      cx: xS(beta[i]), cy: yL(v), r: 2.5, fill: '#5BD4FF',
    })));

    // legend
    const legendItems = [
      { c: '#5BD4FF', t: 'E[total]', x: padL + 8 },
      { c: '#FFB454', t: 'PV (MWp)', x: padL + 92 },
      { c: '#B58CFF', t: 'BESS (MWh)', x: padL + 180 },
    ];
    legendItems.forEach(li => {
      svg.appendChild(el('rect', {
        x: li.x, y: padT - 2, width: 12, height: 2, fill: li.c, rx: 1,
      }));
      const t = el('text', {
        x: li.x + 16, y: padT + 2, fill: '#A0AABF',
        'font-family': 'JetBrains Mono, monospace', 'font-size': 9,
      });
      t.textContent = li.t;
      svg.appendChild(t);
    });

    // Tooltip group
    const tooltipG = el('g', { class: 'chart-tooltip-group' });
    const tooltipRect = el('rect', { class: 'chart-tooltip-rect', x: 0, y: 0, width: 1, height: 1 });
    const tooltipTextL1 = el('text', { class: 'chart-tooltip-text', x: 0, y: 0 });
    const tooltipTextL2 = el('text', { class: 'chart-tooltip-text', x: 0, y: 0 });
    const tooltipTextL3 = el('text', { class: 'chart-tooltip-text', x: 0, y: 0 });
    tooltipG.append(tooltipRect, tooltipTextL1, tooltipTextL2, tooltipTextL3);
    svg.appendChild(tooltipG);

    function showTooltip(i, x, y) {
      const lines = [
        `β = ${beta[i]}`,
        `Cost: ${cost[i].toFixed(1)} kUSD/y`,
        `PV: ${pv[i].toFixed(2)} MWp   BESS: ${bessMWh[i].toFixed(2)} MWh`,
      ];
      const tw = 180, th = 58, tx = clamp(x - tw / 2, padL + 4, padL + innerW - tw - 4), ty = clamp(y - th - 10, padT + 4, padT + innerH - th - 4);
      tooltipRect.setAttribute('x', tx); tooltipRect.setAttribute('y', ty);
      tooltipRect.setAttribute('width', tw); tooltipRect.setAttribute('height', th);
      tooltipTextL1.setAttribute('x', tx + 10); tooltipTextL1.setAttribute('y', ty + 18);
      tooltipTextL1.textContent = lines[0];
      tooltipTextL2.setAttribute('x', tx + 10); tooltipTextL2.setAttribute('y', ty + 34);
      tooltipTextL2.textContent = lines[1];
      tooltipTextL3.setAttribute('x', tx + 10); tooltipTextL3.setAttribute('y', ty + 50);
      tooltipTextL3.textContent = lines[2];
      tooltipG.classList.add('active');
    }
    function hideTooltip() { tooltipG.classList.remove('active'); }

    // hit areas for each data point
    beta.forEach((b, i) => {
      const hx = xS(b), hy = yL(cost[i]);
      const hit = el('circle', { cx: hx, cy: hy, r: 12, fill: 'transparent', style: 'cursor:pointer' });
      hit.addEventListener('mouseenter', () => showTooltip(i, hx, hy));
      hit.addEventListener('mouseleave', hideTooltip);
      svg.appendChild(hit);
    });

    // border
    svg.appendChild(el('rect', {
      x: padL, y: padT, width: innerW, height: innerH,
      fill: 'none', stroke: '#1A2238', 'stroke-width': '0.5',
    }));
  }

  /* ────────────────────────── Results bar chart ──────────────────── */
  function renderResultsBars() {
    const svg = document.getElementById('results-bars');
    if (!svg) return;
    const rows = [
      { key: 'gudi',   label: tr('chart.bar.gudi'),       expected: 779.7, cvar: 779.9, hl: false },
      { key: 'detEV',  label: tr('chart.bar.detEV'),      expected: 520.7, cvar: 521.7, hl: false },
      { key: 'stormRN', label: tr('chart.bar.stormRN'),    expected: 520.4, cvar: 520.7, hl: true },
      { key: 'stormCVaR', label: tr('chart.bar.stormCVaR'),  expected: 525.4, cvar: 525.6, hl: true },
      { key: 'contracts', label: tr('chart.bar.contracts'),  expected: 626.7, cvar: 626.7, hl: false },
      { key: 'derOnly', label: tr('chart.bar.derOnly'),    expected: 551.0, cvar: 551.2, hl: false },
      { key: 'noDeg', label: tr('chart.bar.noDeg'),      expected: 525.5, cvar: 525.8, hl: false },
    ];
    const W = 520, H = 320;
    const padL = 56, padR = 12, padT = 16, padB = 70;
    const innerW = W - padL - padR;
    const innerH = H - padT - padB;
    const yMax = 850;
    const yS = v => padT + innerH - (v / yMax) * innerH;

    // y grid
    for (let k = 0; k <= 4; k++) {
      const v = (k / 4) * yMax;
      const y = yS(v);
      svg.appendChild(el('line', {
        x1: padL, x2: padL + innerW, y1: y, y2: y,
        stroke: '#1A2238', 'stroke-dasharray': '2 4', 'stroke-width': '0.5',
      }));
      const t = el('text', {
        x: padL - 6, y: y + 3, fill: '#6A7488',
        'font-family': 'JetBrains Mono, monospace', 'font-size': 9, 'text-anchor': 'end',
      });
      t.textContent = Math.round(v);
      svg.appendChild(t);
    }
    // axis label
    const axisLabel = el('text', {
      x: padL - 4, y: padT - 6, fill: '#A0AABF',
      'font-family': 'JetBrains Mono, monospace', 'font-size': 10,
    });
    axisLabel.textContent = tr('chart.kusdYear');
    svg.appendChild(axisLabel);

    const slot = innerW / rows.length;
    const barW = slot * 0.32;
    const gap = 2;

    rows.forEach((r, i) => {
      const cx = padL + slot * (i + 0.5);
      const expY = yS(r.expected);
      const cvY = yS(r.cvar);
      const baseY = padT + innerH;

      // expected bar
      const fill = r.hl
        ? 'url(#bar-hl)'
        : (r.key === 'gudi' ? '#3F4A60' : '#2A3656');
      const stroke = r.hl ? '#5BD4FF' : 'transparent';

      const expRect = el('rect', {
        x: cx - barW - gap, y: baseY, width: barW, height: 0,
        fill, stroke, 'stroke-width': r.hl ? '1' : '0',
        rx: 2,
      });
      svg.appendChild(expRect);
      requestAnimationFrame(() => {
        expRect.style.transition = `y 1s cubic-bezier(0.4, 0, 0.2, 1) ${0.05 * i}s, height 1s cubic-bezier(0.4, 0, 0.2, 1) ${0.05 * i}s`;
        expRect.setAttribute('y', expY);
        expRect.setAttribute('height', baseY - expY);
      });

      // cvar bar
      const cvFill = r.hl ? '#5BD4FF' : '#FFB454';
      const cvRect = el('rect', {
        x: cx + gap, y: baseY, width: barW, height: 0,
        fill: cvFill, opacity: 0.55, rx: 2,
      });
      svg.appendChild(cvRect);
      requestAnimationFrame(() => {
        cvRect.style.transition = `y 1s cubic-bezier(0.4, 0, 0.2, 1) ${0.05 * i + 0.1}s, height 1s cubic-bezier(0.4, 0, 0.2, 1) ${0.05 * i + 0.1}s`;
        cvRect.setAttribute('y', cvY);
        cvRect.setAttribute('height', baseY - cvY);
      });

      // value label
      const vl = el('text', {
        x: cx, y: expY - 6, fill: r.hl ? '#5BD4FF' : '#A0AABF',
        'font-family': 'JetBrains Mono, monospace', 'font-size': 9,
        'font-weight': r.hl ? 600 : 400, 'text-anchor': 'middle',
      });
      vl.textContent = r.expected.toFixed(1);
      svg.appendChild(vl);

      // category label — rotated so longer labels (STORM-CVaR) don't collide
      const labelY = padT + innerH + 12;
      const cl = el('text', {
        x: cx, y: labelY, fill: r.hl ? '#E6EDF7' : '#A0AABF',
        'font-family': 'Inter, sans-serif', 'font-size': 10,
        'font-weight': r.hl ? 600 : 400, 'text-anchor': 'end',
        transform: `rotate(-28, ${cx}, ${labelY})`,
      });
      cl.textContent = r.label;
      svg.appendChild(cl);
    });

    // gradient def for highlighted bars
    const defs = el('defs');
    const grad = el('linearGradient', { id: 'bar-hl', x1: 0, y1: 0, x2: 0, y2: 1 });
    [
      { offset: '0%', color: '#5BD4FF' },
      { offset: '100%', color: '#4F8BFF' },
    ].forEach(s => {
      const stop = el('stop', { offset: s.offset });
      stop.setAttribute('stop-color', s.color);
      grad.appendChild(stop);
    });
    defs.appendChild(grad);
    svg.appendChild(defs);

    // legend
    const lg = el('g', { transform: `translate(${padL + innerW - 160}, ${padT - 2})` });
    lg.appendChild(el('rect', { x: 0, y: -8, width: 10, height: 10, fill: '#5BD4FF', rx: 2 }));
    const lgT1 = el('text', { x: 14, y: 0, fill: '#A0AABF',
      'font-family': 'JetBrains Mono, monospace', 'font-size': 9 });
    lgT1.textContent = 'E[total]';
    lg.appendChild(lgT1);
    lg.appendChild(el('rect', { x: 76, y: -8, width: 10, height: 10, fill: '#FFB454', opacity: 0.55, rx: 2 }));
    const lgT2 = el('text', { x: 90, y: 0, fill: '#A0AABF',
      'font-family': 'JetBrains Mono, monospace', 'font-size': 9 });
    lgT2.textContent = 'CVaR₉₅';
    lg.appendChild(lgT2);
    svg.appendChild(lg);
  }

  /* ────────────────────────── KaTeX rendering ────────────────────── */
  function renderEquations() {
    if (typeof katex === 'undefined') {
      // KaTeX not yet loaded — retry once when it appears
      let tries = 0;
      const iv = setInterval(() => {
        if (typeof katex !== 'undefined' || tries++ > 30) {
          clearInterval(iv);
          if (typeof katex !== 'undefined') doRender();
        }
      }, 100);
      return;
    }
    doRender();

    function doRender() {
      document.querySelectorAll('[data-katex]').forEach(node => {
        try {
          katex.render(node.textContent.trim(), node, {
            displayMode: true,
            throwOnError: false,
            output: 'html',
            macros: {
              '\\spot': '\\text{spot}',
              '\\con': '\\text{con}',
            },
          });
        } catch (e) {
          console.warn('KaTeX render failed:', e);
        }
      });
    }
  }

  /* ────────────────────────── Copy buttons ─────────────────── */
  function initCopyButtons() {
    document.querySelectorAll('[data-copy-target]').forEach(btn => {
      btn.addEventListener('click', async () => {
        const targetId = btn.dataset.copyTarget;
        const target = document.getElementById(targetId);
        if (!target) return;
        try {
          await navigator.clipboard.writeText(target.textContent);
          const prev = btn.textContent;
          btn.textContent = 'Copied';
          btn.classList.add('copied');
          setTimeout(() => { btn.textContent = prev; btn.classList.remove('copied'); }, 2000);
        } catch (_) {
          btn.textContent = 'Error';
          setTimeout(() => { btn.textContent = 'Copy'; }, 2000);
        }
      });
    });
  }

  /* ────────────────────────── Scroll progress bar ──────────────── */
  function initScrollProgress() {
    const bar = document.querySelector('.scroll-progress > i');
    if (!bar) return;
    const update = () => {
      const scrollTop = window.scrollY || document.documentElement.scrollTop;
      const docHeight = document.documentElement.scrollHeight - document.documentElement.clientHeight;
      const pct = docHeight > 0 ? (scrollTop / docHeight) * 100 : 0;
      bar.style.width = pct + '%';
    };
    window.addEventListener('scroll', update, { passive: true });
    update();
  }

  /* ────────────────────────── Active section nav indicator ─────── */
  function initActiveNav() {
    const links = document.querySelectorAll('.nav-links a[href^="#"]');
    const sections = Array.from(links).map(a => {
      const id = a.getAttribute('href').slice(1);
      return document.getElementById(id);
    }).filter(Boolean);
    
    const obs = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          links.forEach(l => l.classList.remove('is-active'));
          const id = entry.target.id;
          const active = document.querySelector(`.nav-links a[href="#${id}"]`);
          if (active) active.classList.add('is-active');
        }
      });
    }, { threshold: 0.3, rootMargin: '-80px 0px -40% 0px' });

    sections.forEach(s => obs.observe(s));
  }

  /* ────────────────────────── Fade-in on scroll ─────────────────── */
  function initFadeIn() {
    const targets = document.querySelectorAll('.section, .hero-kpis, .workflow-stage, .app-card, .eq-card');
    targets.forEach(t => t.classList.add('fade-in'));

    const obs = new IntersectionObserver(entries => {
      entries.forEach(e => {
        if (e.isIntersecting) {
          e.target.classList.add('visible');
          obs.unobserve(e.target);
        }
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -60px 0px' });

    targets.forEach(t => obs.observe(t));
  }

  /* ────────────────────────── boot ────────────────────────────── */
  function renderAllCharts() {
    ['fan-demand', 'fan-spot', 'fan-pv', 'cvar-chart', 'results-bars'].forEach(clearSvg);
    renderFan('fan-demand', 'demand', {
      median: '#5BD4FF', trace: '#5BD4FF',
      envInner: '#5BD4FF', envOuter: '#5BD4FF',
    });
    renderFan('fan-spot', 'spot', {
      median: '#B58CFF', trace: '#B58CFF',
      envInner: '#B58CFF', envOuter: '#B58CFF',
    });
    renderFan('fan-pv', 'pv', {
      median: '#FFB454', trace: '#FFB454',
      envInner: '#FFB454', envOuter: '#FFB454',
    });
    renderCVaRChart();
    renderResultsBars();
  }

  function boot() {
    initHeroCanvas();
    renderAllCharts();
    renderEquations();
    initFadeIn();
    initScrollProgress();
    initActiveNav();
    initCopyButtons();
    // re-render charts when the user toggles EN/ES so axis labels update
    document.addEventListener('langchange', renderAllCharts);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
