"""RFP agent prompts and output schemas (§8.4)."""
from app.modules.rfp.hwsizing import INPUTS as HW_INPUTS
from app.modules.rfp.bidpack import BID_FACTS, MODULES, NOT_STATED, PREBID_CATEGORIES, PREBID_FIELDS, SCOPE_OWNERS

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

FACT = _obj({"value": S, "ref": S})
ANALYSIS_SCHEMA = _obj({
    "bid_facts": _obj({key: FACT for key, _label in BID_FACTS}),
    "red_flags": {"type": "array", "items": _obj({"issue": S, "impact": {"type": "string", "enum": ["High", "Medium", "Low"]},
                                                   "ref": S})},
    "summary": S, "objectives": SA, "scope": SA, "submission_requirements": SA,
    "dates": {"type": "array", "items": _obj({"item": S, "date": S, "ref": S})},
    "milestones": SA, "mandatory_conditions": SA, "missing_information": SA})
ANALYSIS_SYSTEM = f"""Analyse this RFP. Give references (page, sheet or section) in brackets for every date and condition.
bid_facts is the bid synopsis the presales team reads first. For each fact give the value as the RFP states it, with
amounts, currency, percentages and durations exactly as written, and the reference. When the RFP does not state it,
the value is "{NOT_STATED}" and the reference is empty. The facts are:
{chr(10).join(f"- {key}: {label}" for key, label in BID_FACTS)}
red_flags are clauses that make bidding hard or risky for a software OEM and its partner: unusual eligibility, short
timelines, uncapped penalties or liquidated damages, unlimited liability, one-sided payment terms, specifications that
point to a single vendor, mandatory items Motadata does not make. Rate the impact on the bid."""

ARCH_SCHEMA = _obj({
    "recommended_architecture": S, "components": SA, "prerequisites": SA, "ha_dr_needs": S,
    "sizing_inputs": {"type": "array", "items": _obj({"name": S, "value": {"type": "number"}, "ref": S})},
    "motadata_inputs": {"type": "array", "items": _obj({
        "name": {"type": "string", "enum": list(HW_INPUTS)}, "value": {"type": "number"}, "ref": S, "note": S})},
    "assumptions": SA, "source_ids": SA})
ARCH_SYSTEM = f"""Recommend the Motadata deployment architecture for this RFP using only the knowledge sources supplied.
Do not state hardware sizing figures: extract the sizing inputs (with the input names listed) and the platform computes sizing from the rule table.
State every assumption.

motadata_inputs feed Motadata's hardware sizing calculator. Give each one the RFP states or clearly implies, with the
reference; leave out the ones the RFP does not support. Add counts across sites and annexures (for example servers plus
network devices plus databases for devices) and say how in note. Use 1 for yes on yes/no inputs. Inputs:
{chr(10).join(f"- {k}: {label}" for k, (label, _p) in HW_INPUTS.items())}"""

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

PREBID_SCHEMA = _obj({
    "tender_format": _obj({
        "found": {"type": "boolean"}, "ref": S, "instructions": S,
        "columns": {"type": "array", "items": _obj({"heading": S, "field": {"type": "string", "enum": PREBID_FIELDS}})}}),
    "queries": {"type": "array", "items": _obj({
        "rank": {"type": "integer"}, "impact": {"type": "string", "enum": ["High", "Medium", "Low"]},
        "category": {"type": "string", "enum": PREBID_CATEGORIES},
        "document": S, "section": S, "page": S, "clause_no": S, "ref": S,
        "clause_text": S, "query": S, "suggested_change": S, "reason": S})}})
PREBID_SYSTEM = f"""Draft pre-bid clarification queries for this RFP on behalf of Motadata (software OEM for ObserveOps and
ServiceOps) and its bidding partner.

1. Tender format. Look for the format the RFP prescribes for pre-bid queries (often an annexure or a table in the
   instructions to bidders). If found, set found=true, give its reference, list its column headings exactly as printed in
   order, and map each heading to the closest field: {", ".join(PREBID_FIELDS)} ("blank" when nothing fits). Put any
   submission instructions (email address, last date and time, file type, portal) in instructions. If no format is
   prescribed, set found=false and leave columns empty.

2. Queries. Raise queries where a clause is unclear, contradictory, restrictive, appears to favour one vendor, sets
   eligibility or OEM conditions a mid-size Indian OEM may not meet, leaves quantities or sizing open, or carries
   uncapped penalties or one-sided commercial terms. Return at most 25, ranked: rank 1 is the query with the biggest
   effect on Motadata's ability to bid and win. The top 10 are what the team will normally submit, so make them count.
   For each: document, section, page and clause number as printed; clause_text quoted exactly; query written politely
   and specifically as the bidder would submit it; suggested_change is the wording or relaxation the bidder asks for
   (empty if it is a pure clarification); reason is internal and explains why the query matters to Motadata.
   ref combines document, page and clause for display."""

ITEM = _obj({"item": S, "ref": S})
SCOPE_SCHEMA = _obj({
    "modules_in_scope": {"type": "array", "items": _obj({
        "product": {"type": "string", "enum": list(MODULES) + ["Other"]}, "module": S, "basis": S})},
    "partner_items": {"type": "array", "items": ITEM},
    "customer_prerequisites": {"type": "array", "items": ITEM},
    "out_of_scope": {"type": "array", "items": ITEM},
    "motadata_gaps": {"type": "array", "items": _obj({"item": S, "ref": S, "note": S})},
    "matrix": {"type": "array", "items": _obj({
        "number": S, "owner": {"type": "string", "enum": SCOPE_OWNERS},
        "product": {"type": "string", "enum": list(MODULES) + ["Other", ""]}, "module": S, "note": S})}})
SCOPE_SYSTEM = f"""Map the scope of this RFP for Motadata, a software OEM selling ObserveOps and ServiceOps through a
partner / system integrator. You get the list of requirements (number, category, reference, text, compliance status)
and Motadata knowledge sources, which may include Motadata's own profile: modules, standard exclusions, standard
deviations and what the partner normally supplies.

For every requirement give one matrix row with the requirement number exactly as given:
- owner: "Motadata" when Motadata software or Motadata services deliver it; "Partner / SI" for hardware, OS and
  database licences, third-party software, cabling, data-centre work, facility management manpower, onsite resident
  engineers unless the knowledge says Motadata provides them; "Customer" for things the buyer must provide (network
  access, credentials, rack space, approvals); "Shared" when Motadata and the partner both have a part; "Not applicable"
  for clauses that ask nothing technical of the bidder (legal, submission, commercial).
- product and module: for Motadata or Shared rows, the Motadata product and module, using these names where they fit:
{chr(10).join(f"  {p}: {', '.join(ms)}" for p, ms in MODULES.items())}
  Leave product empty for rows that are not Motadata's.
- note: a few words when the owner is not obvious, or when the compliance status shows Motadata cannot fully meet it.

Then summarise: modules_in_scope (with the requirement numbers or references as basis), partner_items,
customer_prerequisites, out_of_scope items, and motadata_gaps (requirements in Motadata's area that are non-compliant
or need validation). Base everything on the requirement text and the sources; do not guess capabilities."""

CONSIDERATION_CATEGORIES = ["Eligibility / PQ", "OEM / MAF", "Commercial and payment", "Penalty / SLA / LD",
                            "Motadata product gap", "Partner dependency", "Customer dependency", "Deviation to take",
                            "Timeline", "Submission / documents", "Other"]
CONSIDERATION_OWNERS = ["Presales", "Sales", "Partner / SI", "Management", "Product team", "Commercial / legal"]
CONSIDERATIONS_SCHEMA = _obj({
    "bid_view": _obj({"recommendation": {"type": "string", "enum": ["Go", "Go with conditions", "Needs discussion", "No-go"]},
                      "reason": S}),
    "items": {"type": "array", "items": _obj({
        "category": {"type": "string", "enum": CONSIDERATION_CATEGORIES},
        "consideration": S, "impact": {"type": "string", "enum": ["High", "Medium", "Low"]}, "ref": S, "action": S,
        "owner": {"type": "string", "enum": CONSIDERATION_OWNERS}})}})
CONSIDERATIONS_SYSTEM = """You prepare the key considerations for a bid by Motadata (software OEM for ObserveOps and
ServiceOps, bidding through a partner / system integrator). You get the reviewed bid synopsis (tender facts, red flags,
dates), the reviewed Motadata scope summary, the risk analysis, PQ/TQ gaps, the compliance position and Motadata's own
knowledge (standard deviations, exclusions, partner scope).

List what the bid team must take care of before deciding and submitting: eligibility and OEM / MAF conditions Motadata
or the partner may not meet, commercial and payment terms, penalties, SLA and liquidated damages, Motadata product gaps,
what the partner must supply, what the customer must provide, deviations Motadata should take, timeline pressure, and
documents to arrange. For each give the RFP reference, the impact on the bid, the action to take and who owns it.
Merge duplicates; most important first; at most 20. Base everything on the material supplied; do not invent figures.
bid_view is an indicative recommendation for the bid / no-bid discussion with a one or two sentence reason."""

REVISE_SYSTEM = """You revise one step of an RFP bid review on the presales team's instruction.
You get the current content of the step as JSON and the instruction. Change only what the instruction asks for and keep
everything else exactly as it is, including wording, order and references. Where the instruction needs facts from the
RFP or the knowledge supplied, take them only from that material and give the reference. Return the complete revised
content in the same structure. The rules the step was originally written under follow.

"""

SCOPE_REVISE_SCHEMA = _obj({k: v for k, v in SCOPE_SCHEMA["properties"].items() if k != "matrix"}
                           | {"matrix_changes": SCOPE_SCHEMA["properties"]["matrix"]})
SCOPE_REVISE_NOTE = """For the requirement matrix, return in matrix_changes only the rows the instruction changes (with
the requirement number exactly as given); rows you leave out stay as they are. Return the summary lists in full."""

COMPLIANCE_REVISE_NOTE = """The team has reviewed these answers and gives an instruction below. Rewrite the answers
accordingly, still using only the sources supplied; where the instruction asserts something the sources do not support,
follow the instruction but say so in validation_remarks."""

PROPOSAL_SCHEMA =_obj({"sections": {"type": "array", "items": _obj({"placeholder": S, "content": S})}})
PROPOSAL_SYSTEM = """Write technical proposal content for each placeholder of the selected template, from the workspace
material supplied. Follow the style and structure of the sample documents where given, but take every fact only from the
workspace material and knowledge sources. Use plain paragraphs; start list items with "- "."""

DOC_AGENTS = {
    # key: (agent_key, schema, system, uses_knowledge)
    "analysis": ("rfp_analysis", ANALYSIS_SCHEMA, ANALYSIS_SYSTEM, False),
    # Uses the RFP analysis agent's model settings, so no new agent row (seed.py is shared code).
    "scope": ("rfp_analysis", SCOPE_SCHEMA, SCOPE_SYSTEM, True),
    "architecture": ("architecture_sizing", ARCH_SCHEMA, ARCH_SYSTEM, True),
    "risk": ("risk_gap", RISK_SCHEMA, RISK_SYSTEM, False),
    "pqtq": ("pq_tq", PQTQ_SCHEMA, PQTQ_SYSTEM, True),
    "boq": ("boq_licensing", BOQ_SCHEMA, BOQ_SYSTEM, True),
    "synopsis": ("executive_synopsis", SYNOPSIS_SCHEMA, SYNOPSIS_SYSTEM, False),
    "prebid": ("prebid_query", PREBID_SCHEMA, PREBID_SYSTEM, False),
    # Also on the RFP analysis agent's settings; works from the reviewed outputs, not the full RFP text.
    "considerations": ("rfp_analysis", CONSIDERATIONS_SCHEMA, CONSIDERATIONS_SYSTEM, True),
}
DOC_AGENT_LABELS = {"analysis": "RFP analysis", "scope": "Motadata scope", "architecture": "Architecture and sizing inputs",
                    "risk": "Risk and gap analysis", "pqtq": "PQ/TQ", "boq": "BOQ and licensing inputs",
                    "synopsis": "Executive synopsis", "prebid": "Pre-bid queries", "considerations": "Key considerations"}
