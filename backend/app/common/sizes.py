"""Size parser for customer infrastructure text (fills the customer context parsed sizes).

A number followed within three words by a keyword, with k / thousand / lakh / lac / mn / million units,
plus a "keyword: number" fallback.

Keyword lists are a provisional starting set; extend them as needed.
"""
import re

# Order matters: more specific keys first, so "NCCM devices" is not read as network devices.
KEYWORDS: list[tuple[str, list[str]]] = [
    ("peak_eps", ["peak eps", "eps peak", "peak events per second"]),
    ("eps", ["eps", "events per second", "sustained eps", "events/sec"]),
    ("nccm_devices", ["nccm devices", "nccm", "config managed devices", "configuration managed devices"]),
    ("flow_devices", ["flow devices", "flow exporting devices", "netflow devices", "flow exporters", "flow sources"]),
    ("interfaces", ["interfaces", "ports", "network interfaces"]),
    ("network_devices", ["network devices", "routers and switches", "switches", "routers", "network elements",
                         "network nodes", "devices"]),
    ("servers", ["servers", "vms", "virtual machines", "hosts", "physical servers", "databases"]),
    ("critical_apps", ["critical apps", "critical applications", "business critical applications", "critical services"]),
    ("app_instances", ["app instances", "application instances", "jvms", "app servers"]),
    ("apps", ["applications", "apps"]),
    ("technicians", ["technicians", "technician licences", "agents", "analysts", "itsm users", "helpdesk agents"]),
    ("end_users", ["end users", "employees", "users", "requesters", "staff"]),
    ("endpoints", ["endpoints", "desktops", "laptops", "workstations", "pcs"]),
    ("sites", ["sites", "branches", "locations", "offices", "wan links", "stores", "plants", "campuses"]),
    ("hot_retention_days", ["days hot", "days online", "days retention", "days of retention", "days log retention"]),
]

FIELD_LABELS = {
    "network_devices": "Network devices", "interfaces": "Interfaces", "sites": "Sites / WAN links",
    "nccm_devices": "NCCM devices", "flow_devices": "Flow-exporting devices", "servers": "Servers / VMs",
    "eps": "Log EPS (sustained)", "peak_eps": "Log EPS (peak)", "apps": "APM applications",
    "app_instances": "APM app instances", "critical_apps": "Critical apps", "technicians": "ITSM technicians",
    "end_users": "End users", "endpoints": "Endpoints", "hot_retention_days": "Hot log retention (days)",
    "growth": "Annual growth", "term_years": "Contract term (years)",
}

UNITS = {"k": 1e3, "thousand": 1e3, "lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "lacs": 1e5, "mn": 1e6, "million": 1e6}
NUM_RE = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{2,3})+|\d+(?:\.\d+)?)\s*(k|thousand|lakhs?|lacs?|mn|million)?(?![\w])", re.I)
WORD_RE = re.compile(r"[a-z0-9/+]+")


def _value(num: str, unit: str | None) -> float:
    v = float(num.replace(",", ""))
    return v * UNITS.get((unit or "").lower(), 1)


def _match_keyword(words: list[str]) -> str | None:
    """Return the key whose phrase starts nearest the number, within three words and before the next number."""
    for i, w in enumerate(words):
        if re.fullmatch(r"[\d.,]+", w):
            words = words[:i]
            break
    for start in range(0, 3):
        for key, phrases in KEYWORDS:
            for phrase in phrases:
                p = phrase.split()
                if words[start:start + len(p)] == p:
                    return key
    return None


def parse_sizes(text: str) -> dict:
    """Return {key: number}. Later mentions of the same key do not overwrite the first."""
    if not text:
        return {}
    lower = text.lower()
    out: dict[str, float] = {}

    for m in NUM_RE.finditer(lower):
        after = WORD_RE.findall(lower[m.end():m.end() + 80])
        key = _match_keyword(after)
        if key and key not in out:
            out[key] = _value(m.group(1), m.group(2))

    # keyword: number fallback
    for key, phrases in KEYWORDS:
        if key in out:
            continue
        for phrase in phrases:
            m = re.search(rf"\b{re.escape(phrase)}\s*[:=\-]\s*(\d[\d,]*(?:\.\d+)?)\s*(k|thousand|lakhs?|lacs?|mn|million)?", lower)
            if m:
                out[key] = _value(m.group(1), m.group(2))
                break

    g = re.search(r"(\d+(?:\.\d+)?)\s*%\s*(?:annual\s+|yearly\s+|y-?o-?y\s+)?growth|growth\s*(?:of|:|=)?\s*(\d+(?:\.\d+)?)\s*%", lower)
    if g:
        out["growth"] = float(g.group(1) or g.group(2)) / 100
    t = re.search(r"(\d+)\s*[- ]?(?:years?|yrs?)\s*(?:contract|term|amc|period)|(?:contract|term)\s*(?:of|:)?\s*(\d+)\s*(?:years?|yrs?)", lower)
    if t:
        out["term_years"] = float(t.group(1) or t.group(2))
    return {k: (int(v) if float(v).is_integer() else v) for k, v in out.items()}
