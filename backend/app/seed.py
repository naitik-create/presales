"""Idempotent seed: permissions, default roles, Knowledge Hub sections, agents, models, starter content.

Run: python -m app.seed  (prints the first administrator password once)
"""
import secrets
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.embeddings import OPTIONS
from app.config import get_settings
from app.core.permissions import ALL_SECTIONS, DEFAULT_ROLES, section_permission, static_permissions
from app.core.security import hash_password
from app.db import SessionLocal
from app.models.ai import AgentConfiguration, AIModel, EmbeddingConfiguration, ModelPrice
from app.models.core import Permission, Role, User
from app.models.demo import DemoUseCase
from app.models.knowledge import KnowledgeSection
from app.models.scorecard import ScoringCategory

SECTIONS = [
    # key, name, description, used by, priority
    ("specifications", "Specifications", "Product specification documents", "Ask Motadata, RFP Intelligence", 1),
    ("datasheets", "Datasheets", "ObserveOps and ServiceOps datasheets", "Ask Motadata, RFP Intelligence", 1),
    ("hardware_requirements_and_sizing", "Hardware requirements and sizing", "Sizing guide from the product team, hardware tables", "Ask Motadata sizing rules, RFP Intelligence", 1),
    ("prerequisites", "Prerequisites", "Installation prerequisites, ports, OS and database support", "Ask Motadata, RFP Intelligence", 1),
    ("architecture_and_deployment", "Architecture and deployment", "Architecture guides, HA and DR designs", "Ask Motadata, RFP Intelligence", 1),
    ("integrations", "Integrations", "Supported integrations and methods", "Ask Motadata, RFP Intelligence", 1),
    ("licensing", "Licensing", "Licence models and metrics (no prices)", "Ask Motadata, RFP Intelligence", 1),
    ("online_documentation", "Online documentation", "Registered documentation URLs", "All", 1),
    ("competitor_information", "Competitor information", "Verified comparisons and internal observations, labelled separately", "Demo Intelligence", 2),
    ("templates_and_samples", "Templates and samples", "Word proposal templates and sample documents", "RFP Intelligence", 2),
    ("demo_use_cases", "Demo use cases", "Curated demo flows", "Demo Intelligence", 2),
    ("internal_presales_knowledge", "Internal presales knowledge", "Approved internal notes and answers", "Ask Motadata, RFP Intelligence", 2),
]

AGENTS = [
    # key, label, module, effort, max tokens
    ("ask_motadata", "Ask Motadata", "ask", "medium", 16000),
    ("rfp_analysis", "RFP analysis", "rfp", "medium", 16000),
    ("requirement_extraction", "Requirement extraction", "rfp", "medium", 32000),
    ("technical_compliance", "Technical compliance", "rfp", "medium", 16000),
    ("architecture_sizing", "Architecture and sizing inputs", "rfp", "medium", 16000),
    ("risk_gap", "Risk and gap analysis", "rfp", "medium", 16000),
    ("pq_tq", "PQ/TQ", "rfp", "medium", 16000),
    ("boq_licensing", "BOQ and licensing inputs", "rfp", "medium", 16000),
    ("executive_synopsis", "Executive synopsis", "rfp", "medium", 8000),
    ("prebid_query", "Pre-bid query", "rfp", "medium", 16000),
    ("proposal_generation", "Proposal generation", "rfp", "high", 32000),
    ("demo_script", "Demo script", "demo", "medium", 16000),
]

MODELS = [
    # Prices per million tokens (USD), Anthropic first-party rates. The administrator keeps these current.
    ("claude-opus-5-5", "Claude Opus 5.5", Decimal("4.00"), Decimal("20.00")),
    ("claude-sonnet-5-5", "Claude Sonnet 5.5", Decimal("2.00"), Decimal("10.00")),
    ("claude-haiku-5-5", "Claude Haiku 5.5", Decimal("0.10"), Decimal("0.50")),
]
DEFAULT_MODEL = "claude-opus-5-5"

STARTER_USE_CASES = [
    ("Link down to auto-ticket", "ObserveOps", "IM", "Network outages are found late and tickets are raised by hand."),
    ("Slow transaction trace", "ObserveOps", "AP", "Users report slowness and teams cannot locate the cause."),
    ("Config change linked to change request", "ObserveOps", "NC", "Unauthorised configuration changes cause outages."),
    ("Vulnerable endpoint patched and closed", "ServiceOps", "VM", "Vulnerabilities stay open because scanning and patching are separate."),
    ("Log anomaly correlated with a metric spike", "ObserveOps", "LM", "Logs and metrics are in different tools, so root cause takes long."),
    ("CI impact", "ServiceOps", "CM", "Teams do not know which services an outage affects."),
    ("Prohibited software removal", "ServiceOps", "AM", "Unlicensed and prohibited software creates audit risk."),
    ("Auditor uptime report", "ObserveOps", "IM", "Auditors ask for availability evidence that takes days to compile."),
]

SCORING_CATEGORIES = ["Discipline and process", "CRM and opportunity updates", "Communication and responsiveness",
                      "Demo and POC contribution", "Team collaboration", "Learning and improvement"]


def seed(db: Session) -> str | None:
    # permissions
    existing = {p.code for p in db.scalars(select(Permission))}
    for code, area, label in static_permissions():
        if code not in existing:
            db.add(Permission(code=code, area=area, label=label))
    for i, (key, name, desc, used, prio) in enumerate(SECTIONS):
        if not db.scalar(select(KnowledgeSection).where(KnowledgeSection.key == key)):
            db.add(KnowledgeSection(key=key, name=name, description=desc, used_by=used, priority=prio, sort=i * 10))
        if section_permission(key) not in existing:
            db.add(Permission(code=section_permission(key), area="Knowledge Hub", label=f"View section: {name}"))
    db.flush()
    all_sections = [section_permission(s.key) for s in db.scalars(select(KnowledgeSection))]
    for name, (desc, codes) in DEFAULT_ROLES.items():
        role = db.scalar(select(Role).where(Role.name == name))
        if role is None:
            expanded = [c for c in codes if c != ALL_SECTIONS] + (all_sections if ALL_SECTIONS in codes else [])
            role = Role(name=name, description=desc, is_system=True,
                        permissions=list(db.scalars(select(Permission).where(Permission.code.in_(expanded)))))
            db.add(role)
    # AI
    for model_id, label, inp, out in MODELS:
        if not db.scalar(select(AIModel).where(AIModel.model_id == model_id)):
            db.add(AIModel(model_id=model_id, label=label))
            db.add(ModelPrice(model_id=model_id, input_per_mtok=inp, output_per_mtok=out))
    for key, label, module, effort, tokens in AGENTS:
        if not db.scalar(select(AgentConfiguration).where(AgentConfiguration.agent_key == key)):
            db.add(AgentConfiguration(agent_key=key, label=label, module=module, model_id=DEFAULT_MODEL, effort=effort,
                                      max_output_tokens=tokens, timeout_seconds=600))
    if not db.scalar(select(EmbeddingConfiguration)):
        provider = get_settings().EMBEDDING_PROVIDER if get_settings().EMBEDDING_PROVIDER in OPTIONS else "local"
        opt = OPTIONS[provider]
        db.add(EmbeddingConfiguration(provider=provider, model_name=opt["model_name"], dimension=opt["dimension"], is_active=True))
    if not db.scalar(select(DemoUseCase)):
        for name, product, mod, pain in STARTER_USE_CASES:
            db.add(DemoUseCase(name=name, product=product, module_key=mod, pain=pain, status="Draft",
                               what_to_show="To be written by the team from their best demo.",
                               expected_result="To be written by the team."))
    for i, name in enumerate(SCORING_CATEGORIES):
        if not db.scalar(select(ScoringCategory).where(ScoringCategory.name == name)):
            db.add(ScoringCategory(name=name, sort=i * 10))
    # first administrator
    password = None
    if not db.scalar(select(User)):
        password = "Adm-" + secrets.token_urlsafe(10) + "9z"
        admin_roles = list(db.scalars(select(Role).where(Role.name.in_(["System Administrator", "Presales Manager",
                                                                        "Knowledge Administrator"]))))
        db.add(User(username="admin", full_name="Administrator", password_hash=hash_password(password), roles=admin_roles,
                    must_change_password=True))
    db.commit()
    return password


if __name__ == "__main__":
    with SessionLocal() as s:
        pw = seed(s)
    if pw:
        print(f"Created user 'admin' with temporary password: {pw}\nYou will be asked to change it at first sign-in.")
    else:
        print("Seed complete (no changes to users).")
