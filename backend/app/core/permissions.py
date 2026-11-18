"""Permission catalogue (§12) and default role bundles (§2.3). Codes are '<area>.<action>'."""

CATALOGUE: dict[str, tuple[str, list[tuple[str, str]]]] = {
    "rfp": ("RFP Intelligence", [
        ("view", "View"), ("create", "Create workspace"), ("edit", "Edit"), ("approve", "Approve answers"),
        ("export", "Export"), ("manage_templates", "Manage templates"), ("cancel_jobs", "Cancel jobs"),
    ]),
    "demo": ("Demo Intelligence", [
        ("view", "View"), ("create", "Create"), ("edit", "Edit"), ("export", "Export"), ("manage_templates", "Manage templates"),
    ]),
    "usecases": ("Demo use cases", [("view", "View"), ("create", "Create"), ("edit", "Edit"), ("approve", "Approve")]),
    "ask": ("Ask Motadata", [("use", "Use"), ("view_gaps", "View gap log")]),
    "knowledge": ("Knowledge Hub", [
        ("upload", "Upload"), ("register_url", "Register URL"), ("approve", "Approve sources"), ("manage_sections", "Manage sections"),
    ]),
    "submitted": ("Submitted RFP repository", [("view", "View"), ("upload", "Upload"), ("manage", "Manage")]),
    "scoring": ("Team Scorecard", [
        ("view_own", "View own"), ("view_all", "View all"), ("propose", "Propose"), ("approve", "Approve"),
        ("manage_rules", "Manage rules"), ("view_reports", "View reports"),
    ]),
    "customers": ("Customer context", [("view", "View"), ("create", "Create"), ("edit", "Edit")]),
    "admin": ("Administration", [
        ("users", "Manage users"), ("roles", "Manage roles"), ("ai_config", "AI configuration"), ("usage", "View usage"),
        ("budget", "Manage budget"), ("settings", "System settings"), ("audit", "View audit log"),
        ("api_keys", "Manage API keys"), ("branding", "Manage branding"),
    ]),
}

# Knowledge Hub "View per section" permissions are generated per section: knowledge.view.<section_key>
KNOWLEDGE_VIEW_PREFIX = "knowledge.view."


def static_permissions() -> list[tuple[str, str, str]]:
    out = []
    for area, (area_label, actions) in CATALOGUE.items():
        for action, label in actions:
            out.append((f"{area}.{action}", area_label, label))
    return out


def section_permission(section_key: str) -> str:
    return f"{KNOWLEDGE_VIEW_PREFIX}{section_key}"


def _all_in(*areas: str) -> list[str]:
    return [f"{a}.{act}" for a in areas for act, _ in CATALOGUE[a][1]]


ALL_SECTIONS = "*sections*"  # expanded at seed time to every knowledge.view.<section>

DEFAULT_ROLES: dict[str, tuple[str, list[str]]] = {
    "System Administrator": (
        "Users, roles, permissions, AI model configuration, usage and budget, system settings",
        _all_in("admin"),
    ),
    "Presales Manager": (
        "All modules; approves RFP answers and scoring transactions",
        _all_in("rfp", "demo", "usecases", "ask", "submitted", "scoring", "customers")
        + ["knowledge.upload", "knowledge.register_url", ALL_SECTIONS, "admin.usage"],
    ),
    "Presales Engineer": (
        "Uses the modules granted to them",
        ["rfp.view", "rfp.create", "rfp.edit", "rfp.export", "demo.view", "demo.create",
         "demo.edit", "demo.export", "usecases.view", "usecases.create", "ask.use", "submitted.view",
         "customers.view", "customers.create", "customers.edit", ALL_SECTIONS],
    ),
    "Knowledge Administrator": (
        "Uploads, approves and maintains Knowledge Hub sources",
        _all_in("knowledge", "submitted") + ["ask.use", "ask.view_gaps", "usecases.view", "usecases.edit", ALL_SECTIONS],
    ),
    "RFP only": ("RFP Intelligence and Ask Motadata", _all_in("rfp") + ["ask.use", "customers.view", ALL_SECTIONS]),
    "Scoring participant": ("Team Scorecard: View own", ["scoring.view_own"]),
}
