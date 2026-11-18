"use client";
import { Download, Link2, Plus, RefreshCw, Trash2, Upload } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Alert, Badge, Button, Card, Field, Input, Modal, NumberInput, PageHeader, Select, SettingRow, Spinner, StatusBadge, Table, Tabs, Textarea, Toggle } from "@/components/ui";
import { api, download, fmtDate } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useSession } from "@/lib/session";

function KnowledgeHome() {
  const { can } = useSession();
  const params = useSearchParams();
  const [tab, setTab] = useState(params.get("tab") || "sources");
  const tabs = [{ key: "sources", label: "Sections and sources" },
    ...(can("knowledge.approve") ? [{ key: "approval", label: "Approval queue" }] : []),
    { key: "sizing", label: "Sizing rules" }, { key: "search", label: "Test retrieval" }];
  return (
    <>
      <PageHeader title="Knowledge Hub" subtitle="The one repository of approved Motadata material that every AI feature uses." />
      <Tabs tabs={tabs} active={tab} onChange={setTab} />
      {tab === "sources" && <Sources initialSource={params.get("source")} />}
      {tab === "approval" && <Sources approvalOnly />}
      {tab === "sizing" && <Sizing />}
      {tab === "search" && <TestSearch />}
    </>
  );
}

function Sources({ approvalOnly, initialSource }: { approvalOnly?: boolean; initialSource?: string | null }) {
  const { can } = useSession();
  const sections = useApi<any[]>("/knowledge/sections");
  const [section, setSection] = useState<number | null>(null);
  const qs = approvalOnly ? "?status=Pending" : section ? `?section_id=${section}` : "";
  const sources = useApi<any[]>(`/knowledge/sources${qs}`, [qs]);
  const [modal, setModal] = useState<"" | "upload" | "url" | "section">("");
  const [open, setOpen] = useState<number | null>(initialSource ? Number(initialSource) : null);
  const [msg, setMsg] = useState<{ tone: "error" | "success" | "warning"; text: string } | null>(null);

  useEffect(() => {
    const t = setInterval(() => { if ((sources.data || []).some((s) => ["Queued", "Processing"].includes(s.ingest_status))) sources.reload(); }, 5000);
    return () => clearInterval(t);
  }, [sources]);

  async function submit(path: string, form: FormData | object) {
    try {
      const r = form instanceof FormData ? await api.upload(path, form) : await api.post(path, form);
      setMsg(r.warning ? { tone: "warning", text: r.warning } : { tone: "success", text: "Saved. Ingestion runs in the background; approve the source when it is Ready." });
      setModal("");
      sources.reload(); sections.reload();
    } catch (e) { setMsg({ tone: "error", text: (e as Error).message }); }
  }
  const secOpts = (sections.data || []).map((s) => ({ value: s.id, label: s.name }));

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[256px_1fr]">
      {!approvalOnly && (
        <div className="flex flex-col gap-1">
          <button onClick={() => setSection(null)} className={`rounded px-3 py-2 text-left text-sm ${!section ? "bg-offwhite font-semibold" : "hover:bg-offwhite"}`}>All sections</button>
          {(sections.data || []).map((s) => (
            <button key={s.id} onClick={() => setSection(s.id)} className={`flex justify-between rounded px-3 py-2 text-left text-sm ${section === s.id ? "bg-offwhite font-semibold" : "hover:bg-offwhite"}`}>
              <span>{s.name}{!s.enabled && " (disabled)"}</span><span className="text-muted">{Object.values(s.counts as Record<string, number>).reduce((a, b) => a + b, 0)}</span>
            </button>
          ))}
          {can("knowledge.manage_sections") && <Button variant="ghost" onClick={() => setModal("section")}><Plus size={16} /> Section</Button>}
        </div>
      )}
      <div className={approvalOnly ? "lg:col-span-2" : ""}>
        {msg && <div className="mb-4"><Alert tone={msg.tone}>{msg.text}</Alert></div>}
        {!approvalOnly && (
          <div className="mb-4 flex gap-2">
            {can("knowledge.upload") && <Button variant="primary" onClick={() => setModal("upload")}><Upload size={16} /> Upload file</Button>}
            {can("knowledge.register_url") && <Button onClick={() => setModal("url")}><Link2 size={16} /> Register URL</Button>}
          </div>
        )}
        {sources.loading && !sources.data ? <Spinner /> : (
          <Table head={["Source", "Section", "Product", "Ingestion", "Status", "Updated", ""]} empty={approvalOnly ? "Nothing waiting for approval." : "No sources yet."}>
            {(sources.data || []).map((s) => (
              <tr key={s.id}>
                <td className="font-semibold">{s.title}<div className="text-sm font-normal text-muted">{s.kind === "url" ? s.url : s.document_type}{s.label && ` · ${s.label}`}</div>
                  {s.duplicate_of && <Badge tone="warning">Duplicate of #{s.duplicate_of}</Badge>}</td>
                <td>{s.section}</td><td>{s.product}{s.product_version && ` ${s.product_version}`}</td>
                <td><StatusBadge status={s.ingest_status} />{s.ingest_error && <div className="text-sm text-error">{s.ingest_error}</div>}</td>
                <td><StatusBadge status={s.status} /></td><td>{fmtDate(s.updated_at || s.created_at)}</td>
                <td><Button variant="ghost" onClick={() => setOpen(s.id)}>Open</Button></td>
              </tr>
            ))}
          </Table>
        )}
      </div>
      <Modal open={modal === "upload"} title="Upload file" onClose={() => setModal("")}>
        <form className="flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); submit("/knowledge/sources/upload", new FormData(e.currentTarget)); }}>
          <Field label="Section"><Select name="section_id" defaultValue={section || undefined} options={secOpts} /></Field>
          <Field label="Title"><Input name="title" placeholder="Defaults to the file name" /></Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Product"><Select name="product" options={["Both", "ObserveOps", "ServiceOps"]} /></Field>
            <Field label="Product version"><Input name="product_version" /></Field>
            <Field label="Document type"><Input name="document_type" /></Field>
            <Field label="Publication date"><Input name="publication_date" type="date" /></Field>
          </div>
          <Field label="Label" hint="For competitor information: verified or internal observation."><Select name="label" options={["", "verified", "internal observation"]} /></Field>
          <Field label="File" hint="PDF (scanned PDFs use OCR), DOCX, DOC, XLSX, XLS, CSV, TXT or MD."><input type="file" name="file" required /></Field>
          <div><Button variant="primary" type="submit">Upload</Button></div>
        </form>
      </Modal>
      <UrlModal open={modal === "url"} onClose={() => setModal("")} sections={secOpts} defaultSection={section} onSubmit={(b: object) => submit("/knowledge/sources/url", b)} />
      <SectionModal open={modal === "section"} onClose={() => setModal("")} onSubmit={(b: object) => submit("/knowledge/sections", b)} />
      {open && <SourceModal id={open} onClose={() => setOpen(null)} onChanged={() => sources.reload()} />}
    </div>
  );
}

function UrlModal({ open, onClose, sections, defaultSection, onSubmit }: any) {
  const [b, setB] = useState<any>({ section_id: defaultSection || sections[0]?.value, url: "", title: "", product: "Both", product_version: "" });
  useEffect(() => { setB((x: any) => ({ ...x, section_id: defaultSection || sections[0]?.value })); }, [defaultSection, sections]);
  return (
    <Modal open={open} title="Register URL" onClose={onClose}>
      <div className="flex flex-col gap-4">
        <Field label="Section"><Select value={b.section_id} onChange={(e) => setB({ ...b, section_id: Number(e.target.value) })} options={sections} /></Field>
        <Field label="URL" hint="Only registered domains can be fetched (Administration > Settings)."><Input value={b.url} onChange={(e) => setB({ ...b, url: e.target.value })} /></Field>
        <Field label="Title"><Input value={b.title} onChange={(e) => setB({ ...b, title: e.target.value })} /></Field>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Product"><Select value={b.product} onChange={(e) => setB({ ...b, product: e.target.value })} options={["Both", "ObserveOps", "ServiceOps"]} /></Field>
          <Field label="Product version"><Input value={b.product_version} onChange={(e) => setB({ ...b, product_version: e.target.value })} /></Field>
        </div>
        <div><Button variant="primary" disabled={!b.url} onClick={() => onSubmit({ ...b, section_id: Number(b.section_id) })}>Register</Button></div>
      </div>
    </Modal>
  );
}

function SectionModal({ open, onClose, onSubmit }: any) {
  const [b, setB] = useState({ name: "", description: "", used_by: "", priority: 1, enabled: true, sort: 200 });
  return (
    <Modal open={open} title="New section" onClose={onClose}>
      <div className="flex flex-col gap-4">
        <Field label="Name"><Input value={b.name} onChange={(e) => setB({ ...b, name: e.target.value })} /></Field>
        <Field label="Description"><Input value={b.description} onChange={(e) => setB({ ...b, description: e.target.value })} /></Field>
        <Field label="Source priority" hint="1 current documentation, 2 internal knowledge, 3 past submissions">
          <Select value={b.priority} onChange={(e) => setB({ ...b, priority: Number(e.target.value) })} options={[{ value: 1, label: "1" }, { value: 2, label: "2" }, { value: 3, label: "3" }]} /></Field>
        <div><Button variant="primary" disabled={!b.name} onClick={() => onSubmit(b)}>Create</Button></div>
      </div>
    </Modal>
  );
}

function SourceModal({ id, onClose, onChanged }: { id: number; onClose: () => void; onChanged: () => void }) {
  const { can } = useSession();
  const s = useApi<any>(`/knowledge/sources/${id}`);
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");
  const act = async (a: string) => {
    try { await api.post(`/knowledge/sources/${id}/${a}`, { note }); s.reload(); onChanged(); } catch (e) { setErr((e as Error).message); }
  };
  if (!s.data) return null;
  const d = s.data;
  return (
    <Modal open title={d.title} onClose={onClose} wide>
      <div className="flex flex-col gap-4">
        {err && <Alert tone="error">{err}</Alert>}
        <div className="flex flex-wrap items-center gap-2 text-sm"><StatusBadge status={d.status} /><StatusBadge status={d.ingest_status} />
          <span>{d.section}</span><span>{d.product} {d.product_version}</span><span>{d.chunks} chunks</span><span>Version {d.current_version}</span></div>
        {d.kind === "url" && <p className="text-sm"><a className="underline" href={d.url} target="_blank" rel="noreferrer">{d.url}</a> · Last successful fetch {fmtDate(d.last_fetch_ok_at, true) || "never"} · Last attempt {fmtDate(d.last_fetch_attempt_at, true) || "never"}</p>}
        {d.ingest_error && <Alert tone="error">{d.ingest_error}</Alert>}
        <div className="flex flex-wrap gap-2">
          {d.kind === "file" && <Button onClick={() => download(`/knowledge/sources/${id}/download`)}><Download size={16} /> Original</Button>}
          {d.kind === "url" && can("knowledge.register_url") && <Button onClick={() => act("resync")}><RefreshCw size={16} /> Re-sync</Button>}
          {d.kind === "file" && can("knowledge.upload") && (
            <label className="inline-flex cursor-pointer items-center gap-2 rounded border border-border px-4 py-2 text-sm font-semibold hover:bg-offwhite">
              <Upload size={16} /> New version
              <input type="file" className="hidden" onChange={async (e) => {
                const f = e.target.files?.[0]; if (!f) return;
                const fd = new FormData(); fd.set("file", f);
                try { await api.upload(`/knowledge/sources/${id}/versions`, fd); s.reload(); onChanged(); } catch (x) { setErr((x as Error).message); }
              }} />
            </label>
          )}
        </div>
        {can("knowledge.approve") && (
          <Card title="Approval">
            <Textarea rows={2} placeholder="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
            <div className="mt-2 flex gap-2">
              {d.status !== "Approved" && <Button variant="primary" onClick={() => act("approve")}>Approve</Button>}
              {d.status === "Pending" && <Button onClick={() => act("reject")}>Reject</Button>}
              {d.status === "Approved" && <Button onClick={() => act("disable")}>Disable</Button>}
              {d.status === "Disabled" && <Button onClick={() => act("enable")}>Enable</Button>}
            </div>
          </Card>
        )}
        <Table head={["Version", "Pages", "OCR", "Embedding model", "Uploaded"]}>
          {d.versions.map((v: any) => <tr key={v.version}><td>{v.version}</td><td>{v.page_count || ""}</td><td>{v.used_ocr ? "Yes" : ""}</td><td>{v.embedding_model}</td><td>{fmtDate(v.created_at, true)}</td></tr>)}
        </Table>
        {d.history.length > 0 && <ul className="text-sm">{d.history.map((h: any, i: number) => <li key={i}>{fmtDate(h.at, true)} · {h.action}{h.note && `: ${h.note}`}</li>)}</ul>}
      </div>
    </Modal>
  );
}

type Range = { name: string; min: string; max: string };
type Spec = { name: string; value: string };

function toForm(r: any) {
  return {
    id: r.id, product: r.product, component: r.component, source: r.source, sort: r.sort ?? 100, active: r.active ?? true,
    conditions: Object.entries(r.conditions || {}).map(([name, b]: any) => ({ name, min: b?.[0] ?? "", max: b?.[1] ?? "" })) as Range[],
    result: Object.entries(r.result || {}).map(([name, value]) => ({ name, value: String(value) })) as Spec[],
  };
}

function Sizing() {
  const { can } = useSession();
  const { data, reload } = useApi<any[]>("/ask/sizing-rules");
  const [edit, setEdit] = useState<ReturnType<typeof toForm> | null>(null);
  const [err, setErr] = useState("");
  const manage = can("knowledge.manage_sections");
  const blank = toForm({ product: "ObserveOps", component: "", conditions: { monitored_devices: [0, null] }, result: { cpu: "", ram: "", disk: "" }, source: "" });

  async function save() {
    if (!edit) return;
    setErr("");
    const conditions: Record<string, (number | null)[]> = {};
    for (const c of edit.conditions) {
      if (!c.name.trim()) continue;
      conditions[c.name.trim()] = [c.min === "" ? null : Number(c.min), c.max === "" ? null : Number(c.max)];
    }
    const result: Record<string, string> = {};
    for (const r of edit.result) if (r.name.trim()) result[r.name.trim()] = r.value;
    if (!edit.component.trim()) return setErr("Enter the component, for example Application server");
    if (!Object.keys(conditions).length) return setErr("Add at least one input range");
    if (!Object.keys(result).length) return setErr("Add at least one hardware value");
    const body = { product: edit.product, component: edit.component, conditions, result, source: edit.source, sort: Number(edit.sort) || 100, active: edit.active };
    try {
      if (edit.id) await api.put(`/ask/sizing-rules/${edit.id}`, body); else await api.post("/ask/sizing-rules", body);
      setEdit(null); reload();
    } catch (e) { setErr((e as Error).message); }
  }
  const set = (patch: Partial<ReturnType<typeof toForm>>) => edit && setEdit({ ...edit, ...patch });
  const fmtRange = (b: any[]) => `${b[0] ?? 0} to ${b[1] ?? "no limit"}`;

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
        <p className="max-w-prose text-sm text-muted">The product team&apos;s sizing guide as a rule table. Ask Motadata and RFP Intelligence answer sizing questions only from these rules; a rule applies when every input falls inside its range (lower bound included, upper bound excluded).</p>
        {manage && <Button variant="primary" onClick={() => { setErr(""); setEdit(blank); }}><Plus size={16} /> Sizing rule</Button>}
      </div>
      <Table head={["Product", "Component", "Applies when", "Recommended hardware", "Source", ""]} empty="No sizing rules yet. Sizing questions are referred to the product team.">
        {(data || []).map((r) => (
          <tr key={r.id}>
            <td>{r.product}{!r.active && <div><Badge>Inactive</Badge></div>}</td>
            <td className="font-semibold">{r.component}</td>
            <td>{Object.entries(r.conditions).map(([k, v]: any) => <div key={k} className="text-sm"><span className="text-muted">{k.replace(/_/g, " ")}:</span> {fmtRange(v)}</div>)}</td>
            <td>{Object.entries(r.result).map(([k, v]) => <div key={k} className="text-sm"><span className="text-muted">{k.toUpperCase()}:</span> {String(v)}</div>)}</td>
            <td className="text-sm text-muted">{r.source}</td>
            <td className="text-right">{manage && <Button variant="ghost" onClick={() => { setErr(""); setEdit(toForm(r)); }}>Edit</Button>}</td>
          </tr>
        ))}
      </Table>
      <Modal open={!!edit} title={edit?.id ? "Edit sizing rule" : "New sizing rule"} onClose={() => setEdit(null)} wide>
        {edit && <div className="flex flex-col gap-6">
          {err && <Alert tone="error">{err}</Alert>}
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <Field label="Product"><Select value={edit.product} onChange={(e) => set({ product: e.target.value })} options={["ObserveOps", "ServiceOps", "Both"]} /></Field>
            <Field label="Component"><Input value={edit.component} placeholder="e.g. Application server" onChange={(e) => set({ component: e.target.value })} /></Field>
            <Field label="Source"><Input value={edit.source} placeholder="e.g. Sizing guide v3, table 2" onChange={(e) => set({ source: e.target.value })} /></Field>
          </div>
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <section className="rounded border border-border">
              <header className="border-b border-lightborder bg-offwhite px-4 py-2"><div className="text-sm font-semibold">Applies when</div>
                <div className="text-sm text-muted">Input names must match what users ask about, e.g. monitored_devices, eps, endpoints.</div></header>
              <div className="flex flex-col gap-2 p-4">
                {edit.conditions.map((c, i) => (
                  <div key={i} className="grid grid-cols-[1fr_96px_96px_32px] items-center gap-2">
                    <Input value={c.name} placeholder="input name" onChange={(e) => set({ conditions: edit.conditions.map((x, j) => j === i ? { ...x, name: e.target.value } : x) })} />
                    <Input type="number" value={c.min} placeholder="from" onChange={(e) => set({ conditions: edit.conditions.map((x, j) => j === i ? { ...x, min: e.target.value } : x) })} />
                    <Input type="number" value={c.max} placeholder="below" onChange={(e) => set({ conditions: edit.conditions.map((x, j) => j === i ? { ...x, max: e.target.value } : x) })} />
                    <button aria-label="Remove range" className="rounded p-1 hover:bg-offwhite" onClick={() => set({ conditions: edit.conditions.filter((_, j) => j !== i) })}><Trash2 size={16} /></button>
                  </div>
                ))}
                <div><Button variant="ghost" onClick={() => set({ conditions: [...edit.conditions, { name: "", min: "", max: "" }] })}><Plus size={16} /> Add input range</Button></div>
              </div>
            </section>
            <section className="rounded border border-border">
              <header className="border-b border-lightborder bg-offwhite px-4 py-2"><div className="text-sm font-semibold">Recommended hardware</div>
                <div className="text-sm text-muted">For example CPU 16 vCPU, RAM 64 GB, Disk 2 TB SSD, Nodes 2.</div></header>
              <div className="flex flex-col gap-2 p-4">
                {edit.result.map((r, i) => (
                  <div key={i} className="grid grid-cols-[128px_1fr_32px] items-center gap-2">
                    <Input value={r.name} placeholder="cpu" onChange={(e) => set({ result: edit.result.map((x, j) => j === i ? { ...x, name: e.target.value } : x) })} />
                    <Input value={r.value} placeholder="16 vCPU" onChange={(e) => set({ result: edit.result.map((x, j) => j === i ? { ...x, value: e.target.value } : x) })} />
                    <button aria-label="Remove value" className="rounded p-1 hover:bg-offwhite" onClick={() => set({ result: edit.result.filter((_, j) => j !== i) })}><Trash2 size={16} /></button>
                  </div>
                ))}
                <div><Button variant="ghost" onClick={() => set({ result: [...edit.result, { name: "", value: "" }] })}><Plus size={16} /> Add value</Button></div>
              </div>
            </section>
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <SettingRow title="Active" help="Inactive rules are ignored when answering."><Toggle label="Active" checked={edit.active} onChange={(v) => set({ active: v })} /></SettingRow>
            <SettingRow title="Order" help="Lower numbers are checked first when ranges overlap."><NumberInput value={edit.sort} min={0} onChange={(v) => set({ sort: v })} /></SettingRow>
          </div>
          <div className="flex justify-between gap-2 border-t border-lightborder pt-4">
            <div>{edit.id && <Button variant="danger" onClick={() => confirm("Delete this sizing rule?") && api.del(`/ask/sizing-rules/${edit.id}`).then(() => { setEdit(null); reload(); })}>Delete rule</Button>}</div>
            <div className="flex gap-2"><Button variant="ghost" onClick={() => setEdit(null)}>Cancel</Button><Button variant="primary" onClick={save}>{edit.id ? "Save rule" : "Create rule"}</Button></div>
          </div>
        </div>}
      </Modal>
    </>
  );
}

function TestSearch() {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<any[] | null>(null);
  return (
    <div className="flex flex-col gap-4">
      <form className="flex max-w-prose gap-2" onSubmit={async (e) => { e.preventDefault(); setHits(await api.get(`/knowledge/search?q=${encodeURIComponent(q)}`)); }}>
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="See which approved chunks a question retrieves" />
        <Button type="submit">Search</Button>
      </form>
      {hits && (hits.length ? hits.map((h) => (
        <Card key={h.id} title={<span>{h.title} <span className="text-sm font-normal text-muted">{h.section} › {h.section_path} {h.page} · score {h.score}</span></span>}>
          <p className="whitespace-pre-wrap text-sm">{h.text}</p>
        </Card>)) : <p className="text-sm text-muted">No approved sources matched.</p>)}
    </div>
  );
}

export default function KnowledgePage() {
  return <Suspense><KnowledgeHome /></Suspense>;
}