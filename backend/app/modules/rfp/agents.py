"""RFP agent prompts and output schemas (§8.4)."""

COMPLIANCE_STATUSES = ["Compliant", "Partially Compliant", "Non-Compliant", "Needs Product Validation", "Not Applicable"]


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "additionalProperties": False, "required": required or list(props), "properties": props}


S = {"type": "string"}
SA = {"type": "array", "items": S}

EXTRACT_SCHEMA = _obj({"requirements": {"type": "array", "items": _obj({
    "text": S, "category": {"type": "string", "enum": ["Technical", "Functional", "PQ", "TQ", "Commercial", "Legal",
                                                       "Submission", "SLA", "Implementation", "Support", "Other"]},
    "ref": S, "section": S})}})
EXTRACT_SYSTEM = """Identify every individual requirement in this part of a customer RFP.
Split compound sentences into separate requirements only when they ask for clearly different things.
Copy requirement text exactly as written; do not paraphrase. For each, give the reference marker shown in square brackets
before the line it came from (for example "p.12" or "Sheet1!R40") and the section heading it sits under.
Skip boilerplate that asks nothing of the bidder."""

CORRIGENDUM_SCHEMA = _obj({"changes": {"type": "array", "items": _obj({
    "action": {"type": "string", "enum": ["added", "changed", "removed"]}, "original_number": S, "original_text_hint": S,
    "text": S, "category": S, "ref": S})}})
CORRIGENDUM_SYSTEM = """This is a corrigendum to an RFP. List every change it makes to the requirements:
added requirements, changed requirements (give the new full text) and removed requirements.
Use original_number or original_text_hint to identify the requirement it changes, matching the list supplied."""

COMPLIANCE_SCHEMA = _obj({"answers": {"type": "array", "items": _obj({
    "requirement_id": S, "status": {"type": "string", "enum": COMPLIANCE_STATUSES}, "proposed_response": S,
    "explanation": S, "evidence": S, "source_ids": SA, "validation_remarks": S})}})
COMPLIANCE_SYSTEM = """Prepare the technical compliance response for each RFP requirement for Motadata ObserveOps / ServiceOps.
Sources are given per requirement in priority order: current approved documentation and internal knowledge (S),
then past submitted RFP answers (P). Prefer higher-priority sources; if sources disagree, say so in validation_remarks.
Use "Needs Product Validation" when the sources do not clearly establish the capability. Do not claim compliance without evidence.
The proposed response is customer-facing, concise and factual. Put caveats and anything the team must check in validation_remarks."""

ANALYSIS_SCHEMA = _obj({
    "summary": S, "objectives": SA, "scope": SA, "submission_requirements": SA,
    "dates": {"type": "array", "items": _obj({"item": S, "date": S, "ref": S})},
    "milestones": SA, "mandatory_conditions": SA, "missing_information": SA})
ANALYSIS_SYSTEM = "Analyse this RFP. Give references (page, sheet or section) in brackets for every date and condition."

ARCH_SCHEMA = _obj({
    "recommended_architecture": S, "components": SA, "prerequisites": SA, "ha_dr_needs": S,
    "sizing_inputs": {"type": "array", "items": _obj({"name": S, "value": {"type": "number"}, "ref": S})},
    "assumptions": SA, "source_ids": SA})
ARCH_SYSTEM = """Recommend the Motadata deployment architecture for this RFP using only the knowledge sources supplied.
Do not state hardware sizing figures: extract the sizing inputs (with the input names listed) and the platform computes sizing from the rule table.
State every assumption."""

RISK_SCHEMA = _obj({"items": {"type": "array", "items": _obj({
    "category": {"type": "string", "enum": ["Product gap", "Integration limit", "Licence dependency", "Migration dependency",
                                            "Customer network constraint", "Penalty / SLA", "Unclear requirement", "Commercial", "Other"]},
    "description": S, "impact": {"type": "string", "enum": ["High", "Medium", "Low"]}, "ref": S, "mitigation": S})}})
RISK_SYSTEM = "Identify risks and gaps in this RFP for Motadata. Base product gaps on the compliance answers supplied, not on assumptions."

PQTQ_SCHEMA = _obj({"items": {"type": "array", "items": _obj({
    "type": {"type": "string", "enum": ["PQ", "TQ"]}, "criterion": S, "ref": S, "draft_response": S,
    "supporting_evidence": S, "missing_items": SA})}})
PQTQ_SYSTEM = """Draft responses to the PQ and TQ criteria. Never invent credentials, certifications, customer references,
turnover figures or experience; where a criterion needs them, list them under missing_items for the team to supply."""

BOQ_SCHEMA = _obj({"lines": {"type": "array", "items": _obj({
    "product": S, "module": S, "licence_metric": S, "quantity": S, "assumption": S, "ref": S})}, "assumptions": SA})
BOQ_SYSTEM = "List the Motadata modules, licence metrics and quantities this RFP needs. Never give prices. Quote the RFP reference for each quantity."

SYNOPSIS_SCHEMA = _obj({"overview": S, "major_requirements": SA, "compliance_position": S, "significant_risks": SA})
SYNOPSIS_SYSTEM = "Write a short management overview of this RFP: scope, major requirements, Motadata's compliance position and significant risks."

PREBID_SCHEMA = _obj({"queries": {"type": "array", "items": _obj({"ref": S, "clause_text": S, "query": S, "reason": S})}})
PREBID_SYSTEM = """Draft pre-bid clarification questions for requirements that are unclear, contradictory, restrictive or
depend on customer information. Questions are polite, specific and reference the clause."""

PROPOSAL_SCHEMA = _obj({"sections": {"type": "array", "items": _obj({"placeholder": S, "content": S})}})
PROPOSAL_SYSTEM = """Write technical proposal content for each placeholder of the selected template, from the workspace
material supplied. Follow the style and structure of the sample documents where given, but take every fact only from the
workspace material and knowledge sources. Use plain paragraphs; start list items with "- "."""

DOC_AGENTS = {
    # key: (agent_key, schema, system, uses_knowledge)
    "analysis": ("rfp_analysis", ANALYSIS_SCHEMA, ANALYSIS_SYSTEM, False),
    "architecture": ("architecture_sizing", ARCH_SCHEMA, ARCH_SYSTEM, True),
    "risk": ("risk_gap", RISK_SCHEMA, RISK_SYSTEM, False),
    "pqtq": ("pq_tq", PQTQ_SCHEMA, PQTQ_SYSTEM, True),
    "boq": ("boq_licensing", BOQ_SCHEMA, BOQ_SYSTEM, True),
    "synopsis": ("executive_synopsis", SYNOPSIS_SCHEMA, SYNOPSIS_SYSTEM, False),
    "prebid": ("prebid_query", PREBID_SCHEMA, PREBID_SYSTEM, False),
}
DOC_AGENT_LABELS = {"analysis": "RFP analysis", "architecture": "Architecture and sizing inputs", "risk": "Risk and gap analysis",
                    "pqtq": "PQ/TQ", "boq": "BOQ and licensing inputs", "synopsis": "Executive synopsis", "prebid": "Pre-bid queries"}
