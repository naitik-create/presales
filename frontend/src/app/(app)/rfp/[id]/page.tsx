"use client";
import { ArrowDown, ArrowUp, CheckCheck, Download, Play, RefreshCw, Sparkles, Upload } from "lucide-react";
import { use, useState } from "react";
import { Alert, Badge, Button, Card, Field, Input, Modal, PageHeader, Progress, Select, Spinner, StatusBadge, Table, Tabs, Textarea } from "@/components/ui";
import { api, download, fmtDate, money } from "@/lib/api";
import { useApi, useJobPoll } from "@/lib/hooks";
import { useSession } from "@/lib/session";

const STATUSES = ["Compliant", "Partially Compliant", "Non-Compliant", "Needs Product Validation", "Not Applicable"];
const AGENT_LABELS: Record<string, string> = {
  synopsis: "Executive synopsis", analysis: "RFP analysis", scope: "Motadata scope", architecture: "Architecture and sizing inputs", risk: "Risk and gap analysis",
  pqtq: "PQ/TQ", boq: "BOQ and licensing inputs", prebid: "Pre-bid queries",
};

export default function WorkspacePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const ws = useApi<any>(`/rfp/workspaces/${id}`);
  const [tab, setTab] = useState("documents");
  const [msg, setMsg] = useState<{ tone: "error" | "success" | "info"; text: string } | null>(null);
  const running = ws.data?.job && ["Queued", "Processing"].includes(ws.data.job.status) ? ws.data.job.id : null;
  const job = useJobPoll(running, () => ws.reload());
  if (!ws.data) return <Spinner />;
  const w = ws.data;
  const run = async (fn: () => Promise<any>, ok: string) => {
    try { await fn(); setMsg({ tone: "success", text: ok }); ws.reload(); } catch (e) { setMsg({ tone: "error", text: (e as Error).message }); }
  };
  return (
    <>
      <PageHeader title={w.name} subtitle={<span className="flex flex-wrap items-center gap-2"><StatusBadge status={w.status} />
        {w.customer && <span>{w.customer}</span>}<span>Revision {w.revision}</span>{w.due_date && <span>Due {fmtDate(w.due_date)}</span>}
        <span>Estimated AI cost {money(w.estimated_cost)}</span></span>} />
      {msg && <div className="mb-4"><Alert tone={msg.tone}>{msg.text}</Alert></div>}
      {running && job && (
        <div className="mb-4"><Card title={`Job #${job.id} · ${job.status}`} actions={<Button onClick={() => run(() => api.post(`/admin/jobs/${job.id}/cancel`), "Cancel requested")}>Cancel</Button>}>
          <div className="mb-2 text-sm">{job.message}</div><Progress value={job.progress} /></Card></div>
      )}
      {w.job?.status === "Failed" && <div className="mb-4"><Alert tone="error">Last job failed: {w.job.error}</Alert></div>}
      <Tabs active={tab} onChange={setTab} tabs={[
        { key: "documents", label: "Documents" }, { key: "requirements", label: "Requirements and answers" },
        { key: "analysis", label: "Analysis" }, { key: "proposal", label: "Proposal" },
        { key: "export", label: "Export and submit" }]} />
      {tab === "documents" && <Documents w={w} reload={ws.reload} run={run} busy={!!running} />}
      {tab === "requirements" && <Requirements wid={id} busy={!!running} run={run} />}
      {tab === "analysis" && <Analysis wid={id} busy={!!running} run={run} />}
      {tab === "proposal" && <Proposal w={w} run={run} busy={!!running} />}
      {tab === "export" && <ExportTab w={w} run={run} />}
    </>
  );
}

function Documents({ w, reload, run, busy }: any) {
  const { can } = useSession();
  const [role, setRole] = useState("rfp");
  const [err, setErr] = useState("");
  async function upload(form: FormData) {
    form.set("role", role);
    try { await api.upload(`/rfp/workspaces/${w.id}/documents`, form); reload(); } catch (e) { setErr((e as Error).message); }
  }
  const hasRfp = w.documents.some((d: any) => d.role === "rfp");
  return (
    <div className="flex flex-col gap-4">
      {err && <Alert tone="error">{err}</Alert>}
      {can("rfp.edit") && (
        <Card title="Upload">
          <form className="flex flex-wrap items-end gap-4" onSubmit={(e) => { e.preventDefault(); upload(new FormData(e.currentTarget)); e.currentTarget.reset(); }}>
            <Field label="Type"><Select value={role} onChange={(e) => setRole(e.target.value)} options={[
              { value: "rfp", label: "RFP documents" }, { value: "corrigendum", label: "Corrigendum (changes only)" },
              { value: "revised", label: "Revised RFP (full replacement)" }, { value: "submitted", label: "Final submitted documents" }]} /></Field>
            <Field label="Files" hint="PDF, DOCX, DOC, XLSX, XLS, CSV, TXT or ZIP. Scanned English PDFs are read with OCR."><input type="file" name="files" multiple required /></Field>
            <Button type="submit"><Upload size={16} /> Upload</Button>
          </form>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button variant="primary" disabled={!hasRfp || busy} onClick={() => run(() => api.post(`/rfp/workspaces/${w.id}/process`), "Processing queued.")}><Play size={16} /> Analyse RFP</Button>
            <Button disabled={busy} onClick={() => run(() => api.post(`/rfp/workspaces/${w.id}/corrigendum?mode=corrigendum`), "Corrigendum queued.")}>Process corrigendum</Button>
            <Button disabled={busy} onClick={() => run(() => api.post(`/rfp/workspaces/${w.id}/corrigendum?mode=revised`), "Revised RFP queued.")}>Process revised RFP</Button>
          </div>
        </Card>
      )}
      <Table head={["Document", "Type", "Revision", "Status", "Extracted", "Uploaded", ""]} empty="No documents uploaded.">
        {w.documents.map((d: any) => (
          <tr key={d.id}><td className="font-semibold">{d.name}</td><td>{d.role}</td><td>{d.revision}</td><td><StatusBadge status={d.status} /></td>
            <td>{d.segments} parts{d.used_ocr && " (OCR)"}</td><td>{fmtDate(d.uploaded_at, true)}</td>
            <td><Button variant="ghost" onClick={() => download(`/rfp/documents/${d.id}/download`)}><Download size={16} /></Button></td></tr>
        ))}
      </Table>
    </div>
  );
}

function Requirements({ wid, busy, run }: any) {
  const { can } = useSession();
  const [filter, setFilter] = useState({ status: "", change: "", approved: "", q: "" });
  const qs = new URLSearchParams(Object.entries(filter).filter(([, v]) => v) as [string, string][]).toString();
  const { data, loading, reload } = useApi<any[]>(`/rfp/workspaces/${wid}/requirements?${qs}`, [qs]);
  const [sel, setSel] = useState<number[]>([]);
  const [open, setOpen] = useState<any | null>(null);
  const agents = useApi<any>(`/rfp/workspaces/${wid}/agents`);
  const scopeBy: Record<string, any> = Object.fromEntries((agents.data?.scope?.output?.matrix || []).map((m: any) => [m.number, m]));
  const approve = (ids: number[], approved = true) => run(() => api.post(`/rfp/workspaces/${wid}/approve`, { requirement_ids: ids, approved }), `${ids.length} answer(s) updated`).then(reload);
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Status"><Select value={filter.status} onChange={(e) => setFilter({ ...filter, status: e.target.value })} options={["", ...STATUSES]} /></Field>
        <Field label="Change"><Select value={filter.change} onChange={(e) => setFilter({ ...filter, change: e.target.value })} options={["", "added", "changed"]} /></Field>
        <Field label="Approval"><Select value={filter.approved} onChange={(e) => setFilter({ ...filter, approved: e.target.value })}
          options={[{ value: "", label: "All" }, { value: "false", label: "Not approved" }, { value: "true", label: "Approved" }]} /></Field>
        <Field label="Search"><Input value={filter.q} onChange={(e) => setFilter({ ...filter, q: e.target.value })} /></Field>
        {can("rfp.approve") && <Button disabled={!sel.length} onClick={() => approve(sel).then(() => setSel([]))}><CheckCheck size={16} /> Approve selected ({sel.length})</Button>}
        {can("rfp.edit") && <Button disabled={busy || !sel.length} onClick={() => run(() => api.post(`/rfp/workspaces/${wid}/agents/compliance/run`, { requirement_ids: sel }), "Re-running compliance for selected")}><RefreshCw size={16} /> Re-run selected</Button>}
      </div>
      {loading ? <Spinner /> : (
        <Table head={[<input key="all" type="checkbox" aria-label="Select all" onChange={(e) => setSel(e.target.checked ? (data || []).map((r) => r.id) : [])} />,
          "No.", "Requirement", "Ref", "Status", "Scope", "Proposed response", "Origin", ""]} empty="No requirements yet. Analyse the RFP first.">
          {(data || []).map((r) => (
            <tr key={r.id}>
              <td><input type="checkbox" checked={sel.includes(r.id)} onChange={(e) => setSel(e.target.checked ? [...sel, r.id] : sel.filter((x) => x !== r.id))} /></td>
              <td className="whitespace-nowrap font-semibold">{r.number}{r.change && <div><Badge tone="info">{r.change}</Badge></div>}</td>
              <td className="max-w-prose">{r.text}</td>
              <td className="whitespace-nowrap text-muted">{r.source_file}<div>{r.source_ref}</div></td>
              <td>{r.answer ? <StatusBadge status={r.answer.status} /> : <span className="text-muted">Pending</span>}{r.answer?.approved && <div><Badge tone="success">Approved</Badge></div>}</td>
              <td>{scopeBy[r.number] && <><Badge tone={OWNER_TONE[scopeBy[r.number].owner] || "neutral"}>{scopeBy[r.number].owner}</Badge>
                <div className="text-sm text-muted">{scopeBy[r.number].module}</div></>}</td>
              <td className="max-w-prose">{r.answer?.response}</td>
              <td>{r.answer?.origin}{r.answer?.origin_detail?.reused_from?.map((x: any, i: number) => <div key={i} className="text-sm text-muted">{x.customer} {x.date} v{x.product_version}</div>)}</td>
              <td><Button variant="ghost" onClick={() => setOpen(r)}>Open</Button></td>
            </tr>
          ))}
        </Table>
      )}
      {open && <AnswerModal r={open} onClose={() => setOpen(null)} onSaved={() => { setOpen(null); reload(); }} approve={approve} />}
    </div>
  );
}

function AnswerModal({ r, onClose, onSaved, approve }: any) {
  const { can } = useSession();
  const [a, setA] = useState({ status: r.answer?.status || "Needs Product Validation", response: r.answer?.response || "", explanation: r.answer?.explanation || "",
    evidence: r.answer?.evidence || "", validation_remarks: r.answer?.validation_remarks || "" });
  const [err, setErr] = useState("");
  async function save() {
    try { await api.put(`/rfp/requirements/${r.id}/answer`, a); onSaved(); } catch (e) { setErr((e as Error).message); }
  }
  return (
    <Modal open title={`${r.number} · ${r.source_file} ${r.source_ref}`} onClose={onClose} wide>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="flex flex-col gap-4">
          <Card title="Requirement"><p className="text-sm">{r.text}</p></Card>
          <Card title="Sources">
            <ul className="flex flex-col gap-2 text-sm">
              {(r.answer?.sources || []).map((s: any, i: number) => (
                <li key={i}>{s.kind === "submitted_rfp" ? <>Past RFP: <b>{s.customer}</b> {s.submitted_on} v{s.product_version}</>
                  : <><b>{s.title}</b> · {s.section} {s.section_path} {s.page} {s.url && <a className="underline" href={s.url} target="_blank" rel="noreferrer">link</a>}</>}</li>
              ))}
              {!(r.answer?.sources || []).length && <li className="text-muted">No sources.</li>}
            </ul>
          </Card>
        </div>
        <div className="flex flex-col gap-3">
          {err && <Alert tone="error">{err}</Alert>}
          <Field label="Status"><Select value={a.status} onChange={(e) => setA({ ...a, status: e.target.value })} options={STATUSES} /></Field>
          <Field label="Proposed response"><Textarea rows={4} value={a.response} onChange={(e) => setA({ ...a, response: e.target.value })} /></Field>
          <Field label="Explanation"><Textarea rows={3} value={a.explanation} onChange={(e) => setA({ ...a, explanation: e.target.value })} /></Field>
          <Field label="Evidence"><Textarea rows={2} value={a.evidence} onChange={(e) => setA({ ...a, evidence: e.target.value })} /></Field>
          <Field label="Validation remarks (internal)"><Textarea rows={2} value={a.validation_remarks} onChange={(e) => setA({ ...a, validation_remarks: e.target.value })} /></Field>
          <div className="flex gap-2">
            {can("rfp.edit") && <Button variant="primary" onClick={save}>Save</Button>}
            {can("rfp.approve") && r.answer && (r.answer.approved
              ? <Button onClick={() => approve([r.id], false).then(onSaved)}>Withdraw approval</Button>
              : <Button onClick={() => approve([r.id]).then(onSaved)}>Approve</Button>)}
          </div>
        </div>
      </div>
    </Modal>
  );
}

function Analysis({ wid, busy, run }: any) {
  const { can } = useSession();
  const { data, reload } = useApi<any>(`/rfp/workspaces/${wid}/agents`);
  const [edit, setEdit] = useState<any | null>(null);
  const [text, setText] = useState("");
  if (!data) return <Spinner />;
  return (
    <div className="flex flex-col gap-4">
      {Object.keys(AGENT_LABELS).map((k) => {
        const r = data[k];
        return (
          <Card key={k} title={<span>{AGENT_LABELS[k]} {r?.approved && <Badge tone="success">Approved</Badge>} {r?.edited && <Badge tone="info">Edited</Badge>}</span>}
            actions={<>
              {can("rfp.edit") && <Button disabled={busy} onClick={() => run(() => api.post(`/rfp/workspaces/${wid}/agents/${k}/run`), `${AGENT_LABELS[k]} queued`)}><Sparkles size={16} /> Run</Button>}
              {r && can("rfp.edit") && <Button onClick={() => { setEdit(r); setText(JSON.stringify(r.output, null, 2)); }}>Edit</Button>}
              {r && !r.approved && can("rfp.approve") && <Button onClick={() => api.post(`/rfp/agent-runs/${r.id}/approve`).then(reload)}>Approve</Button>}
            </>}>
            {!r ? <p className="text-sm text-muted">Not run yet.</p>
              : k === "scope" ? <Scope wid={wid} out={r.output} />
              : k === "architecture" ? <>
                  <Output value={Object.fromEntries(Object.entries(r.output).filter(([x]) => !["motadata_sizing", "motadata_inputs"].includes(x)))} />
                  {r.output.motadata_sizing && <HwSizing key={`${r.id}-${r.edited}`} wid={wid} hw={r.output.motadata_sizing} reload={reload} />}</>
              : k === "prebid" ? <Prebid key={`${r.id}-${r.edited}`} wid={wid} r={r} reload={reload} /> : <Output value={r.output} />}
          </Card>
        );
      })}
      <Modal open={!!edit} title={`Edit ${edit ? AGENT_LABELS[edit.label] || edit.label : ""}`} onClose={() => setEdit(null)} wide>
        <Textarea rows={24} value={text} onChange={(e) => setText(e.target.value)} />
        <div className="mt-2"><Button variant="primary" onClick={() => api.put(`/rfp/agent-runs/${edit.id}`, { output: JSON.parse(text) }).then(() => { setEdit(null); reload(); })}>Save</Button></div>
      </Modal>
    </div>
  );
}

/** Motadata hardware sizing computed from the RFP's figures; inputs can be corrected and the sizing recomputed. */
function HwSizing({ wid, hw, reload }: { wid: string; hw: any; reload: () => void }) {
  const { can } = useSession();
  const byName: Record<string, any> = Object.fromEntries((hw.inputs || []).map((i: any) => [i.name, i]));
  const [vals, setVals] = useState<Record<string, string>>(
    Object.fromEntries((hw.fields || []).map((f: any) => [f.name, byName[f.name] ? String(byName[f.name].value) : ""])));
  const [editing, setEditing] = useState(false);
  const [err, setErr] = useState("");
  async function recompute() {
    const inputs = (hw.fields || []).filter((f: any) => vals[f.name] !== "" && vals[f.name] !== undefined)
      .map((f: any) => ({ name: f.name, value: Number(vals[f.name]), ref: byName[f.name]?.ref || "", note: byName[f.name]?.note || (byName[f.name] ? "" : "Entered on review") }));
    if (inputs.some((i: any) => Number.isNaN(i.value))) { setErr("Enter numbers only."); return; }
    try { await api.post(`/rfp/workspaces/${wid}/sizing`, { inputs }); setErr(""); setEditing(false); reload(); }
    catch (e) { setErr((e as Error).message); }
  }
  return (
    <div className="mt-4 flex flex-col gap-3 border-t border-border pt-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold">Motadata hardware sizing</span>
        {hw.topology && <Badge tone="info">{hw.topology}</Badge>}
        <Badge tone="neutral">{({ standalone: "Standalone", ha: "HA", dc_dr: "DC + DR", ha_dr: "HA + DR" } as Record<string, string>)[hw.architecture] || hw.architecture}</Badge>
        {can("rfp.export") && hw.sites?.length > 0 && <Button onClick={() => download(`/rfp/workspaces/${wid}/export?kind=hw_sizing`)}><Download size={16} /> HW sizing (Excel)</Button>}
        {can("rfp.edit") && <Button variant="ghost" onClick={() => setEditing(!editing)}>{editing ? "Close inputs" : "Edit inputs"}</Button>}
      </div>
      {hw.error && <Alert tone={hw.status === "out_of_range" ? "error" : "warning"}>{hw.error}</Alert>}
      {err && <Alert tone="error">{err}</Alert>}
      {(hw.sites || []).map((s: any) => (
        <div key={s.title}><div className="mb-1 text-sm font-semibold">{s.title}</div>
          <Table head={["Component", "Qty", "vCPU", "RAM (GB)", "Disk (GB)"]}>
            {s.rows.map((row: any, i: number) => <tr key={i}><td>{row.n}</td><td>{row.q}</td><td>{row.c}</td><td>{row.r}</td><td>{row.k}</td></tr>)}
          </Table></div>
      ))}
      {hw.retention && <p className="text-sm text-muted">Retention: {hw.retention}</p>}
      {(hw.notes || []).length > 0 && <ul className="list-disc pl-5 text-sm">{hw.notes.map((n: string, i: number) => <li key={i}>{n}</li>)}</ul>}
      {!editing ? (
        <Table head={["Input from the RFP", "Value", "Reference", "Note"]} empty="No sizing inputs found in the RFP.">
          {(hw.inputs || []).map((i: any) => <tr key={i.name}><td>{i.label}</td><td className="font-semibold">{i.value}</td><td className="text-muted">{i.ref}</td><td className="text-sm text-muted">{i.note}</td></tr>)}
        </Table>
      ) : (
        <div className="flex flex-col gap-2">
          <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
            {(hw.fields || []).map((f: any) => (
              <Field key={f.name} label={`${f.label} · ${f.product}`} hint={byName[f.name]?.ref ? `RFP: ${byName[f.name].ref}` : undefined}>
                <Input inputMode="decimal" value={vals[f.name] ?? ""} onChange={(e) => setVals({ ...vals, [f.name]: e.target.value })} />
              </Field>
            ))}
          </div>
          <div><Button variant="primary" onClick={recompute}>Recompute sizing</Button></div>
        </div>
      )}
    </div>
  );
}

const OWNER_TONE: Record<string, "accent" | "info" | "warning" | "neutral"> = {
  Motadata: "accent", "Partner / SI": "info", Customer: "warning", Shared: "info", "Not applicable": "neutral",
};

/** Who delivers what: owner counts, Motadata modules, partner and customer items, gaps, and the per-requirement matrix. */
function Scope({ wid, out }: { wid: string; out: any }) {
  const { can } = useSession();
  const [owner, setOwner] = useState("");
  const matrix: any[] = (out.matrix || []).filter((m: any) => !owner || m.owner === owner);
  const lists: [string, string][] = [["partner_items", "Partner / SI supplies"], ["customer_prerequisites", "Customer provides"],
    ["out_of_scope", "Out of scope"], ["motadata_gaps", "Motadata gaps (non-compliant or to validate)"]];
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        {(out.owner_counts || []).map((o: any) => (
          <button key={o.owner} type="button" onClick={() => setOwner(owner === o.owner ? "" : o.owner)}
            className={owner === o.owner ? "outline outline-2 outline-black rounded-full" : ""}>
            <Badge tone={OWNER_TONE[o.owner] || "neutral"}>{o.owner}: {o.requirements}</Badge></button>
        ))}
        {can("rfp.export") && <Button onClick={() => download(`/rfp/workspaces/${wid}/export?kind=scope`)}><Download size={16} /> Scope matrix (Excel)</Button>}
      </div>
      <div>
        <div className="text-sm font-semibold">Motadata modules in scope</div>
        {(out.modules_in_scope || []).length ? (
          <ul className="mt-1 flex flex-col gap-1 text-sm">
            {out.modules_in_scope.map((m: any, i: number) => <li key={i}><Badge tone="accent">{m.product}</Badge> <b>{m.module}</b> <span className="text-muted">{m.basis}</span></li>)}
          </ul>) : <p className="text-sm text-muted">None identified.</p>}
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {lists.map(([k, label]) => (
          <div key={k}><div className="text-sm font-semibold">{label}</div>
            {(out[k] || []).length ? <ul className="list-disc pl-5 text-sm">{out[k].map((it: any, i: number) => (
              <li key={i}>{it.item} {it.ref && <span className="text-muted">({it.ref})</span>}{it.note && <span className="text-muted"> · {it.note}</span>}</li>))}</ul>
              : <p className="text-sm text-muted">None</p>}</div>
        ))}
      </div>
      <details>
        <summary className="cursor-pointer text-sm font-semibold">Requirement matrix ({matrix.length}{owner && ` · ${owner}`})</summary>
        <Table head={["No.", "Owner", "Product", "Module", "Note"]} empty="No requirements.">
          {matrix.map((m) => (
            <tr key={m.number}><td className="font-semibold">{m.number}</td><td><Badge tone={OWNER_TONE[m.owner] || "neutral"}>{m.owner}</Badge></td>
              <td>{m.product}</td><td>{m.module}</td><td className="text-sm text-muted">{m.note}</td></tr>
          ))}
        </Table>
      </details>
    </div>
  );
}

const TOP_N = 10;
const IMPACT_TONE: Record<string, "error" | "warning" | "neutral"> = { High: "error", Medium: "warning", Low: "neutral" };

/** Ranked pre-bid queries: tick the ones to submit, reorder, save, and download in the tender's own format. */
function Prebid({ wid, r, reload }: { wid: string; r: any; reload: () => void }) {
  const { can } = useSession();
  const initial = (r.output.queries || []).map((q: any, i: number) => ({ ...q, selected: "selected" in q ? q.selected : i < TOP_N }));
  const [queries, setQueries] = useState<any[]>(initial);
  const [dirty, setDirty] = useState(false);
  const [err, setErr] = useState("");
  const fmt = r.output.tender_format;
  const picked = queries.filter((q) => q.selected).length;
  const update = (next: any[]) => { setQueries(next); setDirty(true); };
  const move = (i: number, d: number) => {
    const j = i + d;
    if (j < 0 || j >= queries.length) return;
    const next = [...queries];
    [next[i], next[j]] = [next[j], next[i]];
    update(next.map((q, n) => ({ ...q, rank: n + 1 })));
  };
  async function save() {
    try {
      await api.put(`/rfp/agent-runs/${r.id}`, { output: { ...r.output, queries } });
      setDirty(false); setErr(""); reload();
    } catch (e) { setErr((e as Error).message); }
  }
  return (
    <div className="flex flex-col gap-3">
      {err && <Alert tone="error">{err}</Alert>}
      {fmt?.found
        ? <Alert tone="info">Format prescribed by the RFP{fmt.ref && ` (${fmt.ref})`}: {fmt.columns.map((c: any) => c.heading).join(" | ")}
            {fmt.instructions && <div className="mt-1">Submission: {fmt.instructions}</div>}</Alert>
        : <Alert tone="info">The RFP prescribes no pre-bid query format, so downloads use the standard format.</Alert>}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm">{picked} of {queries.length} selected to submit{picked !== TOP_N && ` (usually ${TOP_N})`}</span>
        {can("rfp.edit") && dirty && <Button variant="primary" onClick={save}>Save selection</Button>}
        {can("rfp.export") && <>
          <Button disabled={dirty} onClick={() => download(`/rfp/workspaces/${wid}/export?kind=prebid`)}><Download size={16} /> Excel</Button>
          <Button disabled={dirty} onClick={() => download(`/rfp/workspaces/${wid}/export?kind=prebid_docx`)}><Download size={16} /> Word</Button>
        </>}
        {dirty && <span className="text-sm text-muted">Save before downloading.</span>}
      </div>
      <Table head={["Submit", "Rank", "Impact", "Reference", "Query", "Why it matters", ""]} empty="No queries.">
        {queries.map((q, i) => (
          <tr key={i} className={q.selected ? "" : "opacity-60"}>
            <td><input type="checkbox" aria-label={`Submit query ${i + 1}`} checked={!!q.selected} disabled={!can("rfp.edit")}
              onChange={(e) => update(queries.map((x, n) => n === i ? { ...x, selected: e.target.checked } : x))} /></td>
            <td className="font-semibold">{q.rank ?? i + 1}</td>
            <td>{q.impact && <Badge tone={IMPACT_TONE[q.impact] || "neutral"}>{q.impact}</Badge>}<div className="text-sm text-muted">{q.category}</div></td>
            <td className="whitespace-nowrap text-muted">{q.ref}</td>
            <td className="max-w-prose">{q.query}
              {q.clause_text && <div className="mt-1 text-sm text-muted">Clause: {q.clause_text}</div>}
              {q.suggested_change && <div className="mt-1 text-sm">Suggested change: {q.suggested_change}</div>}</td>
            <td className="max-w-prose text-sm">{q.reason}</td>
            <td className="whitespace-nowrap">{can("rfp.edit") && <>
              <Button variant="ghost" aria-label="Move up" disabled={i === 0} onClick={() => move(i, -1)}><ArrowUp size={14} /></Button>
              <Button variant="ghost" aria-label="Move down" disabled={i === queries.length - 1} onClick={() => move(i, 1)}><ArrowDown size={14} /></Button>
            </>}</td>
          </tr>
        ))}
      </Table>
    </div>
  );
}

function Output({ value }: { value: any }) {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "string" || typeof value === "number") return <p className="whitespace-pre-wrap text-sm">{String(value)}</p>;
  if (Array.isArray(value)) {
    if (!value.length) return <p className="text-sm text-muted">None</p>;
    if (typeof value[0] === "object") {
      const keys = Object.keys(value[0]);
      return <Table head={keys.map((k) => k.replace(/_/g, " "))}>{value.map((row, i) => <tr key={i}>{keys.map((k) => <td key={k}>{typeof row[k] === "object" ? JSON.stringify(row[k]) : String(row[k] ?? "")}</td>)}</tr>)}</Table>;
    }
    return <ul className="list-disc pl-5 text-sm">{value.map((v, i) => <li key={i}>{String(v)}</li>)}</ul>;
  }
  return (
    <div className="flex flex-col gap-3">
      {Object.entries(value).filter(([k]) => !["source_ids", "citations"].includes(k)).map(([k, v]) => (
        <div key={k}><div className="text-sm font-semibold">{k.replace(/_/g, " ")}</div><Output value={v} /></div>
      ))}
    </div>
  );
}

function Proposal({ w, run, busy }: any) {
  const { can } = useSession();
  const templates = useApi<any[]>("/rfp/templates?module=rfp");
  const proposals = useApi<any[]>(`/rfp/workspaces/${w.id}/proposals`);
  const [tid, setTid] = useState<string>(w.template_id ? String(w.template_id) : "");
  const [content, setContent] = useState<Record<string, string> | null>(null);
  const latest = proposals.data?.[0];
  const tpls = (templates.data || []).filter((t) => t.kind === "template");
  return (
    <div className="flex flex-col gap-4">
      <Card title="Generate technical proposal">
        <div className="flex flex-wrap items-end gap-4">
          <Field label="Template"><Select value={tid} onChange={(e) => setTid(e.target.value)} options={[{ value: "", label: "Select" }, ...tpls.map((t) => ({ value: t.id, label: `${t.name} v${t.version}` }))]} /></Field>
          {can("rfp.edit") && <Button variant="primary" disabled={!tid || busy} onClick={() => run(() => api.post(`/rfp/workspaces/${w.id}/proposal`, { template_id: Number(tid) }), "Proposal generation queued")}><Sparkles size={16} /> Generate</Button>}
        </div>
        {!tpls.length && <p className="mt-2 text-sm text-muted">Upload a template with placeholders under RFP Intelligence &gt; Templates and samples.</p>}
      </Card>
      {latest && (
        <Card title={`Proposal v${latest.version}`} actions={<>
          {can("rfp.export") && <><Button onClick={() => download(`/rfp/proposals/${latest.id}/export?fmt=docx`)}><Download size={16} /> Word</Button>
            <Button onClick={() => download(`/rfp/proposals/${latest.id}/export?fmt=pdf`)}><Download size={16} /> PDF</Button></>}
          {can("rfp.edit") && content && <Button variant="primary" onClick={() => api.put(`/rfp/proposals/${latest.id}`, { content }).then(() => { setContent(null); proposals.reload(); })}>Save edits</Button>}
        </>}>
          <div className="flex flex-col gap-4">
            {Object.entries(content || latest.content).map(([k, v]) => (
              <Field key={k} label={k.replace(/_/g, " ")}>
                <Textarea rows={6} value={v as string} disabled={!can("rfp.edit")} onChange={(e) => setContent({ ...(content || latest.content), [k]: e.target.value })} />
              </Field>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}

function ExportTab({ w, run }: any) {
  const { can } = useSession();
  return (
    <div className="flex flex-col gap-4">
      {can("rfp.export") && (
        <Card title="Export">
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => download(`/rfp/workspaces/${w.id}/export?kind=compliance`)}><Download size={16} /> Customer compliance sheet</Button>
            <Button onClick={() => download(`/rfp/workspaces/${w.id}/export?kind=internal`)}><Download size={16} /> Internal workbook</Button>
            <Button onClick={() => download(`/rfp/workspaces/${w.id}/export?kind=report`)}><Download size={16} /> Analysis report (Word)</Button>
            <Button onClick={() => download(`/rfp/workspaces/${w.id}/export?kind=report_pdf`)}><Download size={16} /> Analysis report (PDF)</Button>
          </div>
        </Card>
      )}
      {can("rfp.approve") && (
        <Card title="Mark submitted">
          <p className="mb-4 text-sm text-muted">Upload the final submitted documents on the Documents tab first. Approved requirement and response pairs are added to the Submitted RFP repository.</p>
          <Button variant="primary" disabled={w.status === "Submitted"} onClick={() => run(() => api.post(`/rfp/workspaces/${w.id}/submit`), "Workspace marked Submitted.")}>
            {w.status === "Submitted" ? `Submitted ${fmtDate(w.submitted_at)}` : "Mark submitted"}</Button>
        </Card>
      )}
    </div>
  );
}
