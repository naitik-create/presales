"""Deterministic sizing from the product team's rule table (§10.4). No free-text generation of hardware figures."""
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.knowledge import SizingRule


@dataclass
class SizingResult:
    status: str  # ok | missing_inputs | out_of_range | no_rules
    product: str
    inputs: dict
    missing: list[str] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)  # [{"component":..,"result":{..},"rule_id":..,"source":..,"conditions":..}]
    out_of_range: list[str] = field(default_factory=list)


def required_inputs(rules: list[SizingRule]) -> list[str]:
    seen: list[str] = []
    for r in rules:
        for k in r.conditions:
            if k not in seen:
                seen.append(k)
    return seen


def _matches(rule: SizingRule, inputs: dict) -> bool:
    for k, bounds in rule.conditions.items():
        v = inputs.get(k)
        lo, hi = (bounds + [None, None])[:2] if isinstance(bounds, list) else (None, None)
        if v is None:
            return False
        if lo is not None and v < lo:
            return False
        if hi is not None and v >= hi:
            return False
    return True


def apply_rules(db: Session, product: str, inputs: dict) -> SizingResult:
    rules = list(db.scalars(select(SizingRule).where(SizingRule.active.is_(True),
                                                     SizingRule.product.in_([product, "Both"]))
                            .order_by(SizingRule.component, SizingRule.sort)))
    if not rules:
        return SizingResult("no_rules", product, inputs)
    inputs = {k: float(v) for k, v in inputs.items() if v is not None and str(v).strip() != ""}
    by_component: dict[str, list[SizingRule]] = {}
    for r in rules:
        by_component.setdefault(r.component, []).append(r)
    missing = []
    for comp_rules in by_component.values():
        for k in required_inputs(comp_rules):
            if k not in inputs and k not in missing:
                missing.append(k)
    if missing:
        return SizingResult("missing_inputs", product, inputs, missing=missing)
    res = SizingResult("ok", product, inputs)
    for comp, comp_rules in by_component.items():
        match = next((r for r in comp_rules if _matches(r, inputs)), None)
        if match is None:
            res.out_of_range.append(comp)
        else:
            res.rows.append({"component": comp, "result": match.result, "rule_id": match.id, "source": match.source,
                             "conditions": match.conditions})
    if res.out_of_range:
        res.status = "out_of_range"
    return res


def render(res: SizingResult) -> str:
    if res.status == "no_rules":
        return (f"No sizing rules are configured for {res.product}. Sizing figures come only from the product team's "
                "sizing guide, so I cannot give hardware numbers. Please refer this to the product team.")
    if res.status == "missing_inputs":
        return "To size this deployment from the sizing rules I need: " + ", ".join(res.missing) + "."
    lines = [f"**Sizing for {res.product}** (from the sizing rule table)", "",
             "Inputs used: " + ", ".join(f"{k} = {v:g}" for k, v in res.inputs.items()), ""]
    for row in res.rows:
        spec = ", ".join(f"{k}: {v}" for k, v in row["result"].items())
        lines.append(f"- **{row['component']}**: {spec}  _(rule #{row['rule_id']}; source: {row['source'] or 'sizing guide'})_")
    if res.out_of_range:
        lines += ["", "These inputs fall outside the sizing table for: " + ", ".join(res.out_of_range)
                  + ". Please refer this to the product team."]
    return "\n".join(lines)
