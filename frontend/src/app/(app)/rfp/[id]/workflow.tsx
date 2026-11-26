"use client";
/** Guided bid workflow: each step is reviewed on the same screen, edited directly or revised by the AI on an
 *  instruction, approved, and only then downloaded. */
import { ArrowDown, ArrowUp, Check, Copy, Download, History, Pencil, Plus, RefreshCw, Sparkles, Trash2, Undo2 } from "lucide-react";
import { ReactNode, useState } from "react";
import { Alert, Badge, Button, Card, Field, Input, Modal, Select, Spinner, Table, Textarea, cx } from "@/components/ui";
import { api, download, fmtDate } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useSession } from "@/lib/session";

type Msg = { tone: "error" | "success" | "info" | "warning"; text: string } | null;
const STATUS: Record<string, { label: string; tone: "success" | "warning" | "info" | "neutral" }> = {
  approved: { label: "Approved", tone: "success" }, needs_review: { label: "Needs review", tone: "warning" },
  to_review: { label: "To review", tone: "info" }, not_run: { label: "Not generated", tone: "neutral" },
};
const AGENT_OF: Record<string, string> = { synopsis: "analysis", scope: "scope", considerations: "considerations", prebid: "prebid" };
const IMPACTS = ["High", "Medium", "Low"];
const IMPACT_TONE: Record<string, "error" | "warning" | "neutral"> = { High: "error", Medium: "warning", Low: "neutral" };
const OWNERS = ["Motadata", "Partner / SI", "Customer", "Shared", "Not applicable"];
const PRODUCTS = ["", "ObserveOps", "ServiceOps", "Platform", "Other"];
const OWNER_TONE: Record<string, "accent" | "info" | "warning" | "neutral"> = {
  Motadata: "accent", "Partner / SI": "info", Customer: "warning", Shared: "info", "Not applicable": "neutral",
};
const CONS_CATEGORIES = ["Eligibility / PQ", "OEM / MAF", "Commercial and payment", "Penalty / SLA / LD", "Motadata product gap",
  "Partner dependency", "Customer dependency", "Deviation to take", "Timeline", "Submission / documents", "Other"];
const CONS_OWNERS = ["Presales", "Sales", "Partner / SI", "Management", "Product team", "Commercial / legal"];
const PREBID_CATEGORIES = ["Restrictive or vendor-specific specification", "Eligibility / PQ relaxation", "OEM / MAF condition",
  "Quantity or sizing unclear", "Scope unclear", "SLA / penalty", "Payment / commercial terms", "Timeline", "Contradiction", "Other"];
const HINTS: Record<string, string> = {
  synopsis: "e.g. EMD is Rs 10 lakh as per corrigendum 1; add a red flag for the 7-day MAF deadline",
  scope: "e.g. R014 to R020 (rack, UPS, cabling) are Partner / SI; add Log management for R031",
  considerations: "e.g. add that the 3-year onsite engineer must come from the partner; mark the PBG item High",
  prebid: "e.g. add a query asking to relax OEM turnover to Rs 50 crore; make query 3 more polite",
  compliance: "e.g. make these Partially Compliant: custom integration needed through REST API",
};

export function BidWorkflow({ wid, step, setStep, busy, onJob, renderCompliance, renderBoq }: {
  wid: string; step: string | null; setStep: (k: string) => void; busy: boolean; onJob: () => void;
  renderCompliance: (onRevise: (ids: number[]) => void, reloadWorkflow: () => void) => ReactNode;
  renderBoq: (reloadWorkflow: () => void) => ReactNode;
}) {
  const wf = useApi<any>(`/rfp/workspaces/${wid}/workflow`);
  const agents = useApi<any>(`/rfp/workspaces/${wid}/agents`);
  const [msg, setMsg] = useState<Msg>(null);
  if (!wf.data || !agents.data) return <Spinner />;
  const stages: any[] = wf.data.stages;
  const active = stages.find((s) => s.key === step) || stages.find((s) => s.status !== "approved") || stages[0];
  const idx = stages.indexOf(active);
  const reload = () => { wf.reload(); agents.reload(); };
  const approvedCount = stages.filter((s) => s.status === "approved").length;
  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[240px_1fr]">
      <div className="flex flex-col gap-4">
        <ol className="flex flex-col gap-1" aria-label="Bid workflow steps">
          {stages.map((s, i) => (
            <li key={s.key}>
              <button type="button" onClick={() => { setStep(s.key); setMsg(null); }}
                className={cx("flex w-full items-start gap-3 rounded px-2 py-2 text-left", s.key === active.key ? "bg-mono-100" : "hover:bg-mono-50")}>
                <span className={cx("mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-sm font-semibold",
                  s.status === "approved" ? "border-success bg-success text-white" : s.key === active.key ? "border-black" : "border-border")}>
                  {s.status === "approved" ? <Check size={14} /> : i + 1}</span>
                <span className="flex flex-col gap-1">
                  <span className="text-sm font-semibold">{s.label}</span>
                  <Badge tone={STATUS[s.status].tone}>{STATUS[s.status].label}</Badge>
                </span>
              </button>
            </li>
          ))}
        </ol>
        <AllApproved wid={wid} count={approvedCount} total={stages.length} />
      </div>
      <div className="flex min-w-0 flex-col gap-4">
        {msg && <Alert tone={msg.tone}>{msg.text}</Alert>}
        <StepPanel key={`${active.key}-${active.run_id}-${active.status}`} wid={wid} s={active} n={idx + 1} busy={busy}
          out={AGENT_OF[active.key] ? agents.data[AGENT_OF[active.key]]?.output : null} compliance={wf.data.compliance}
          setMsg={setMsg} onChanged={(d?: any) => { if (d?.stages) wf.setData(d); reload(); }} onJob={onJob}
          next={stages[idx + 1]} goNext={() => stages[idx + 1] && setStep(stages[idx + 1].key)}
          renderCompliance={renderCompliance} renderBoq={renderBoq} reload={reload} />
      </div>
    </div>
  );
}

function AllApproved({ wid, count, total }: { wid: string; count: number; total: number }) {
  const { can } = useSession();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  if (!can("rfp.export")) return null;
  async function go() {
    setBusy(true); setErr("");
    try { const p = await api.post<any>(`/rfp/workspaces/${wid}/bid-pack`); await download(`/rfp/bid-packs/${p.id}/download`); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }
  return (
    <div className="rounded border border-border p-3 text-sm">
      <div className="mb-2 text-muted">{count} of {total} steps approved. Each step has its own downloads; this ZIP holds the approved ones only. No prices.</div>
      <Button disabled={!count || busy} onClick={go}>{busy ? <Spinner /> : <Download size={16} />} All approved (ZIP)</Button>
      {err && <div className="mt-2"><Alert tone="error">{err}</Alert></div>}
    </div>
  );
}

function StepPanel({ wid, s, n, busy, out, compliance, setMsg, onChanged, onJob, next, goNext, renderCompliance, renderBoq, reload }: any) {
  const { can } = useSession();
  const docStage = s.key in AGENT_OF;
  const [editing, setEditing] = useState(false);
  const [doc, setDoc] = useState<any>(out ? structuredClone(out) : null);
  const [asking, setAsking] = useState<number[] | null>(null);
  const [instruction, setInstruction] = useState("");
  const [working, setWorking] = useState(false);
  const [showVersions, setShowVersions] = useState(false);
  const [emailText, setEmailText] = useState<string | null>(null);
  const approved = s.status === "approved";
  const act = async (fn: () => Promise<any>, ok?: string) => {
    setWorking(true);
    try { const r = await fn(); onChanged(r); if (ok) setMsg({ tone: "success", text: ok }); return r; }
    catch (e) { setMsg({ tone: "error", text: (e as Error).message }); } finally { setWorking(false); }
  };
  const save = () => act(() => api.put(`/rfp/workspaces/${wid}/stages/${s.key}`, { output: doc }), `${s.label} saved as a new version. Approve it when it is right.`)
    .then(() => setEditing(false));
  const approve = (yes: boolean) => act(() => api.post(`/rfp/workspaces/${wid}/stages/${s.key}/approve`, { approved: yes }),
    yes ? `${s.label} approved. Its downloads are open.` : `${s.label} reopened.`);
  const regenerate = async () => {
    if (!window.confirm(`Generate ${s.label} again from the RFP? Your current version stays in the version history.`)) return;
    try { await api.post(`/rfp/workspaces/${wid}/agents/${AGENT_OF[s.key]}/run`); setMsg({ tone: "info", text: `${s.label} is being generated.` }); onJob(); }
    catch (e) { setMsg({ tone: "error", text: (e as Error).message }); }
  };
  const revise = async () => {
    try {
      await api.post(`/rfp/workspaces/${wid}/stages/${s.key}/revise`, { instruction, requirement_ids: asking || [] });
      setAsking(null); setInstruction("");
      setMsg({ tone: "info", text: "The AI is revising this step. The proposed change appears here to accept or discard." }); onJob();
    } catch (e) { setMsg({ tone: "error", text: (e as Error).message }); }
  };
  const copyEmail = async () => {
    try {
      const r = await api.get<any>(`/rfp/workspaces/${wid}/export?kind=considerations_text`);
      try { await navigator.clipboard.writeText(r.text); setMsg({ tone: "success", text: "Copied. Paste it into your email." }); }
      catch { setEmailText(r.text); }
    } catch (e) { setMsg({ tone: "error", text: (e as Error).message }); }
  };
  return (
    <>
      <Card title={<span className="flex flex-wrap items-center gap-2">Step {n} · {s.label} <Badge tone={STATUS[s.status].tone}>{STATUS[s.status].label}</Badge></span>}
        actions={<>
          {docStage && can("rfp.edit") && !approved && !editing && out && <Button disabled={busy} onClick={() => { setDoc(structuredClone(out)); setEditing(true); }}><Pencil size={16} /> Edit</Button>}
          {docStage && can("rfp.edit") && !approved && !editing && out && <Button disabled={busy} onClick={() => setAsking([])}><Sparkles size={16} /> Ask AI to change</Button>}
          {docStage && can("rfp.edit") && !approved && !editing && <Button variant="ghost" disabled={busy} onClick={regenerate}><RefreshCw size={16} /> {out ? "Regenerate" : "Generate"}</Button>}
          {docStage && s.versions > 1 && <Button variant="ghost" onClick={() => setShowVersions(true)}><History size={16} /> Versions ({s.versions})</Button>}
          {can("rfp.approve") && !approved && !editing && s.status !== "not_run" &&
            <Button variant="primary" disabled={working || busy || s.blocked_by.length > 0 || !!s.draft} onClick={() => approve(true)}><Check size={16} /> Approve</Button>}
          {can("rfp.approve") && approved && s.key !== "compliance" && <Button disabled={working} onClick={() => approve(false)}><Undo2 size={16} /> Reopen</Button>}
        </>}>
        <div className="flex flex-col gap-3">
          <p className="text-sm text-muted">
            {s.run_id && `Version ${s.versions || 1} · ${s.how} · ${fmtDate(s.at, true)}`}
            {approved && s.approved_by && ` · Approved by ${s.approved_by} ${fmtDate(s.approved_at, true)}`}
            {s.depends_on.length > 0 && ` · Built on: ${s.depends_on.join(", ")}`}
          </p>
          {s.reason && <Alert tone="warning">{s.reason}. Review and approve again.</Alert>}
          {s.inputs_changed.length > 0 && <Alert tone="warning">{s.inputs_changed.join(" and ")} changed after this version was made. Check it, or Regenerate to rebuild it from the latest {s.inputs_changed.join(" and ")}.</Alert>}
          {!approved && s.blocked_by.length > 0 && <Alert tone="info">Approve {s.blocked_by.join(" and ")} first; this step is built on it. You can review and edit it meanwhile.</Alert>}
          {s.draft && <DraftCard wid={wid} s={s} working={working} act={act} />}
          {asking && (
            <div className="flex flex-col gap-2 rounded border border-border p-3">
              <Field label={s.key === "compliance" ? `What should change in the ${asking.length} selected answer(s)?` : "What should change?"} hint={HINTS[s.key]}>
                <Textarea rows={3} value={instruction} onChange={(e) => setInstruction(e.target.value)} autoFocus />
              </Field>
              <div className="flex gap-2">
                <Button variant="primary" disabled={instruction.trim().length < 3 || busy} onClick={revise}><Sparkles size={16} /> Ask AI</Button>
                <Button variant="ghost" onClick={() => setAsking(null)}>Cancel</Button>
              </div>
              <p className="text-sm text-muted">Only this step changes. You see what changed and accept or discard it.</p>
            </div>
          )}
          <div className="flex flex-wrap items-center gap-2">
            {can("rfp.export") && s.downloads.map((d: any) => (
              <Button key={d.kind} disabled={!approved || editing} onClick={() => download(`/rfp/workspaces/${wid}/export?kind=${d.kind}`).catch((e: Error) => setMsg({ tone: "error", text: e.message }))}>
                <Download size={16} /> {d.label}</Button>))}
            {s.key === "considerations" && can("rfp.export") && <Button disabled={!approved} onClick={copyEmail}><Copy size={16} /> Copy for email</Button>}
            {!approved && <span className="text-sm text-muted">Downloads open after approval.</span>}
            {approved && next && <Button variant="ghost" onClick={goNext}>Next: {next.label} →</Button>}
          </div>
        </div>
      </Card>

      {editing && (
        <div className="sticky top-0 z-10 flex items-center gap-2 rounded border border-accent bg-white p-2">
          <span className="text-sm font-semibold">Editing {s.label}</span>
          <Button variant="primary" disabled={working} onClick={save}>Save as new version</Button>
          <Button variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>
        </div>
      )}

      {s.status === "not_run" && docStage && <Card><p className="text-sm text-muted">Not generated yet. Analyse the RFP on the Documents tab, or press Generate.</p></Card>}
      {s.key === "synopsis" && out && <SynopsisView d={editing ? doc : out} editing={editing} set={setDoc} />}
      {s.key === "scope" && out && <ScopeView wid={wid} d={editing ? doc : out} editing={editing} set={setDoc} />}
      {s.key === "considerations" && out && <ConsiderationsView d={editing ? doc : out} editing={editing} set={setDoc} />}
      {s.key === "prebid" && out && <PrebidView d={editing ? doc : out} editing={editing} set={setDoc} />}
      {s.key === "compliance" && <>
        <ComplianceSummary c={compliance} />
        {renderCompliance((ids: number[]) => { if (!approved) setAsking(ids); }, reload)}
      </>}
      {s.key === "boq" && renderBoq(reload)}

      {showVersions && <Versions wid={wid} s={s} onClose={() => setShowVersions(false)} act={act} />}
      <Modal open={emailText !== null} title="Key considerations for email" onClose={() => setEmailText(null)} wide>
        <p className="mb-2 text-sm text-muted">Select all and copy (the browser blocked automatic copying on this connection).</p>
        <Textarea rows={18} readOnly value={emailText || ""} onFocus={(e) => e.currentTarget.select()} />
      </Modal>
    </>
  );
}

function DraftCard({ wid, s, working, act }: any) {
  const { can } = useSession();
  const d = s.draft;
  const accept = () => act(() => api.post(`/rfp/workspaces/${wid}/stages/${s.key}/draft/accept`), "Change accepted as a new version. Approve the step when it is right.");
  const discard = () => act(() => api.post(`/rfp/workspaces/${wid}/stages/${s.key}/draft/discard`), "Proposed change discarded.");
  const changes: any[] = s.key === "compliance"
    ? (d.answers || []).flatMap((a: any) => ["status", "response", "explanation", "validation_remarks"]
      .filter((k) => (a.before[k] || "") !== (a.after[k] || "")).map((k) => ({ where: `${a.number} · ${k.replace("_", " ")}`, before: a.before[k], after: a.after[k] })))
    : d.changes || [];
  return (
    <div className="flex flex-col gap-2 rounded border border-accent p-3">
      <div className="text-sm"><b>Proposed by the AI</b> on {d.by ? `${d.by}'s` : "your"} request: “{d.instruction}” <span className="text-muted">· {fmtDate(d.at, true)}</span></div>
      {d.outdated && <Alert tone="warning">The step was changed after this proposal was made. Discard it and ask again.</Alert>}
      <Table head={["Where", "Before", "After"]} empty="The AI made no changes.">
        {changes.map((c, i) => (
          <tr key={i}><td className="whitespace-nowrap text-sm font-semibold">{c.where}</td>
            <td className="max-w-prose text-sm text-muted line-through decoration-mono-300">{c.before}</td>
            <td className="max-w-prose text-sm">{c.after}</td></tr>))}
      </Table>
      {can("rfp.edit") && <div className="flex gap-2">
        <Button variant="primary" disabled={working || d.outdated || !changes.length} onClick={accept}><Check size={16} /> Accept</Button>
        <Button disabled={working} onClick={discard}>Discard</Button>
      </div>}
    </div>
  );
}

function Versions({ wid, s, onClose, act }: any) {
  const { can } = useSession();
  const v = useApi<any[]>(`/rfp/workspaces/${wid}/stages/${s.key}/versions`);
  return (
    <Modal open title={`${s.label} · versions`} onClose={onClose}>
      {!v.data ? <Spinner /> : (
        <Table head={["Version", "Made", "How", ""]}>
          {v.data.map((x) => (
            <tr key={x.id}><td className="font-semibold">v{x.version}{x.current && <> <Badge tone="info">current</Badge></>}{x.approved && <> <Badge tone="success">approved</Badge></>}</td>
              <td>{fmtDate(x.at, true)}</td><td>{x.how}{x.revision > 1 && <span className="text-muted"> · RFP rev {x.revision}</span>}</td>
              <td>{!x.current && can("rfp.edit") && s.status !== "approved" &&
                <Button variant="ghost" onClick={() => act(() => api.post(`/rfp/workspaces/${wid}/stages/${s.key}/versions/${x.id}/restore`), `v${x.version} restored as a new version.`).then(onClose)}>Restore</Button>}</td></tr>))}
        </Table>)}
    </Modal>
  );
}

function ComplianceSummary({ c }: { c: any }) {
  return (
    <Card title="Compliance position">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span><b>{c.approved}</b> of {c.total} answers approved</span>
        {Object.entries(c.by_status || {}).map(([k, v]) => <Badge key={k} tone={k === "Compliant" ? "success" : k === "Non-Compliant" ? "error" : k === "Not Applicable" ? "neutral" : "warning"}>{k}: {String(v)}</Badge>)}
      </div>
      <p className="mt-2 text-sm text-muted">{c.from_past_rfps} answer(s) use a past submitted RFP ({c.only_past_rfps} from past RFPs alone; the rest also cite current docs).
        Open an answer to see which past bid it came from. Select answers and use “Ask AI to change selected” to revise them, or edit one directly.
        Approving the step approves every answer.</p>
    </Card>
  );
}

// ---------- step views (read and edit) ----------
type Col = { key: string; label: string; kind?: "text" | "area" | "select"; options?: string[] };

function Rows({ rows, cols, editing, onChange, empty = "None", addLabel = "Add row", reorder }: {
  rows: any[]; cols: Col[]; editing: boolean; onChange: (r: any[]) => void; empty?: string; addLabel?: string; reorder?: boolean;
}) {
  const set = (i: number, k: string, v: any) => onChange(rows.map((r, n) => n === i ? { ...r, [k]: v } : r));
  const move = (i: number, d: number) => {
    const j = i + d; if (j < 0 || j >= rows.length) return;
    const next = [...rows]; [next[i], next[j]] = [next[j], next[i]]; onChange(next);
  };
  if (!editing && !rows.length) return <p className="text-sm text-muted">{empty}</p>;
  return (
    <div className="flex flex-col gap-2">
      <Table head={[...cols.map((c) => c.label), ...(editing ? [""] : [])]}>
        {rows.map((r, i) => (
          <tr key={i}>
            {cols.map((c) => (
              <td key={c.key} className={c.kind === "area" ? "min-w-[220px] max-w-prose" : ""}>
                {!editing ? (c.key === "impact" && r[c.key] ? <Badge tone={IMPACT_TONE[r[c.key]] || "neutral"}>{r[c.key]}</Badge>
                  : <span className="whitespace-pre-wrap text-sm">{String(r[c.key] ?? "")}</span>)
                  : c.kind === "select" ? <Select value={r[c.key] ?? ""} onChange={(e) => set(i, c.key, e.target.value)} options={c.options || []} />
                  : c.kind === "area" ? <Textarea rows={2} value={r[c.key] ?? ""} onChange={(e) => set(i, c.key, e.target.value)} />
                  : <Input value={r[c.key] ?? ""} onChange={(e) => set(i, c.key, e.target.value)} />}
              </td>))}
            {editing && <td className="whitespace-nowrap">
              {reorder && <><Button variant="ghost" aria-label="Move up" onClick={() => move(i, -1)}><ArrowUp size={14} /></Button>
                <Button variant="ghost" aria-label="Move down" onClick={() => move(i, 1)}><ArrowDown size={14} /></Button></>}
              <Button variant="ghost" aria-label="Remove" onClick={() => onChange(rows.filter((_, n) => n !== i))}><Trash2 size={14} /></Button></td>}
          </tr>))}
      </Table>
      {editing && <div><Button variant="ghost" onClick={() => onChange([...rows, Object.fromEntries(cols.map((c) => [c.key, c.kind === "select" ? (c.options || [""])[0] : ""]))])}><Plus size={14} /> {addLabel}</Button></div>}
    </div>
  );
}

function Lines({ items, editing, onChange }: { items: string[]; editing: boolean; onChange: (v: string[]) => void }) {
  if (editing) return <Textarea rows={Math.max(3, items.length + 1)} value={items.join("\n")} onChange={(e) => onChange(e.target.value.split("\n"))} />;
  if (!items.length) return <p className="text-sm text-muted">None</p>;
  return <ul className="list-disc pl-5 text-sm">{items.filter(Boolean).map((x, i) => <li key={i}>{x}</li>)}</ul>;
}

const SYN_LISTS: [string, string][] = [["objectives", "Objectives"], ["scope", "Scope of work"], ["submission_requirements", "Submission requirements"],
  ["milestones", "Milestones"], ["mandatory_conditions", "Mandatory conditions"], ["missing_information", "Missing information"]];

function SynopsisView({ d, editing, set }: any) {
  const upd = (k: string, v: any) => set({ ...d, [k]: v });
  return (
    <div className="flex flex-col gap-4">
      <Card title="Summary">{editing ? <Textarea rows={5} value={d.summary || ""} onChange={(e) => upd("summary", e.target.value)} />
        : <p className="whitespace-pre-wrap text-sm">{d.summary}</p>}</Card>
      <Card title="Bid facts">
        <Table head={["Item", "Value", "RFP reference"]}>
          {(d.bid_facts || []).map((f: any, i: number) => (
            <tr key={f.item}><td className="text-sm font-semibold">{f.item}</td>
              <td className="max-w-prose">{editing ? <Textarea rows={1} value={f.value} onChange={(e) => upd("bid_facts", d.bid_facts.map((x: any, n: number) => n === i ? { ...x, value: e.target.value } : x))} />
                : <span className={cx("text-sm", f.value === "Not stated" && "text-muted")}>{f.value}</span>}</td>
              <td>{editing ? <Input value={f.ref} onChange={(e) => upd("bid_facts", d.bid_facts.map((x: any, n: number) => n === i ? { ...x, ref: e.target.value } : x))} />
                : <span className="text-sm text-muted">{f.ref}</span>}</td></tr>))}
        </Table>
      </Card>
      <Card title="Key dates"><Rows rows={d.dates || []} editing={editing} onChange={(v) => upd("dates", v)} addLabel="Add date"
        cols={[{ key: "item", label: "Event" }, { key: "date", label: "Date" }, { key: "ref", label: "Reference" }]} /></Card>
      <Card title="Red flags"><Rows rows={d.red_flags || []} editing={editing} onChange={(v) => upd("red_flags", v)} addLabel="Add red flag"
        cols={[{ key: "issue", label: "Issue", kind: "area" }, { key: "impact", label: "Impact", kind: "select", options: IMPACTS }, { key: "ref", label: "Reference" }]} /></Card>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        {SYN_LISTS.map(([k, label]) => <Card key={k} title={label}><Lines items={d[k] || []} editing={editing} onChange={(v) => upd(k, v)} /></Card>)}
      </div>
    </div>
  );
}

function ScopeView({ wid, d, editing, set }: any) {
  const reqs = useApi<any[]>(`/rfp/workspaces/${wid}/requirements`);
  const [owner, setOwner] = useState("");
  const text: Record<string, any> = Object.fromEntries((reqs.data || []).map((r) => [r.number, r]));
  const upd = (k: string, v: any) => set({ ...d, [k]: v });
  const setRow = (num: string, k: string, v: string) => upd("matrix", d.matrix.map((m: any) => m.number === num ? { ...m, [k]: v } : m));
  const rows = (d.matrix || []).filter((m: any) => !owner || m.owner === owner);
  const ITEM: Col[] = [{ key: "item", label: "Item", kind: "area" }, { key: "ref", label: "Reference" }];
  return (
    <div className="flex flex-col gap-4">
      <Card title="Motadata modules in scope"><Rows rows={d.modules_in_scope || []} editing={editing} onChange={(v) => upd("modules_in_scope", v)} addLabel="Add module"
        cols={[{ key: "product", label: "Product", kind: "select", options: PRODUCTS.slice(1) }, { key: "module", label: "Module" }, { key: "basis", label: "Basis (requirements)", kind: "area" }]} /></Card>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card title="Partner / SI supplies"><Rows rows={d.partner_items || []} editing={editing} onChange={(v) => upd("partner_items", v)} cols={ITEM} /></Card>
        <Card title="Customer provides"><Rows rows={d.customer_prerequisites || []} editing={editing} onChange={(v) => upd("customer_prerequisites", v)} cols={ITEM} /></Card>
        <Card title="Out of scope"><Rows rows={d.out_of_scope || []} editing={editing} onChange={(v) => upd("out_of_scope", v)} cols={ITEM} /></Card>
        <Card title="Motadata gaps"><Rows rows={d.motadata_gaps || []} editing={editing} onChange={(v) => upd("motadata_gaps", v)}
          cols={[...ITEM, { key: "note", label: "Note" }]} /></Card>
      </div>
      <Card title={`Scope matrix (${rows.length})`} actions={<Select value={owner} onChange={(e) => setOwner(e.target.value)}
        options={[{ value: "", label: "All owners" }, ...OWNERS.map((o) => ({ value: o, label: `${o} (${(d.matrix || []).filter((m: any) => m.owner === o).length})` }))]} />}>
        <Table head={["No.", "Requirement", "Owner", "Product", "Module", "Note"]} empty="No requirements.">
          {rows.map((m: any) => (
            <tr key={m.number}>
              <td className="font-semibold">{m.number}</td>
              <td className="max-w-prose text-sm">{text[m.number]?.text}{text[m.number]?.answer && <div className="text-muted">{text[m.number].answer.status}</div>}</td>
              {editing ? <>
                <td><Select value={m.owner} onChange={(e) => setRow(m.number, "owner", e.target.value)} options={OWNERS} /></td>
                <td><Select value={m.product} onChange={(e) => setRow(m.number, "product", e.target.value)} options={PRODUCTS} /></td>
                <td><Input value={m.module} onChange={(e) => setRow(m.number, "module", e.target.value)} /></td>
                <td><Input value={m.note} onChange={(e) => setRow(m.number, "note", e.target.value)} /></td>
              </> : <>
                <td><Badge tone={OWNER_TONE[m.owner] || "neutral"}>{m.owner}</Badge></td><td className="text-sm">{m.product}</td>
                <td className="text-sm">{m.module}</td><td className="text-sm text-muted">{m.note}</td>
              </>}
            </tr>))}
        </Table>
      </Card>
    </div>
  );
}

function ConsiderationsView({ d, editing, set }: any) {
  const view = d.bid_view || { recommendation: "Needs discussion", reason: "" };
  return (
    <div className="flex flex-col gap-4">
      <Card title="Indicative bid view">
        {editing ? <div className="flex flex-col gap-2">
          <Field label="Recommendation"><Select value={view.recommendation} onChange={(e) => set({ ...d, bid_view: { ...view, recommendation: e.target.value } })}
            options={["Go", "Go with conditions", "Needs discussion", "No-go"]} /></Field>
          <Field label="Reason"><Textarea rows={2} value={view.reason} onChange={(e) => set({ ...d, bid_view: { ...view, reason: e.target.value } })} /></Field>
        </div> : <p className="text-sm"><Badge tone={view.recommendation === "Go" ? "success" : view.recommendation === "No-go" ? "error" : "warning"}>{view.recommendation}</Badge> {view.reason}</p>}
      </Card>
      <Card title={`Considerations (${(d.items || []).length})`}>
        <Rows rows={d.items || []} editing={editing} onChange={(v) => set({ ...d, items: v })} addLabel="Add consideration" reorder
          cols={[{ key: "impact", label: "Impact", kind: "select", options: IMPACTS }, { key: "category", label: "Category", kind: "select", options: CONS_CATEGORIES },
            { key: "consideration", label: "Consideration", kind: "area" }, { key: "ref", label: "Reference" },
            { key: "action", label: "Action", kind: "area" }, { key: "owner", label: "Owner", kind: "select", options: CONS_OWNERS }]} />
      </Card>
    </div>
  );
}

function PrebidView({ d, editing, set }: any) {
  const fmt = d.tender_format;
  const qs: any[] = (d.queries || []).map((q: any, i: number) => ({ ...q, selected: "selected" in q ? q.selected : i < 10 }));
  const picked = qs.filter((q) => q.selected).length;
  const setQs = (v: any[]) => set({ ...d, queries: v.map((q, i) => ({ ...q, rank: i + 1 })) });
  return (
    <div className="flex flex-col gap-4">
      {fmt?.found
        ? <Alert tone="info">Format prescribed by the RFP{fmt.ref && ` (${fmt.ref})`}: {fmt.columns.map((c: any) => c.heading).join(" | ")}
          {fmt.instructions && <div className="mt-1">Submission: {fmt.instructions}</div>}</Alert>
        : <Alert tone="info">The RFP prescribes no pre-bid query format, so downloads use the standard format.</Alert>}
      <Card title={`Queries · ${picked} of ${qs.length} to submit${picked !== 10 ? " (usually 10)" : ""}`}>
        {editing && <p className="mb-2 text-sm text-muted">Tick the queries to submit; only ticked ones go into the downloads, in this order.</p>}
        <Table head={["Submit", "Rank", "Impact", "Reference", "Query", "Suggested change", "Why it matters (internal)", ...(editing ? [""] : [])]} empty="No queries.">
          {qs.map((q, i) => {
            const upd = (k: string, v: any) => setQs(qs.map((x, n) => n === i ? { ...x, [k]: v } : x));
            const move = (dlt: number) => { const j = i + dlt; if (j < 0 || j >= qs.length) return; const nx = [...qs]; [nx[i], nx[j]] = [nx[j], nx[i]]; setQs(nx); };
            return (
              <tr key={i} className={q.selected ? "" : "opacity-60"}>
                <td><input type="checkbox" aria-label={`Submit query ${i + 1}`} checked={!!q.selected} disabled={!editing} onChange={(e) => upd("selected", e.target.checked)} /></td>
                <td className="font-semibold">{i + 1}</td>
                <td>{editing ? <><Select value={q.impact || "Medium"} onChange={(e) => upd("impact", e.target.value)} options={IMPACTS} />
                  <Select value={q.category || "Other"} onChange={(e) => upd("category", e.target.value)} options={PREBID_CATEGORIES} /></>
                  : <>{q.impact && <Badge tone={IMPACT_TONE[q.impact] || "neutral"}>{q.impact}</Badge>}<div className="text-sm text-muted">{q.category}</div></>}</td>
                <td className="min-w-[140px]">{editing ? <><Input placeholder="Reference" value={q.ref || ""} onChange={(e) => upd("ref", e.target.value)} />
                  <Textarea rows={2} placeholder="Clause text" value={q.clause_text || ""} onChange={(e) => upd("clause_text", e.target.value)} /></>
                  : <span className="text-sm text-muted">{q.ref}{q.clause_text && <div className="mt-1">“{q.clause_text}”</div>}</span>}</td>
                <td className="min-w-[220px] max-w-prose">{editing ? <Textarea rows={3} value={q.query || ""} onChange={(e) => upd("query", e.target.value)} /> : <span className="text-sm">{q.query}</span>}</td>
                <td className="min-w-[180px] max-w-prose">{editing ? <Textarea rows={3} value={q.suggested_change || ""} onChange={(e) => upd("suggested_change", e.target.value)} /> : <span className="text-sm">{q.suggested_change}</span>}</td>
                <td className="min-w-[180px] max-w-prose">{editing ? <Textarea rows={3} value={q.reason || ""} onChange={(e) => upd("reason", e.target.value)} /> : <span className="text-sm text-muted">{q.reason}</span>}</td>
                {editing && <td className="whitespace-nowrap">
                  <Button variant="ghost" aria-label="Move up" onClick={() => move(-1)}><ArrowUp size={14} /></Button>
                  <Button variant="ghost" aria-label="Move down" onClick={() => move(1)}><ArrowDown size={14} /></Button>
                  <Button variant="ghost" aria-label="Remove" onClick={() => setQs(qs.filter((_, n) => n !== i))}><Trash2 size={14} /></Button></td>}
              </tr>);
          })}
        </Table>
        {editing && <div className="mt-2"><Button variant="ghost" onClick={() => setQs([...qs, { query: "", ref: "", clause_text: "", suggested_change: "", reason: "", impact: "Medium", category: "Other", selected: true }])}><Plus size={14} /> Add query</Button></div>}
      </Card>
    </div>
  );
}
