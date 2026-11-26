"""From the sizing inputs the architecture agent reads in the RFP to Motadata hardware rows (sizing_engine).
Pure functions: the agent only extracts numbers with references; every hardware figure comes from the engine."""
from __future__ import annotations

from app.modules.rfp import sizing_engine as E

# name -> (label, product). The architecture agent extracts these; anything else it notes as an assumption.
INPUTS: dict[str, tuple[str, str]] = {
    "devices": ("Monitored devices (network devices, servers, VMs, databases, apps)", "ObserveOps"),
    "log_gb_per_day": ("Log volume (GB per day)", "ObserveOps"),
    "log_eps": ("Log events per second (EPS)", "ObserveOps"),
    "log_sources": ("Log sources", "ObserveOps"),
    "flows_per_sec": ("Flows per second (FPS)", "ObserveOps"),
    "flow_sources": ("Flow-exporting devices", "ObserveOps"),
    "apm_apps": ("APM units (applications / app servers)", "ObserveOps"),
    "rum_apps": ("Front-end applications for real user monitoring", "ObserveOps"),
    "ncm_devices": ("Configuration-managed (NCM) devices", "ObserveOps"),
    "ping_targets": ("Ping / availability-only targets", "ObserveOps"),
    "technicians": ("Service desk technicians / agents", "ServiceOps"),
    "assets": ("Managed assets (ITAM / CMDB)", "ServiceOps"),
    "endpoints": ("Patch-managed endpoints", "ServiceOps"),
    "vulnerability": ("Vulnerability management required (1 = yes)", "ServiceOps"),
    "sites": ("Sites / branches needing a file server", "ServiceOps"),
    "ha": ("High availability required at DC (1 = yes)", "Both"),
    "dr": ("DR site required (1 = yes)", "Both"),
    "log_retention_days": ("Log retention asked by the RFP (days)", "ObserveOps"),
    "monitoring_retention_days": ("Performance data retention asked by the RFP (days)", "ObserveOps"),
}

OBSERVE_KEYS = ("devices", "log_gb_per_day", "log_eps", "log_sources", "flows_per_sec", "flow_sources", "apm_apps",
                "rum_apps", "ncm_devices", "ping_targets")
SERVICE_KEYS = ("technicians", "assets", "endpoints")


def clean_inputs(items: list[dict]) -> list[dict]:
    """One entry per known input name, first stated value wins (windows of a long RFP may repeat them)."""
    seen: dict[str, dict] = {}
    for it in items or []:
        name = it.get("name")
        if name in INPUTS and name not in seen and isinstance(it.get("value"), (int, float)) and it["value"] >= 0:
            seen[name] = {"name": name, "label": INPUTS[name][0], "value": it["value"], "ref": it.get("ref", ""),
                          "note": it.get("note", "")}
    return [seen[n] for n in INPUTS if n in seen]


def engine_input(values: dict, products: list[str]) -> tuple[dict, list[str]]:
    """Map named values to hardware_sites() input. Returns (input, notes explaining each conversion)."""
    v = {k: values.get(k) or 0 for k in INPUTS}
    notes: list[str] = []
    gb = E.GB
    log: dict = {}
    if v["log_gb_per_day"] > 0:
        log = {"mode": "gb", "value": v["log_gb_per_day"]}
    elif v["log_eps"] > 0:
        log = {"mode": "gb", "value": round(v["log_eps"] * 86400 * E.BYTES_PER_EVENT["log"] / gb, 2)}
        notes.append(f"Log volume {log['value']} GB/day from {v['log_eps']:g} EPS at {E.BYTES_PER_EVENT['log']} bytes per event.")
    elif v["log_sources"] > 0:
        log = {"mode": "src", "value": v["log_sources"]}
    flow: dict = {}
    if v["flows_per_sec"] > 0:
        flow = {"mode": "gb", "value": round(v["flows_per_sec"] * 86400 * E.BYTES_PER_EVENT["flow"] / gb, 2)}
        notes.append(f"Flow volume {flow['value']} GB/day from {v['flows_per_sec']:g} flows/sec at "
                     f"{E.BYTES_PER_EVENT['flow']} bytes per flow.")
    elif v["flow_sources"] > 0:
        flow = {"mode": "src", "value": v["flow_sources"]}
    observe = "ObserveOps" in products and any(v[k] > 0 for k in OBSERVE_KEYS)
    service = "ServiceOps" in products and any(v[k] > 0 for k in SERVICE_KEYS)
    ha, dr = v["ha"] >= 1, v["dr"] >= 1
    architecture = "ha_dr" if ha and dr else "ha" if ha else "dc_dr" if dr else "standalone"
    for key, dim in (("log_retention_days", "log"), ("monitoring_retention_days", "monitoring")):
        if v[key] > 0:
            d = E.RETENTION[dim]
            notes.append(f"The RFP asks for {v[key]:g} days of {d['label'].lower()} retention; sizing uses the standard "
                         f"{d['raw']} days raw / {d['agg']} days aggregated. Set custom retention on review if needed.")
    inp = {"architecture": architecture, "observe": observe, "service": service,
           "observeInput": {"devices": v["devices"], "log": log, "flow": flow, "apm": v["apm_apps"], "rum": v["rum_apps"],
                            "nccm": v["ncm_devices"], "ping": v["ping_targets"]},
           "technicians": v["technicians"], "assets": v["assets"], "endpoints": v["endpoints"],
           "vuln": v["vulnerability"] >= 1, "sites": v["sites"]}
    return inp, notes


def compute(items: list[dict], products: list[str], tables: dict | None = None) -> dict:
    """Hardware sizing for the architecture agent's extracted inputs."""
    inputs = clean_inputs(items)
    inp, notes = engine_input({i["name"]: i["value"] for i in inputs}, products)
    out = {"inputs": inputs, "engine_input": inp, "notes": notes, "status": "ok", "error": "", "sites": [],
           "architecture": inp["architecture"], "retention": "", "topology": "",
           "fields": [{"name": k, "label": label, "product": p} for k, (label, p) in INPUTS.items()]}
    if not inp["observe"] and not inp["service"]:
        out["status"] = "missing_inputs"
        out["error"] = "No sizing inputs were found in the RFP. Enter them on review."
        return out
    try:
        res = E.hardware_sites(tables or E.SERVICEOPS_TABLES, inp)
    except E.SizingError as e:
        out["status"], out["error"] = "out_of_range", str(e)
        return out
    out["sites"], out["retention"] = res["sites"], res["retentionText"]
    if inp["observe"]:
        oo = E.size({**inp["observeInput"], "isHA": inp["architecture"] in ("ha", "ha_dr")})
        out["topology"] = oo["topologyLabel"]
        if oo["cpuForced"]:
            notes.append("Single-box would exceed 32 vCPU, so the ObserveOps deployment is distributed.")
        if oo["haRecommended"]:
            notes.append("More than 5,000 devices: HA is recommended.")
    return out
