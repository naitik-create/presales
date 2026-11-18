"use client";
import { Plus } from "lucide-react";
import { useState } from "react";
import { Alert, Badge, Button, Card, Field, Input, Modal, PageHeader, Select, Spinner, StatusBadge, Table, Tabs, Textarea } from "@/components/ui";
import { api, fmtDate } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useSession } from "@/lib/session";

export default function ScorecardPage() {
  const ov = useApi<any>("/scorecard/overview");
  const [tab, setTab] = useState("ledger");
  if (ov.error) return <Alert tone="error">{ov.error}</Alert>;
  if (!ov.data) return <Spinner />;
  const o = ov.data;
  const tabs = [{ key: "ledger", label: "Transactions" }, { key: "warnings", label: "Warnings" },
    ...(o.can.approve ? [{ key: "approvals", label: `Approvals (${o.pending?.length || 0})` }] : []),
    ...(o.can.manage_rules ? [{ key: "rules", label: "Rules" }] : []),
    ...(o.can.reports ? [{ key: "reports", label: "Reports" }] : [])];
  return (
    <>
      <PageHeader title="Team Scorecard" subtitle={`Quarter ${o.period.label} (${fmtDate(o.period.starts_on)} to ${fmtDate(o.period.ends_on)}). Everyone starts the quarter at 100 points.`} />
      <div className="mb-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        {o.me && (
          <Card title="My score">
            <div className="text-h2">{o.me.score}</div>
            <ul className="mt-2 text-sm">{Object.entries(o.me.by_category).map(([k, v]: any) => <li key={k} className="flex justify-between"><span>{k}</span><span>+{v.rewards} / {v.deductions}</span></li>)}</ul>
          </Card>
        )}
        {o.team && (
          <Card title="Team" className="lg:col-span-2">
            <Table head={["Participant", "Score", "Level"]} empty="No scoring participants.">
              {o.team.map((t: any) => <tr key={t.employee_id}><td>{t.name}</td><td className="font-semibold">{t.score}</td><td><Level score={t.score} /></td></tr>)}
            </Table>
          </Card>
        )}
      </div>
      <Tabs tabs={tabs} active={tab} onChange={setTab} />
      {tab === "ledger" && <Ledger canPropose={o.can.propose} canApprove={o.can.approve} reloadOv={ov.reload} />}
      {tab === "warnings" && <Warnings />}
      {tab === "approvals" && <Approvals pending={o.pending || []} reload={ov.reload} />}
      {tab === "rules" && <Rules />}
      {tab === "reports" && <Reports />}
    </>
  );
}

function Level({ score }: { score: number }) {
  if (score <= 0) return <Badge tone="error">Manager review</Badge>;
  if (score < 10) return <Badge tone="error">Third warning</Badge>;
  if (score < 30) return <Badge tone="warning">Second warning</Badge>;
  if (score < 50) return <Badge tone="warning">First warning</Badge>;
  return <Badge tone="success">In good standing</Badge>;
}

function Ledger({ canPropose, canApprove, reloadOv }: { canPropose: boolean; canApprove: boolean; reloadOv: () => void }) {
  const { me } = useSession();
  const tx = useApi<any[]>("/scorecard/transactions");
  const [propose, setPropose] = useState(false);
  const [comment, setComment] = useState<any | null>(null);
  return (
    <>
      {canPropose && <div className="mb-4 flex justify-end"><Button variant="primary" onClick={() => setPropose(true)}><Plus size={16} /> Propose transaction</Button></div>}
      <Table head={["#", "Employee", "Rule", "Points", "Reason and evidence", "Status", "Proposed", ""]} empty="No transactions this quarter.">
        {(tx.data || []).map((t) => (
          <tr key={t.id}>
            <td>{t.id}{t.reverses_id && <div className="text-sm text-muted">reverses #{t.reverses_id}</div>}</td><td>{t.employee}</td><td>{t.rule}</td>
            <td className={`font-semibold ${t.points < 0 ? "text-error" : "text-success"}`}>{t.points > 0 ? `+${t.points}` : t.points}</td>
            <td className="max-w-prose">{t.reason}<div className="text-sm text-muted">Evidence: {t.evidence}</div>
              {t.exception_note && <div className="text-sm">Exception: {t.exception_note}</div>}
              {t.comments.map((c: any) => <div key={c.id} className="mt-1 text-sm"><Badge tone={c.kind === "review_request" ? "warning" : "neutral"}>{c.kind.replace("_", " ")}</Badge> {c.author}: {c.text}</div>)}</td>
            <td><StatusBadge status={t.status} />{t.decided_by && <div className="text-sm text-muted">{t.decided_by}</div>}</td>
            <td>{fmtDate(t.proposed_at)}<div className="text-sm text-muted">{t.proposed_by}</div></td>
            <td className="whitespace-nowrap">
              {(t.employee_id === me?.id || canApprove) && <Button variant="ghost" onClick={() => setComment(t)}>Comment</Button>}
              {canApprove && t.status === "Approved" && !t.reverses_id && <Button variant="ghost" onClick={() => setComment({ ...t, reverse: true })}>Correct</Button>}
            </td>
          </tr>
        ))}
      </Table>
      {propose && <ProposeModal onClose={() => setPropose(false)} onSaved={() => { setPropose(false); tx.reload(); reloadOv(); }} />}
      {comment && <CommentModal t={comment} canApprove={canApprove} onClose={() => setComment(null)} onSaved={() => { setComment(null); tx.reload(); reloadOv(); }} />}
    </>
  );
}

function ProposeModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const people = useApi<any[]>("/scorecard/participants");
  const rules = useApi<any[]>("/scorecard/rules");
  const [b, setB] = useState({ employee_id: "", rule_id: "", reason: "", evidence: "" });
  const [err, setErr] = useState("");
  const rule = (rules.data || []).find((r) => String(r.id) === b.rule_id);
  async function save() {
    try { await api.post("/scorecard/transactions", { ...b, employee_id: Number(b.employee_id), rule_id: Number(b.rule_id) }); onSaved(); }
    catch (e) { setErr((e as Error).message); }
  }
  return (
    <Modal open title="Propose transaction" onClose={onClose}>
      <div className="flex flex-col gap-4">
        {err && <Alert tone="error">{err}</Alert>}
        <Alert tone="info">Approved leave and authorised work from home never cause a deduction. A deduction must relate to a procedure not followed, with evidence.</Alert>
        <Field label="Employee"><Select value={b.employee_id} onChange={(e) => setB({ ...b, employee_id: e.target.value })} options={[{ value: "", label: "Select" }, ...(people.data || []).map((p) => ({ value: p.id, label: p.name }))]} /></Field>
        <Field label="Rule"><Select value={b.rule_id} onChange={(e) => setB({ ...b, rule_id: e.target.value })} options={[{ value: "", label: "Select" }, ...(rules.data || []).map((r) => ({ value: r.id, label: `${r.name} (${r.points > 0 ? "+" : ""}${r.points})` }))]} /></Field>
        {rule?.description && <p className="text-sm text-muted">{rule.description}</p>}
        <Field label="Reason"><Textarea rows={2} value={b.reason} onChange={(e) => setB({ ...b, reason: e.target.value })} /></Field>
        <Field label="Evidence"><Textarea rows={2} value={b.evidence} onChange={(e) => setB({ ...b, evidence: e.target.value })} /></Field>
        <div><Button variant="primary" disabled={!b.employee_id || !b.rule_id || !b.reason.trim() || !b.evidence.trim()} onClick={save}>Submit for approval</Button></div>
      </div>
    </Modal>
  );
}

function CommentModal({ t, canApprove, onClose, onSaved }: { t: any; canApprove: boolean; onClose: () => void; onSaved: () => void }) {
  const { me } = useSession();
  const [kind, setKind] = useState(t.reverse ? "reverse" : t.employee_id === me?.id ? "comment" : "review_outcome");
  const [text, setText] = useState("");
  const [err, setErr] = useState("");
  async function save() {
    try {
      if (kind === "reverse") await api.post(`/scorecard/transactions/${t.id}/reverse`, { note: text });
      else await api.post(`/scorecard/transactions/${t.id}/comments`, { kind, text });
      onSaved();
    } catch (e) { setErr((e as Error).message); }
  }
  const options = t.reverse ? [{ value: "reverse", label: "Correction (new reversing transaction)" }] : [
    ...(t.employee_id === me?.id ? [{ value: "comment", label: "Comment" }, { value: "review_request", label: "Request a review" }] : []),
    ...(canApprove ? [{ value: "review_outcome", label: "Record review outcome" }, { value: "comment", label: "Comment" }] : [])];
  return (
    <Modal open title={`Transaction #${t.id}`} onClose={onClose}>
      <div className="flex flex-col gap-4">
        {err && <Alert tone="error">{err}</Alert>}
        <p className="text-sm text-muted">Comments, review requests and approved transactions cannot be edited or deleted.</p>
        <Field label="Type"><Select value={kind} onChange={(e) => setKind(e.target.value)} options={options} /></Field>
        <Field label="Text"><Textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} /></Field>
        <div><Button variant="primary" disabled={!text.trim()} onClick={save}>Submit</Button></div>
      </div>
    </Modal>
  );
}

function Approvals({ pending, reload }: { pending: any[]; reload: () => void }) {
  const [note, setNote] = useState<Record<number, string>>({});
  const [err, setErr] = useState("");
  const act = async (id: number, action: string, exception = false) => {
    try { await api.post(`/scorecard/transactions/${id}/${action}`, { note: note[id] || "", exception }); reload(); } catch (e) { setErr((e as Error).message); }
  };
  return (
    <>
      {err && <div className="mb-4"><Alert tone="error">{err}</Alert></div>}
      <Table head={["#", "Employee", "Rule", "Points", "Reason and evidence", "Note", ""]} empty="Nothing waiting for approval.">
        {pending.map((t) => (
          <tr key={t.id}><td>{t.id}</td><td>{t.employee}</td><td>{t.rule}</td><td className="font-semibold">{t.points}</td>
            <td className="max-w-prose">{t.reason}<div className="text-sm text-muted">Evidence: {t.evidence} · proposed by {t.proposed_by}</div></td>
            <td><Input value={note[t.id] || ""} onChange={(e) => setNote({ ...note, [t.id]: e.target.value })} placeholder="Note or exception" /></td>
            <td className="whitespace-nowrap"><Button variant="primary" onClick={() => act(t.id, "approve")}>Approve</Button>
              <Button variant="ghost" onClick={() => act(t.id, "reject")}>Reject</Button>
              <Button variant="ghost" onClick={() => act(t.id, "reject", true)}>Valid exception</Button></td></tr>
        ))}
      </Table>
    </>
  );
}

function Warnings() {
  const { me } = useSession();
  const { data, reload } = useApi<any[]>("/scorecard/warnings");
  return (
    <>
      <p className="mb-4 text-sm text-muted">The application records warnings only. Any employment decision follows company process outside the application.</p>
      <Table head={["Employee", "Quarter", "Level", "Score", "Reason", "Date", "Acknowledged"]} empty="No warnings.">
        {(data || []).map((w) => (
          <tr key={w.id}><td>{w.employee}</td><td>{w.period}</td><td><Badge tone={w.threshold <= 10 ? "error" : "warning"}>{w.level}</Badge></td><td>{w.score_at}</td>
            <td className="max-w-prose">{w.reason}</td><td>{fmtDate(w.at)}</td>
            <td>{w.acknowledged_at ? fmtDate(w.acknowledged_at) : w.employee_id === me?.id
              ? <Button onClick={() => api.post(`/scorecard/warnings/${w.id}/acknowledge`).then(reload)}>Acknowledge</Button> : "Not yet"}</td></tr>
        ))}
      </Table>
    </>
  );
}

function Rules() {
  const cats = useApi<any[]>("/scorecard/categories");
  const rules = useApi<any[]>("/scorecard/rules");
  const [edit, setEdit] = useState<any | null>(null);
  const [newCat, setNewCat] = useState("");
  const [err, setErr] = useState("");
  async function save() {
    try {
      const body = { category_id: Number(edit.category_id), name: edit.name, points: Number(edit.points), description: edit.description || "" };
      if (edit.id) await api.put(`/scorecard/rules/${edit.id}`, body); else await api.post("/scorecard/rules", body);
      setEdit(null); rules.reload();
    } catch (e) { setErr((e as Error).message); }
  }
  return (
    <>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-4">
        <p className="text-sm text-muted">Categories group rules for reporting only. Changing a rule applies to later transactions only.</p>
        <div className="flex gap-2">
          <Input placeholder="New category" value={newCat} onChange={(e) => setNewCat(e.target.value)} />
          <Button disabled={!newCat} onClick={() => api.post("/scorecard/categories", { name: newCat }).then(() => { setNewCat(""); cats.reload(); })}>Add category</Button>
          <Button variant="primary" onClick={() => setEdit({ category_id: cats.data?.[0]?.id, name: "", points: -5, description: "" })}><Plus size={16} /> Rule</Button>
        </div>
      </div>
      {(cats.data || []).map((c) => (
        <Card key={c.id} title={c.name} className="mb-4">
          <Table head={["Rule", "Points", "Description", ""]} empty="No rules in this category.">
            {(rules.data || []).filter((r) => r.category_id === c.id).map((r) => (
              <tr key={r.id}><td>{r.name}</td><td className="font-semibold">{r.points > 0 ? `+${r.points}` : r.points}</td><td>{r.description}</td>
                <td className="whitespace-nowrap"><Button variant="ghost" onClick={() => setEdit(r)}>Edit</Button>
                  <Button variant="ghost" onClick={() => api.del(`/scorecard/rules/${r.id}`).then(rules.reload)}>Retire</Button></td></tr>
            ))}
          </Table>
        </Card>
      ))}
      <Modal open={!!edit} title={edit?.id ? "Edit rule" : "New rule"} onClose={() => setEdit(null)}>
        {edit && <div className="flex flex-col gap-4">
          {err && <Alert tone="error">{err}</Alert>}
          <Field label="Category"><Select value={edit.category_id} onChange={(e) => setEdit({ ...edit, category_id: e.target.value })} options={(cats.data || []).map((c) => ({ value: c.id, label: c.name }))} /></Field>
          <Field label="Rule"><Input value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></Field>
          <Field label="Points (negative for deductions)"><Input type="number" value={edit.points} onChange={(e) => setEdit({ ...edit, points: e.target.value })} /></Field>
          <Field label="Description"><Textarea rows={2} value={edit.description} onChange={(e) => setEdit({ ...edit, description: e.target.value })} /></Field>
          <div><Button variant="primary" onClick={save}>Save</Button></div>
        </div>}
      </Modal>
    </>
  );
}

function Reports() {
  const { data } = useApi<any>("/scorecard/reports");
  if (!data) return <Spinner />;
  return (
    <div className="flex flex-col gap-6">
      <Card title={`Rewards and deductions by category · ${data.period}`}>
        <Table head={["Category", "Rewards", "Deductions"]}>
          {Object.entries(data.by_category).map(([k, v]: any) => <tr key={k}><td>{k}</td><td>+{v.rewards}</td><td>{v.deductions}</td></tr>)}
        </Table>
        <p className="mt-2 text-sm text-muted">{data.pending_count} transaction(s) pending approval.</p>
      </Card>
      <Card title="Quarter on quarter">
        <Table head={["Participant", ...data.periods]}>
          {data.quarter_on_quarter.map((r: any) => <tr key={r.employee_id}><td>{r.name}</td>{data.periods.map((p: string) => <td key={p}>{r.scores[p] ?? "-"}</td>)}</tr>)}
        </Table>
      </Card>
    </div>
  );
}
