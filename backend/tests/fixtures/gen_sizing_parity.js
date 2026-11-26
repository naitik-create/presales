// Runs the BOQ Generator's oo_sizing.js over seeded random inputs and records outputs (or errors).
global.window = {};
require(process.argv[2]);
const S = window.OOSizing;
let seed = 20261125;
const rnd = () => { seed = (seed + 0x6D2B79F5) | 0; let t = seed; t = Math.imul(t ^ (t >>> 15), t | 1);
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
const pick = a => a[Math.floor(rnd() * a.length)];
const maybe = (p, v) => (rnd() < p ? v : 0);
const HW = JSON.parse(process.argv[3]);
const cases = [];
for (let i = 0; i < Number(process.argv[4]); i++) {
  const oi = {
    devices: pick([0, 50, 100, 101, 250, 800, 1000, 1500, 2000, 2999, 3000, 3001, 4500, 5000, 5001, 8000, 10000, 10001]),
    log: rnd() < 0.5 ? {mode: pick(["gb", "src"]), value: pick([1, 5, 24, 30, 48, 75, 120, 200, 300, 600, 8, 26, 100, 150])} : {},
    flow: rnd() < 0.4 ? {mode: pick(["gb", "src"]), value: pick([2, 10, 16, 40, 64, 100, 200, 400, 30, 50, 51])} : {},
    apm: maybe(0.3, pick([1, 5, 6, 25, 60, 100, 101])), rum: maybe(0.2, pick([1, 3, 20, 200, 351])),
    nccm: maybe(0.3, pick([50, 300, 2500, 9000, 12000])), ping: maybe(0.2, pick([100, 800, 4000, 25000, 30000])),
  };
  if (rnd() < 0.35) oi.retention = {monitoring: {raw: pick([90, 180, 365]), agg: pick([365, 730])},
    log: {raw: pick([7, 30, 90]), agg: pick([180, 365])}, flow: {raw: pick([3, 7, 30]), agg: pick([90, 180])}};
  const sizeIn = Object.assign({}, oi, {isHA: rnd() < 0.3, observer: rnd() < 0.2});
  const hwIn = {architecture: pick(["standalone", "ha", "dc_dr", "ha_dr"]), observe: rnd() < 0.85, service: rnd() < 0.5,
    observeInput: oi, technicians: maybe(0.6, pick([3, 5, 15, 40, 100, 150])), assets: maybe(0.6, pick([500, 1000, 4000, 20000, 30000])),
    endpoints: maybe(0.6, pick([200, 1000, 3000, 9000, 15000])), vuln: rnd() < 0.4, sites: pick([0, 1, 3])};
  const run = f => { try { return {ok: f()}; } catch (e) { return {error: e.message}; } };
  cases.push({sizeIn, size: run(() => S.size(sizeIn)), hwIn, hw: run(() => S.hardwareSites(HW, hwIn))});
}
process.stdout.write(JSON.stringify(cases));
