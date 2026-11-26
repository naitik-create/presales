"""Motadata hardware sizing: a line-by-line Python port of the BOQ Generator's sizing
(motadata-boq static/js/oo_sizing.js, 172.16.12.103:5050, md5 12b2a0fc... read 2026-11-25).

* ObserveOps slabs and rules: copied by the BOQ Generator from the ObserveOps Suite hardware sizing page
  (172.16.12.77:8082/hardware-sizing). Edits made on that page do not flow here.
* ServiceOps tables: the BOQ Generator's hw_sizing defaults (the product team's sizing Excel).
* Vulnerability + Patch server: docs.motadata.com system requirements (Standalone).

Keep this file identical in behaviour to the JS: tests/test_sizing_engine.py holds parity cases produced by running
the JS. Pure functions only; no database or AI.
"""
from __future__ import annotations

import copy
import math

SLABS: dict[str, dict[str, dict]] = {
    "monitoring": {
        "M1": {"masterCpu": 8, "masterRam": 8, "masterDisk": 180, "masterIops": 200, "dataCpu": "N/A", "dataRam": "N/A", "dataDisk": "N/A", "dataIops": "N/A", "collectorCount": 0, "observerCpu": 4, "observerRam": 8},
        "M2": {"masterCpu": 8, "masterRam": 8, "masterDisk": 250, "masterIops": 200, "dataCpu": "N/A", "dataRam": "N/A", "dataDisk": "N/A", "dataIops": "N/A", "collectorCount": 0, "observerCpu": 4, "observerRam": 8},
        "M3": {"masterCpu": 12, "masterRam": 12, "masterDisk": 370, "masterIops": 200, "dataCpu": "N/A", "dataRam": "N/A", "dataDisk": "N/A", "dataIops": "N/A", "collectorCount": 0, "observerCpu": 4, "observerRam": 8},
        "M4": {"masterCpu": 16, "masterRam": 16, "masterDisk": 580, "masterIops": 250, "dataCpu": "N/A", "dataRam": "N/A", "dataDisk": "N/A", "dataIops": "N/A", "collectorCount": 0, "observerCpu": 4, "observerRam": 8},
        "M5": {"masterCpu": 16, "masterRam": 16, "masterDisk": 790, "masterIops": 250, "dataCpu": "N/A", "dataRam": "N/A", "dataDisk": "N/A", "dataIops": "N/A", "collectorCount": 0, "observerCpu": 4, "observerRam": 8},
        "M6": {"masterCpu": 16, "masterRam": 24, "masterDisk": 1430, "masterIops": 250, "dataCpu": "N/A", "dataRam": "N/A", "dataDisk": "N/A", "dataIops": "N/A", "collectorCount": 0, "observerCpu": 4, "observerRam": 8},
        "M7": {"masterCpu": 16, "masterRam": 24, "masterDisk": 300, "masterIops": 300, "dataCpu": 16, "dataRam": 24, "dataDisk": 2290, "dataIops": 300, "collectorCpu": 16, "collectorRam": 16, "collectorCount": 1, "observerCpu": 4, "observerRam": 8},
        "M8": {"masterCpu": 24, "masterRam": 32, "masterDisk": 350, "masterIops": 350, "dataCpu": 24, "dataRam": 36, "dataDisk": 4420, "dataIops": 300, "collectorCpu": 16, "collectorRam": 16, "collectorCount": 2, "observerCpu": 4, "observerRam": 12},
    },
    "log": {
        "L1": {"metric": 590, "masterCpu": 2, "masterRam": 2, "masterDisk": 75, "dataCpu": 4, "dataRam": 8, "dataDisk": 250, "collectorCount": 0},
        "L2": {"metric": 1520, "masterCpu": 6, "masterRam": 6, "masterDisk": 195, "dataCpu": 14, "dataRam": 24, "dataDisk": 650, "collectorCount": 0},
        "L3": {"metric": 2950, "masterCpu": 8, "masterRam": 8, "masterDisk": 360, "dataCpu": 16, "dataRam": 32, "dataDisk": 1200, "collectorCpu": 12, "collectorRam": 12, "collectorCount": 1},
        "L4": {"metric": 5900, "masterCpu": 12, "masterRam": 10, "masterDisk": 720, "dataCpu": 24, "dataRam": 48, "dataDisk": 2400, "collectorCpu": 12, "collectorRam": 12, "collectorCount": 2},
        "L5": {"metric": 11800, "masterCpu": 16, "masterRam": 14, "masterDisk": 1440, "dataCpu": 32, "dataRam": 64, "dataDisk": 4800, "collectorCpu": 16, "collectorRam": 16, "collectorCount": 2},
    },
    "flow": {
        "F1": {"metric": 2330, "masterCpu": 12, "masterRam": 16, "masterDisk": 225, "dataCpu": 14, "dataRam": 24, "dataDisk": 750, "collectorCount": 0},
        "F2": {"metric": 5980, "masterCpu": 16, "masterRam": 16, "masterDisk": 600, "dataCpu": 20, "dataRam": 36, "dataDisk": 1900, "collectorCpu": 12, "collectorRam": 12, "collectorCount": 1},
        "F3": {"metric": 11650, "masterCpu": 24, "masterRam": 24, "masterDisk": 1140, "dataCpu": 24, "dataRam": 48, "dataDisk": 3710, "collectorCpu": 12, "collectorRam": 12, "collectorCount": 2},
    },
    "apm": {
        "A1": {"masterCpu": 4, "masterRam": 6, "masterDisk": 10, "dataCpu": 8, "dataRam": 12, "dataDisk": 30, "collectorCount": 0},
        "A2": {"masterCpu": 6, "masterRam": 8, "masterDisk": 15, "dataCpu": 10, "dataRam": 14, "dataDisk": 50, "collectorCount": 0},
        "A3": {"masterCpu": 12, "masterRam": 16, "masterDisk": 40, "dataCpu": 14, "dataRam": 18, "dataDisk": 120, "collectorCount": 0},
        "A4": {"masterCpu": 16, "masterRam": 24, "masterDisk": 45, "dataCpu": 18, "dataRam": 24, "dataDisk": 130, "collectorCount": 0},
        "A5": {"masterCpu": 20, "masterRam": 32, "masterDisk": 78, "dataCpu": 24, "dataRam": 32, "dataDisk": 260, "collectorCount": 0},
    },
    "rum": {
        "R1": {"sessionsDay": 25000, "masterCpu": 2, "masterRam": 2, "masterDisk": 2, "dataCpu": 2, "dataRam": 2, "dataDisk": 5, "collectorCount": 0},
        "R2": {"sessionsDay": 50000, "masterCpu": 2, "masterRam": 2, "masterDisk": 2, "dataCpu": 2, "dataRam": 2, "dataDisk": 5, "collectorCount": 0},
        "R3": {"sessionsDay": 100000, "masterCpu": 4, "masterRam": 4, "masterDisk": 2, "dataCpu": 4, "dataRam": 4, "dataDisk": 5, "collectorCount": 0},
        "R4": {"sessionsDay": 250000, "masterCpu": 4, "masterRam": 4, "masterDisk": 2, "dataCpu": 4, "dataRam": 4, "dataDisk": 5, "collectorCount": 0},
        "R5": {"sessionsDay": 500000, "masterCpu": 4, "masterRam": 4, "masterDisk": 3, "dataCpu": 4, "dataRam": 6, "dataDisk": 10, "collectorCount": 0},
        "R6": {"sessionsDay": 1000000, "masterCpu": 6, "masterRam": 6, "masterDisk": 5, "dataCpu": 8, "dataRam": 12, "dataDisk": 15, "collectorCount": 0},
        "R7": {"sessionsDay": 2500000, "masterCpu": 8, "masterRam": 8, "masterDisk": 11, "dataCpu": 12, "dataRam": 16, "dataDisk": 35, "collectorCount": 0},
        "R8": {"sessionsDay": 5000000, "masterCpu": 12, "masterRam": 12, "masterDisk": 21, "dataCpu": 16, "dataRam": 24, "dataDisk": 70, "collectorCount": 0},
    },
    "nccm": {
        "N1": {"masterCpu": 1, "masterRam": 2, "masterDisk": 5, "dataCpu": 0, "dataRam": 0, "dataDisk": 5, "collectorCount": 0},
        "N2": {"masterCpu": 1, "masterRam": 2, "masterDisk": 5, "dataCpu": 0, "dataRam": 0, "dataDisk": 7, "collectorCount": 0},
        "N3": {"masterCpu": 2, "masterRam": 2, "masterDisk": 5, "dataCpu": 0, "dataRam": 0, "dataDisk": 10, "collectorCount": 0},
        "N4": {"masterCpu": 2, "masterRam": 2, "masterDisk": 5, "dataCpu": 0, "dataRam": 0, "dataDisk": 13, "collectorCount": 0},
        "N5": {"masterCpu": 2, "masterRam": 2, "masterDisk": 5, "dataCpu": 0, "dataRam": 0, "dataDisk": 15, "collectorCount": 0},
        "N6": {"masterCpu": 4, "masterRam": 4, "masterDisk": 5, "dataCpu": 0, "dataRam": 0, "dataDisk": 25, "collectorCount": 0},
        "N7": {"masterCpu": 4, "masterRam": 6, "masterDisk": 5, "dataCpu": 0, "dataRam": 0, "dataDisk": 35, "collectorCount": 0},
        "N8": {"masterCpu": 6, "masterRam": 6, "masterDisk": 5, "dataCpu": 0, "dataRam": 0, "dataDisk": 50, "collectorCount": 0},
    },
    "ping": {
        "P1": {"masterCpu": 2, "masterRam": 2, "masterDisk": 4, "dataCpu": 2, "dataRam": 2, "dataDisk": 100, "collectorCount": 0},
        "P2": {"masterCpu": 2, "masterRam": 4, "masterDisk": 5, "dataCpu": 2, "dataRam": 4, "dataDisk": 300, "collectorCount": 0},
        "P3": {"masterCpu": 4, "masterRam": 4, "masterDisk": 7, "dataCpu": 4, "dataRam": 4, "dataDisk": 512, "collectorCount": 0},
        "P4": {"masterCpu": 6, "masterRam": 10, "masterDisk": 10, "dataCpu": 4, "dataRam": 6, "dataDisk": 1024, "collectorCpu": 8, "collectorRam": 8, "collectorCount": 1},
        "P5": {"masterCpu": 8, "masterRam": 10, "masterDisk": 10, "dataCpu": 8, "dataRam": 10, "dataDisk": 2048, "collectorCpu": 16, "collectorRam": 16, "collectorCount": 1},
        "P6": {"masterCpu": 12, "masterRam": 16, "masterDisk": 10, "dataCpu": 16, "dataRam": 20, "dataDisk": 5222, "collectorCpu": 16, "collectorRam": 16, "collectorCount": 2},
    },
}

DIMS = {
    "monitoring": {"label": "Monitoring", "unit": "devices", "code": "M", "max": [100, 250, 500, 1000, 1500, 3000, 5000, 10000]},
    "log": {"label": "Log", "unit": "log sources", "code": "L", "max": [10, 25, 50, 100, 200]},
    "flow": {"label": "Flow", "unit": "flow sources", "code": "F", "max": [10, 25, 50]},
    "apm": {"label": "APM", "unit": "APM units", "code": "A", "max": [5, 10, 25, 50, 100]},
    "rum": {"label": "RUM", "unit": "front-end apps", "code": "R", "max": [2, 5, 10, 25, 50, 100, 200, 350]},
    "nccm": {"label": "NCCM", "unit": "NCCM devices", "code": "N", "max": [100, 250, 500, 1000, 1500, 3000, 5000, 10000]},
    "ping": {"label": "Ping", "unit": "ping targets", "code": "P", "max": [500, 1000, 2500, 5000, 10000, 25000]},
}

# Slab default retention (days), used when no custom retention is set
RETENTION = {
    "monitoring": {"raw": 365, "agg": 365, "label": "Monitoring"},
    "log": {"raw": 30, "agg": 180, "label": "Logs"},
    "flow": {"raw": 7, "agg": 180, "label": "Flows"},
    "apm": {"raw": 2, "agg": 2, "label": "APM"},
    "rum": {"raw": 2, "agg": 2, "label": "RUM"},
    "ping": {"raw": 365, "agg": 365, "label": "Ping"},
}

GB = 1073741824
BYTES_PER_EVENT = {"log": 600, "flow": 400}
EPS_PER_SOURCE = {"log": 59, "flow": 233}
SINGLE_BOX_MAX_VCPU = 32
ARCHITECT = "engage a Solution Architect for this sizing"

# ServiceOps Vulnerability + Patch server, from docs.motadata.com system requirements (Standalone)
VULN_PATCH = [
    {"me": 1000, "c": 12, "r": 20, "k": 375},
    {"me": 5000, "c": 24, "r": 40, "k": 625},
    {"me": 10000, "c": 48, "r": 80, "k": 625},
]

# ServiceOps tables (BOQ Generator hw_sizing defaults v1.0, from the product team's sizing Excel)
SERVICEOPS_TABLES = {
    "ASSET": [{"ma": 1000, "c": 4, "r": 8, "k": 200}, {"ma": 5000, "c": 8, "r": 16, "k": 500},
              {"ma": 10000, "c": 16, "r": 32, "k": 1000}, {"ma": 25000, "c": 32, "r": 64, "k": 1000}],
    "SOPS_COMBO": [{"mt": 5, "ma": 1000, "c": 8, "r": 12, "k": 500}, {"mt": 20, "ma": 5000, "c": 12, "r": 24, "k": 500},
                   {"mt": 50, "ma": 10000, "c": 24, "r": 48, "k": 1024}, {"mt": 100, "ma": 25000, "c": 48, "r": 96, "k": 1024}],
    "SOPS_HELP": [{"mt": 5, "c": 4, "r": 8, "k": 200}, {"mt": 20, "c": 8, "r": 16, "k": 500},
                  {"mt": 50, "c": 16, "r": 32, "k": 1024}, {"mt": 100, "c": 32, "r": 64, "k": 1024}],
    "PATCH": [{"me": 1000, "c": 8, "r": 16, "k": 300}, {"me": 5000, "c": 16, "r": 32, "k": 500},
              {"me": 10000, "c": 32, "r": 64, "k": 500}],
    "FSERV": [{"me": 1000, "c": 4, "r": 8, "k": 500}, {"me": 5000, "c": 4, "r": 8, "k": 1024},
              {"me": 10000, "c": 8, "r": 16, "k": 1024}],
}


class SizingError(ValueError):
    """Inputs beyond the sizing tables: the message says to engage a Solution Architect."""


def _num(v):
    """JS toNum: missing -> None, number -> number, anything else ("N/A") -> 0."""
    if v is None:
        return None
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else 0


def _n0(v) -> float:
    return _num(v) or 0


def _round(x: float) -> int:
    """JS Math.round (halves round up)."""
    return math.floor(x + 0.5)


def _pos(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0


def _fmt(n) -> str:
    """JS toLocaleString() in en-US for whole numbers."""
    return f"{n:,}" if float(n).is_integer() else f"{n:,.3f}".rstrip("0").rstrip(".")


def _slab_for(dim: str, count) -> str:
    d = DIMS[dim]
    for i, m in enumerate(d["max"]):
        if count <= m:
            return d["code"] + str(i + 1)
    raise SizingError(f"More than {_fmt(d['max'][-1])} {d['unit']}: {ARCHITECT}.")


def _slab_for_eps(dim: str, eps: float) -> str:
    rows = SLABS[dim]
    for code, row in rows.items():
        if eps <= row["metric"]:
            return code
    last = list(rows)[-1]
    raise SizingError(f"{DIMS[dim]['label']} volume above {_fmt(rows[last]['metric'])} EPS: {ARCHITECT}.")


def _eps_from_gb(dim: str, gb: float) -> float:
    return gb * GB / 86400 / BYTES_PER_EVENT[dim]


def _custom_disk_gb(dim: str, count, ret: dict, eps):
    raw, agg = ret["raw"], ret["agg"]
    if dim == "monitoring":
        return count * (raw * 1048576 + agg * 204800) / GB + 150
    if dim in ("log", "flow"):
        return eps * 86400 * (raw * 50 + agg * 20) / GB
    if dim == "apm":
        return count * 250 * 86400 * (raw * 80 + agg * 30) / GB
    if dim == "rum":
        return eps * 100 * (raw * 50 + agg * 20) / GB  # eps carries sessions/day here
    if dim == "ping":
        return count * (raw * 512000 + agg * 102400) / GB
    return None


def _master_base_gb(devices) -> int:
    if devices <= 5000:
        return 250
    if devices <= 10000:
        return 350
    return 550


def size(inp: dict) -> dict:
    """ObserveOps sizing. inp: {devices, log: {mode: "gb"|"src", value}, flow: {...}, apm, rum, nccm, ping,
    isHA, observer, retention: None | {monitoring: {raw, agg}, log: {...}, ...}}"""
    devices = inp.get("devices") or 0
    is_ha = bool(inp.get("isHA"))
    custom = inp.get("retention") or None
    base_topology = "single" if devices <= 3000 else "dist" if devices <= 5000 else "ha"

    matches: list[dict] = []

    def add(dim, count, code, **extra):
        matches.append({"dim": dim, "count": count, "code": code, "spec": copy.deepcopy(SLABS[dim][code]), **extra})

    if devices > 0:
        add("monitoring", devices, _slab_for("monitoring", devices))
    for dim in ("log", "flow"):
        f = inp.get(dim) or {}
        if not _pos(f.get("value")):
            continue
        if f.get("mode") == "src":
            add(dim, f["value"], _slab_for(dim, f["value"]))
            continue
        eps = _eps_from_gb(dim, f["value"])
        add(dim, f["value"], _slab_for_eps(dim, eps), eps=eps)
    for dim in ("apm", "rum", "nccm", "ping"):
        if _pos(inp.get(dim)):
            add(dim, inp[dim], _slab_for(dim, inp[dim]))

    # Storage override (custom retention, or GB/day entry) and proportional compute for GB/day
    for m in matches:
        direct = "eps" in m
        ret = RETENTION.get(m["dim"])
        if not ret or not (custom or direct):
            continue
        use = (custom and custom.get(m["dim"])) or ret
        if direct:
            eps = m["eps"]
        elif m["dim"] == "rum":
            eps = m["spec"]["sessionsDay"]
        elif m["dim"] in ("log", "flow"):
            eps = m["count"] * EPS_PER_SOURCE[m["dim"]]
        else:
            eps = 0
        gb = _custom_disk_gb(m["dim"], m["count"], use, eps)
        spec = m["spec"]
        if m["dim"] == "monitoring":
            if base_topology == "single":
                spec["masterDisk"], spec["dataDisk"] = gb, 0
            else:
                spec["dataDisk"] = gb
        else:
            spec["dataDisk"] = gb
            spec["masterDisk"] = gb * 0.3
        if direct:
            p = min(1, m["eps"] / spec["metric"])
            idx = int(m["code"][1:])
            prev = SLABS[m["dim"]][m["code"][0] + str(idx - 1)] if idx > 1 else None
            for node in ("master", "data"):
                for metric in ("Cpu", "Ram"):
                    key = node + metric
                    v = max(1, math.ceil(spec[key] * p))
                    if prev and v < prev[key]:
                        v = prev[key]
                    spec[key] = v
            if spec["collectorCount"] > 0:
                spec["collectorCount"] = max(1, _round(spec["collectorCount"] * p))

    # Single-box is limited to 32 combined vCPU; beyond that it goes distributed
    raw_vcpu = 0
    if base_topology == "single":
        for m in matches:
            raw_vcpu += _n0(m["spec"].get("masterCpu")) + _n0(m["spec"].get("dataCpu"))
    cpu_forced = base_topology == "single" and raw_vcpu > SINGLE_BOX_MAX_VCPU
    topology = "dist" if cpu_forced else base_topology

    # Distributed without dedicated Data specs: Master 50%, Data 70% of the Master figure
    mon_match = next((m for m in matches if m["dim"] == "monitoring"), None)
    mon = mon_match["spec"] if mon_match else None
    if mon and topology != "single" and mon["dataCpu"] == "N/A":
        for metric in ("Cpu", "Ram"):
            v = mon["master" + metric]
            mon["master" + metric] = math.ceil(v * 0.5)
            mon["data" + metric] = math.ceil(v * 0.7)
        mon["dataIops"] = mon["masterIops"]

    def total(key):
        s = 0
        for m in matches:
            s = s + _n0(m["spec"].get(key))
        return s

    addon_master_gb = 0
    for m in matches:
        if m["dim"] not in ("monitoring", "ping"):
            addon_master_gb = addon_master_gb + _n0(m["spec"].get("masterDisk"))
    ping = inp.get("ping")
    effective_devices = devices + (ping if _pos(ping) else 0)
    headroom = effective_devices * 7 * 1.5 / 1024 if is_ha else 0

    datastore = None
    if topology == "single":
        master = {"c": total("masterCpu") + total("dataCpu"), "r": total("masterRam") + total("dataRam"),
                  "k": math.ceil(total("masterDisk") + total("dataDisk") + headroom)}
    else:
        master = {"c": total("masterCpu"), "r": total("masterRam"),
                  "k": math.ceil(addon_master_gb + _master_base_gb(effective_devices) + headroom)}
        datastore = {"c": total("dataCpu"), "r": total("dataRam"), "k": math.ceil(total("dataDisk"))}

    # One collector row per dimension: specs differ between modules
    collectors = [{"dim": DIMS[m["dim"]]["label"], "slab": m["code"], "n": m["spec"]["collectorCount"],
                   "c": m["spec"].get("collectorCpu"), "r": m["spec"].get("collectorRam"), "k": 150}
                  for m in matches if m["spec"]["collectorCount"] > 0]

    def slab(dim):
        return next((m["code"] for m in matches if m["dim"] == dim), None)

    def event_rate(dim):
        m = next((x for x in matches if x["dim"] == dim), None)
        if not m:
            return None
        return _round(m["eps"] if "eps" in m else m["spec"]["metric"])

    def event_gb(dim):
        m = next((x for x in matches if x["dim"] == dim), None)
        if not m:
            return None
        if "eps" in m:
            return m["count"]
        return _round(event_rate(dim) * 86400 * BYTES_PER_EVENT[dim] / GB * 10) / 10

    label = {"single": "Single-Box", "dist": "Distributed", "ha": "Distributed + HA"}[topology]
    mon_slab = SLABS["monitoring"][slab("monitoring") or "M1"]
    slabs = []
    for m in matches:
        row = {"dim": DIMS[m["dim"]]["label"], "code": m["code"], "count": m["count"], "unit": DIMS[m["dim"]]["unit"],
               "c": _num(m["spec"].get("masterCpu")), "r": _num(m["spec"].get("masterRam"))}
        if "eps" in m:
            row["eps"] = m["eps"]
        slabs.append(row)
    retention_text = ", ".join(
        f"{RETENTION[m['dim']]['label']} {r['raw']}d raw / {r['agg']}d aggregated"
        for m in matches if m["dim"] in RETENTION
        for r in [(custom and custom.get(m["dim"])) or RETENTION[m["dim"]]])
    return {
        "master": master, "datastore": datastore, "collectors": collectors,
        "observer": ({"c": mon_slab["observerCpu"], "r": mon_slab["observerRam"], "k": 150}
                     if (is_ha or inp.get("observer")) else None),
        "eventRates": {"log": event_rate("log"), "flow": event_rate("flow")},
        "eventGb": {"log": event_gb("log"), "flow": event_gb("flow")},
        "hasDS": datastore is not None, "topology": topology, "topologyLabel": label, "cpuForced": cpu_forced,
        "haRecommended": devices > 5000 and not is_ha,
        "io": f"≥{mon['masterIops']} MBps" if mon else "",
        "tl": f"{slab('monitoring')} ({_fmt(devices)} devices)" if mon else "No monitoring",
        "slabs": slabs,
        "retentionText": retention_text,
    }


def _fit(value, table: list[dict], key: str) -> dict:
    """Smallest table row that fits the value; the largest row beyond the table."""
    rows = sorted(table, key=lambda x: x[key])
    return next((x for x in rows if value <= x[key]), rows[-1])


def service_ops(hw: dict, inp: dict) -> dict:
    """ServiceOps rows, same rules as computeBoQ in the BOQ Generator. hw: SERVICEOPS_TABLES (or an uploaded copy)."""
    tech, assets, endpoints = inp.get("technicians"), inp.get("assets"), inp.get("endpoints")
    main = None
    if tech or assets:
        if not tech:
            main = _fit(assets, hw["ASSET"], "ma")
        elif not assets:
            main = _fit(tech, hw["SOPS_HELP"], "mt")
        else:
            by_tech, by_asset = _fit(tech, hw["SOPS_COMBO"], "mt"), _fit(assets, hw["ASSET"], "ma")
            main = by_tech if by_tech["c"] >= by_asset["c"] else by_asset
    patch = _fit(endpoints, VULN_PATCH if inp.get("vuln") else hw["PATCH"], "me") if _pos(endpoints) else None
    file = _fit(endpoints, hw["FSERV"], "me") if _pos(endpoints) else None
    server = None
    if main and patch:
        server = {"n": "Motadata ServiceOps", "q": 1, "c": main["c"] + patch["c"], "r": main["r"] + patch["r"],
                  "k": main["k"] + patch["k"]}
    elif main:
        server = {"n": "Motadata ServiceOps", "q": 1, "c": main["c"], "r": main["r"], "k": main["k"]}
    elif patch:
        server = {"n": "Patch & Vulnerability Management Server" if inp.get("vuln") else "Patch Management Server",
                  "q": 1, "c": patch["c"], "r": patch["r"], "k": patch["k"]}
    return {
        "server": server,
        "fileServer": ({"n": "Motadata File Server (Win/Linux)", "q": max(1, inp.get("sites") or 1),
                        "c": file["c"], "r": file["r"], "k": file["k"]} if file else None),
    }


def hardware_sites(hw: dict, inp: dict) -> dict:
    """Hardware rows per site. inp.architecture: standalone | ha | dc_dr | ha_dr; inp.observe / inp.service;
    inp.observeInput for size(); technicians, assets, endpoints, vuln, sites for ServiceOps."""
    arch = inp.get("architecture")
    is_ha = arch in ("ha", "ha_dr")
    is_dr = arch in ("dc_dr", "ha_dr")
    is_dcdr = arch == "dc_dr"  # HA between DC and DR: ObserveOps Observer at DR
    oo = size({**(inp.get("observeInput") or {}), "isHA": is_ha, "observer": is_ha or is_dcdr}) if inp.get("observe") else None
    so = service_ops(hw, inp) if inp.get("service") else None

    nodes = []
    if oo:
        nodes.append({"n": "Motadata ObserveOps Master" if oo["hasDS"] else "Motadata ObserveOps Master - App + Data Node",
                      "q": 1, **oo["master"]})
        if oo["datastore"]:
            nodes.append({"n": "Motadata ObserveOps Data Node", "q": 1, **oo["datastore"]})
    collectors = [{"n": f"Motadata Collector - {c['dim']}", "q": c["n"], "c": c["c"], "r": c["r"], "k": c["k"]}
                  for c in oo["collectors"]] if oo else []
    service_nodes = [so["server"]] if so and so["server"] else []
    file_rows = [so["fileServer"]] if so and so["fileServer"] else []

    observers = []
    if is_ha:
        if oo:
            observers.append({"n": "Motadata Observer Utility (ObserveOps)" if so else "Motadata Observer Utility", "q": 1,
                              **oo["observer"]})
        if so:
            observers.append({"n": "Motadata Observer Utility (ServiceOps)" if oo else "Motadata Observer Utility", "q": 1,
                              "c": 4, "r": 4, "k": 100})
    elif is_dcdr and oo:
        observers.append({"n": "Motadata Observer Utility (ObserveOps)" if so else "Motadata Observer Utility", "q": 1,
                          **oo["observer"]})

    sites = [{"title": "PRODUCTION DC SITE - ACTIVE SETUP", "rows": [*nodes, *collectors, *service_nodes, *file_rows]}]
    if is_ha:
        sites.append({"title": "PRODUCTION DC SITE - STANDBY SETUP", "rows": [*nodes, *service_nodes, *([] if is_dr else observers)]})
    if is_dr:
        sites.append({"title": "PRODUCTION DR SITE - HA SETUP" if is_dcdr else "PRODUCTION DR SITE - STANDALONE SETUP",
                      "rows": [*nodes, *collectors, *service_nodes, *observers]})
    return {"sites": sites, "retentionText": oo["retentionText"] if oo else ""}
