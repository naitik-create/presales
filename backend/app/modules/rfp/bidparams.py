"""Bid parameters: the figures every output depends on, pre-filled from the RFP analysis and confirmed by presales
before the BOQs are generated. Field names follow the BOQ Generator (172.16.12.103:5050) request so they can be sent
as they are. Pure functions only."""
from __future__ import annotations

import re

from app.modules.rfp import hwsizing

# (name, label, kind, default, options or None, group)
FIELDS: list[tuple] = [
    ("customer_name", "Customer name", "text", "", None, "General"),
    ("product_line", "Product line", "choice", "combined",
     [("combined", "ObserveOps + ServiceOps"), ("aiops", "ObserveOps only"), ("serviceops", "ServiceOps only"),
      ("serviceops_saas", "ServiceOps SaaS")], "General"),
    ("license_type", "Licence type", "choice", "perpetual",
     [("perpetual", "Perpetual"), ("annual", "Annual subscription"), ("saas", "SaaS annual (ServiceOps only)")], "General"),
    ("amc_years", "AMC / ATS years (perpetual)", "int", 5, None, "General"),
    ("architecture", "Deployment architecture", "choice", "standalone",
     [("standalone", "Standalone"), ("ha", "High availability (HA)"), ("dr", "Disaster recovery (DR)"),
      ("ha_dr", "HA + DR")], "General"),
    ("support_window", "Support window", "choice", "8x5", [("8x5", "8x5 working days"), ("24x7", "24x7")], "General"),
    ("onsite_days", "Onsite days", "int", 5, None, "General"),
    ("proposal_validity", "Proposal validity (days)", "int", 30, None, "General"),
    ("monitoring_nodes", "Monitoring nodes (min 25)", "int", 0, None, "ObserveOps licences"),
    ("ncm_nodes", "NCM nodes (min 25, needs monitoring)", "int", 0, None, "ObserveOps licences"),
    ("log_ingestion_gb", "Log-forwarding core devices (min 3)", "int", 0, None, "ObserveOps licences"),
    ("flow_ingestion_gb", "Flow-forwarding core devices (min 3)", "int", 0, None, "ObserveOps licences"),
    ("apm_monolithic_apps", "APM monolithic applications (min 3)", "int", 0, None, "ObserveOps licences"),
    ("apm_cluster_count", "APM clusters (min 3)", "int", 0, None, "ObserveOps licences"),
    ("rum_apps", "RUM applications (min 3)", "int", 0, None, "ObserveOps licences"),
    ("ipam_nodes", "IPAM nodes", "int", 0, None, "ObserveOps licences"),
    ("aiops_platform_users", "ObserveOps platform users (named)", "int", 5, None, "ObserveOps licences"),
    ("serviceops_type", "ServiceOps edition", "choice", "enterprise",
     [("enterprise", "Enterprise"), ("professional", "Professional")], "ServiceOps licences"),
    ("technician_type", "Technician licence", "choice", "named", [("named", "Named"), ("concurrent", "Concurrent")],
     "ServiceOps licences"),
    ("technicians", "Technicians (min 3)", "int", 0, None, "ServiceOps licences"),
    ("assets", "Assets", "int", 0, None, "ServiceOps licences"),
    ("patch_endpoints", "Patch endpoints (min 25)", "int", 0, None, "ServiceOps licences"),
    ("rdp_endpoints", "Remote desktop endpoints", "int", 0, None, "ServiceOps licences"),
    ("serviceops_gui_users", "ServiceOps portal users", "int", 5, None, "ServiceOps licences"),
]
NAMES = [f[0] for f in FIELDS]
_META = {f[0]: f for f in FIELDS}

# Fixed parts of the BOQ Generator request that do not change per bid (unpriced output ignores the percentages).
BOQ_CONSTANTS = {"aiops_type": "hybrid", "ps_implementation": True, "ps_additional": False, "ps_additional_desc": "",
                 "ps_integrations": [], "ps_percentage": 15, "custom_integration_cost": 0, "custom_integration_desc": "",
                 "amc_percentage": 10, "amc_yoy_increase": False, "amc_yoy_percentage": 0, "force_unpriced": True}


def fields_meta() -> list[dict]:
    return [{"name": n, "label": label, "kind": kind, "default": default, "group": group,
             "options": [{"value": v, "label": lbl} for v, lbl in options] if options else None}
            for n, label, kind, default, options, group in FIELDS]


def _fact(analysis: dict, label_start: str) -> dict:
    for f in analysis.get("bid_facts") or []:
        if isinstance(f, dict) and str(f.get("item", "")).startswith(label_start):
            return f
    return {}


def prefill(*, customer: str, products: list[str], analysis: dict, scope: dict, sizing_inputs: list[dict]) -> dict:
    """Best first guess for every field, with where each value came from."""
    p = {n: _META[n][3] for n in NAMES}
    src: dict[str, str] = {n: "Default" for n in NAMES}
    notes: list[str] = []

    if customer:
        p["customer_name"], src["customer_name"] = customer, "Workspace customer"
    else:
        auth = _fact(analysis, "Issuing authority")
        if auth.get("value") and auth["value"] != "Not stated":
            p["customer_name"], src["customer_name"] = auth["value"][:120], f"RFP {auth.get('ref', '')}".strip()

    in_scope = {m.get("product") for m in scope.get("modules_in_scope") or []} & {"ObserveOps", "ServiceOps"}
    prods = in_scope or set(products or [])
    if prods == {"ObserveOps"}:
        p["product_line"] = "aiops"
    elif prods == {"ServiceOps"}:
        p["product_line"] = "serviceops"
    src["product_line"] = "Motadata scope" if in_scope else "Workspace products"

    amc = _fact(analysis, "Warranty")
    m = re.search(r"(\d+)\s*(?:\(\w+\)\s*)?years?", amc.get("value", ""), re.I)
    if m and 1 <= int(m.group(1)) <= 7:
        p["amc_years"], src["amc_years"] = int(m.group(1)), f"RFP {amc.get('ref', '')}".strip()
    contract = (amc.get("value", "") + " " + _fact(analysis, "Contract period").get("value", "")).lower()
    if "subscription" in contract:
        p["license_type"], src["license_type"] = "annual", "RFP mentions subscription"

    sla = " ".join(str(f.get("value", "")) for f in analysis.get("bid_facts") or [] if isinstance(f, dict)).lower()
    if re.search(r"24\s*[x×*/]\s*7", sla):
        p["support_window"], src["support_window"] = "24x7", "RFP asks for 24x7"

    vals = {i["name"]: i for i in sizing_inputs or []}

    def take(field, name, minimum=0):
        it = vals.get(name)
        if it and it["value"] > 0:
            p[field] = int(round(it["value"]))
            src[field] = f"RFP {it.get('ref', '')}".strip()
            if minimum and 0 < p[field] < minimum:
                notes.append(f"{_META[field][1]}: RFP gives {p[field]}; the BOQ minimum applies.")
                p[field] = minimum

    take("monitoring_nodes", "devices", 25)
    take("ncm_nodes", "ncm_devices", 25)
    take("log_ingestion_gb", "log_sources", 3)
    take("flow_ingestion_gb", "flow_sources", 3)
    take("apm_monolithic_apps", "apm_apps", 3)
    take("rum_apps", "rum_apps", 3)
    take("technicians", "technicians", 3)
    take("assets", "assets")
    take("patch_endpoints", "endpoints", 25)
    if not p["log_ingestion_gb"] and (vals.get("log_gb_per_day") or vals.get("log_eps")):
        notes.append("The RFP gives log volume but not the number of log-forwarding devices the licence counts: enter it.")
    if not p["flow_ingestion_gb"] and vals.get("flows_per_sec"):
        notes.append("The RFP gives flow volume but not the number of flow-forwarding devices the licence counts: enter it.")
    ha = vals.get("ha", {}).get("value", 0) >= 1
    dr = vals.get("dr", {}).get("value", 0) >= 1
    p["architecture"] = "ha_dr" if ha and dr else "ha" if ha else "dr" if dr else "standalone"
    if ha or dr:
        src["architecture"] = "RFP sizing inputs"
    return {"params": p, "sources": src, "notes": notes,
            "sizing_inputs": [{k: i[k] for k in ("name", "value", "ref", "note")} for i in sizing_inputs or []]}


def clean(params: dict) -> dict:
    """Type-check edited parameters; unknown fields are dropped, bad choices rejected."""
    out = {}
    for n in NAMES:
        _n, label, kind, default, options, _g = _META[n]
        v = params.get(n, default)
        if kind == "int":
            try:
                v = max(0, int(float(v or 0)))
            except (TypeError, ValueError):
                raise ValueError(f"{label}: enter a whole number")
        elif kind == "choice":
            if v not in [o[0] for o in options]:
                raise ValueError(f"{label}: choose one of the options")
        else:
            v = str(v or "").strip()[:200]
        out[n] = v
    return out


def warnings(p: dict) -> list[str]:
    """The BOQ Generator's own minimum rules, checked before sending so presales sees them on review."""
    w = []
    saas = p["license_type"] == "saas" or p["product_line"] == "serviceops_saas"
    if not p["customer_name"]:
        w.append("Customer name is required.")
    if not saas:
        if 0 < p["monitoring_nodes"] < 25:
            w.append("Minimum monitoring nodes is 25.")
        if p["ncm_nodes"] and not p["monitoring_nodes"]:
            w.append("NCM requires monitoring nodes.")
        for f, mn in (("ncm_nodes", 25), ("log_ingestion_gb", 3), ("flow_ingestion_gb", 3), ("apm_monolithic_apps", 3),
                      ("apm_cluster_count", 3), ("rum_apps", 3)):
            if 0 < p[f] < mn:
                w.append(f"{_META[f][1].split(' (')[0]}: minimum is {mn}.")
    if 0 < p["technicians"] < 3:
        w.append("Minimum technicians is 3.")
    if 0 < p["patch_endpoints"] < 25:
        w.append("Minimum patch endpoints is 25.")
    if p["product_line"] == "aiops" and (p["technicians"] or p["assets"] or p["patch_endpoints"]):
        w.append("ServiceOps quantities are entered but the product line is ObserveOps only; they will not be quoted.")
    return w


def boq_request(p: dict) -> dict:
    """The JSON body for the BOQ Generator's /api/download-boq (unpriced)."""
    body = {**BOQ_CONSTANTS, **p}
    if p["license_type"] != "perpetual":
        body["amc_years"] = 0
        body["amc_percentage"] = 0
    return body


def sizing_items(p: dict, sizing_inputs: list[dict]) -> list[dict]:
    """Sizing inputs with the architecture chosen on review applied, so HW and SW BOQs agree."""
    items = [dict(i) for i in sizing_inputs or [] if i.get("name") not in ("ha", "dr")]
    if p["architecture"] in ("ha", "ha_dr"):
        items.append({"name": "ha", "value": 1, "ref": "Bid parameters", "note": ""})
    if p["architecture"] in ("dr", "ha_dr"):
        items.append({"name": "dr", "value": 1, "ref": "Bid parameters", "note": ""})
    return items


def products_for(p: dict) -> list[str]:
    return {"combined": ["ObserveOps", "ServiceOps"], "aiops": ["ObserveOps"]}.get(p["product_line"], ["ServiceOps"])


def compute_sizing(p: dict, sizing_inputs: list[dict]) -> dict:
    return hwsizing.compute(sizing_items(p, sizing_inputs), products_for(p))
