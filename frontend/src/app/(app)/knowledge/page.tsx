"use client";
import { ChevronRight, Download, FileText, Globe, Link2, Loader2, Plus, RefreshCw, Search, Trash2, Upload } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { ReactNode, Suspense, useEffect, useMemo, useState } from "react";
import { Alert, Badge, Button, buttonClass, cx, Drawer, Field, Input, Modal, NumberInput, Select, SettingRow, Spinner, Table, Tabs, Textarea, Toggle } from "@/components/ui";
import { api, download, fmtDate } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useSession } from "@/lib/session";

type Panel = "" | "upload" | "url" | "section";
const PRODUCTS = ["Both", "ObserveOps", "ServiceOps"];
const PRIORITY_OPTS = [
  { value: 1, label: "Current product documentation (highest)" },
  { value: 2, label: "Internal presales knowledge" },
  { value: 3, label: "Past submissions (lowest)" },
];

/** One status per source, combining ingestion and approval, in the order a person cares about. */
function sourceState(s: any): { tone: "success" | "warning" | "error" | "info" | "neutral"; label: string; busy?: boolean } {
  if (["Queued", "Processing"].includes(s.ingest_status)) return { tone: "info", label: s.ingest_status === "Queued" ? "Queued" : "Processing", busy: true };
  if (s.ingest_status === "Failed") return { tone: "error", label: "Failed" };
  if (s.status === "Pending") return { tone: "warning", label: "Awaiting approval" };
  if (s.status === "Approved") return { tone: "success", label: "Approved" };
  if (s.status === "Rejected") return { tone: "neutral", label: "Rejected" };
  return { tone: "neutral", label: s.status };
}

function StateLabel({ s }: { s: any }) {
  const st = sourceState(s);
  if (st.busy) return <span className="inline-flex items-center gap-2 text-sm text-info"><Loader2 size={14} className="animate-spin" />{st.label}</span>;
  return <Badge tone={st.tone}>{st.label}</Badge>;
}

function KnowledgeHome() {
  const { can } = useSession();
  const router = useRouter();
  const params = useSearchParams();
  const view = params.get("tab") || "sources";
  const setView = (k: string) => router.replace(`/knowledge?tab=${k}`, { scroll: false });
  const pending = useApi<any[]>(can("knowledge.approve") ? "/knowledge/sources?status=Pending" : null, [view]);
  const waiting = (pending.data || []).filter((s) => s.ingest_status === "Ready").length;
  const [panel, setPanel] = useState<Panel>("");
  const [refresh, setRefresh] = useState(0);

  return (
    <>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-h4">Knowledge Hub</h1>
          <p className="text-sm text-muted">Approved Motadata material that Ask Motadata, RFP Intelligence and Demo Intelligence answer from.</p>
        </div>
        <div className="flex gap-2">
          {can("knowledge.register_url") && <Button onClick={() => setPanel("url")}><Link2 size={14} /> Add URL</Button>}
          {can("knowledge.upload") && <Button variant="primary" onClick={() => setPanel("upload")}><Upload size={14} /> Upload file</Button>}
        </div>
      </div>
      <Tabs active={view} onChange={setView} tabs={[
        { key: "sources", label: "Sources" },
        ...(can("knowledge.approve") ? [{ key: "approval", label: waiting ? `Approvals (${waiting})` : "Approvals" }] : []),
        { key: "sizing", label: "Sizing rules" },
        { key: "search", label: "Test search" },
      ]} />
      {view === "sources" && <Sources key={refresh} initialSource={params.get("source")} onNewSection={() => setPanel("section")} onAdd={setPanel} />}
      {view === "approval" && <Approvals onChanged={() => pending.reload()} />}
      {view === "sizing" && <Sizing />}
      {view === "search" && <TestSearch />}
      <AddPanels panel={panel} onClose={() => setPanel("")} onDone={() => { setPanel(""); setRefresh((r) => r + 1); pending.reload(); }} />
    </>
  );
}

function EmptyState({ icon, title, text, children }: { icon: ReactNode; title: string; text: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-3 px-6 py-16 text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-full bg-mono-100 text-mono-600">{icon}</span>
      <div className="text-sm font-semibold">{title}</div>
      <p className="max-w-sm text-sm text-muted">{text}</p>
      {children && <div className="mt-2 flex gap-2">{children}</div>}
    </div>
  );
}

function Sources({ initialSource, onNewSection, onAdd }: { initialSource?: string | null; onNewSection: () => void; onAdd: (p: Panel) => void }) {
  const { can } = useSession();
  const sections = useApi<any[]>("/knowledge/sections");
  const [section, setSection] = useState("");
  const [q, setQ] = useState("");
  const [state, setState] = useState("all");
  const [manage, setManage] = useState(false);
  const qs = new URLSearchParams({ ...(section ? { section_id: section } : {}), ...(q.trim() ? { q: q.trim() } : {}) }).toString();
  const sources = useApi<any[]>(`/knowledge/sources${qs ? `?${qs}` : ""}`, [qs]);
  const [open, setOpen] = useState<number | null>(initialSource ? Number(initialSource) : null);

  const busy = (sources.data || []).some((s) => ["Queued", "Processing"].includes(s.ingest_status));
  useEffect(() => {
    if (!busy) return;
    const t = setInterval(() => sources.reload(), 4000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [busy, qs]);

  const all = sources.data || [];
  const is = (s: any, k: string) => k === "all" || (k === "approved" && sourceState(s).label === "Approved")
    || (k === "awaiting" && sourceState(s).label === "Awaiting approval") || (k === "failed" && s.ingest_status === "Failed");
  const tiles = [
    { key: "all", label: "Total sources" }, { key: "approved", label: "Approved" },
    { key: "awaiting", label: "Awaiting approval" }, { key: "failed", label: "Failed" },
  ].map((t) => ({ ...t, n: all.filter((s) => is(s, t.key)).length }));
  const shown = all.filter((s) => is(s, state));
  const filtered = !!(q || section || state !== "all");

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        {tiles.map((t) => (
          <button key={t.key} onClick={() => setState(t.key)} aria-pressed={state === t.key}
            className={cx("rounded border px-4 py-3 text-left transition-colors", state === t.key ? "border-black" : "border-lightborder hover:border-mono-400")}>
            <div className="text-sm text-muted">{t.label}</div>
            <div className={cx("mt-1 text-h4 tabular-nums", t.key === "failed" && t.n > 0 && "text-error")}>{t.n}</div>
          </button>
        ))}
      </div>

      <div>
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <Select className="w-56" value={section} onChange={(e) => setSection(e.target.value)}
            options={[{ value: "", label: "All sections" }, ...(sections.data || []).map((s) => ({ value: String(s.id), label: s.name }))]} />
          <div className="relative w-full max-w-sm">
            <Search size={14} className="absolute left-2 top-2 text-muted" />
            <Input className="pl-8" placeholder="Search by title" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          {filtered && <Button variant="ghost" onClick={() => { setQ(""); setSection(""); setState("all"); }}>Clear</Button>}
          <div className="ml-auto">{can("knowledge.manage_sections") && <Button variant="ghost" onClick={() => setManage(true)}>Manage sections</Button>}</div>
        </div>

        <div className="rounded border border-lightborder">
          {sources.loading && !sources.data ? <div className="p-6"><Spinner /></div> : shown.length === 0 ? (
            filtered
              ? <EmptyState icon={<Search size={20} />} title="No sources match" text="Try another section, status or search term." />
              : <EmptyState icon={<FileText size={20} />} title="Add your first source" text="Upload product documents or add documentation URLs. They are processed automatically and become searchable once approved.">
                  {can("knowledge.register_url") && <Button onClick={() => onAdd("url")}><Link2 size={14} /> Add URL</Button>}
                  {can("knowledge.upload") && <Button variant="primary" onClick={() => onAdd("upload")}><Upload size={14} /> Upload file</Button>}
                </EmptyState>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-lightborder text-left text-mono-600">
                  <th className="px-4 py-2 font-semibold">Name</th>
                  <th className="px-4 py-2 font-semibold">Section</th>
                  <th className="px-4 py-2 font-semibold">Product</th>
                  <th className="px-4 py-2 font-semibold">Status</th>
                  <th className="px-4 py-2 font-semibold">Updated</th>
                  <th className="w-8 px-2 py-2"><span className="sr-only">Open</span></th>
                </tr>
              </thead>
              <tbody>
                {shown.map((s) => (
                  <tr key={s.id} onClick={() => setOpen(s.id)} className="cursor-pointer border-b border-lightborder last:border-b-0 hover:bg-offwhite">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded bg-mono-100 text-mono-600">{s.kind === "url" ? <Globe size={16} /> : <FileText size={16} />}</span>
                        <div className="min-w-0">
                          <div className="truncate font-semibold">{s.title}</div>
                          <div className="truncate text-muted">{s.kind === "url" ? "Web page" : s.document_type || "Document"}{s.duplicate_of && " · possible duplicate"}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-mono-700">{s.section}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-mono-700">{s.product}{s.product_version && ` ${s.product_version}`}</td>
                    <td className="whitespace-nowrap px-4 py-3"><StateLabel s={s} /></td>
                    <td className="whitespace-nowrap px-4 py-3 text-muted">{fmtDate(s.updated_at || s.created_at)}</td>
                    <td className="px-2 py-3 text-muted"><ChevronRight size={16} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
      <SourceDrawer id={open} onClose={() => setOpen(null)} onChanged={() => { sources.reload(); sections.reload(); }} />
      <SectionsDrawer open={manage} sections={sections.data || []} onClose={() => setManage(false)}
        onNew={() => { setManage(false); onNewSection(); }} onChanged={() => sections.reload()} />
    </div>
  );
}

const PRIORITY_NAMES: Record<number, string> = { 1: "Current documentation", 2: "Internal knowledge", 3: "Past submissions" };

function SectionsDrawer({ open, sections, onClose, onNew, onChanged }: { open: boolean; sections: any[]; onClose: () => void; onNew: () => void; onChanged: () => void }) {
  const [err, setErr] = useState("");
  const total = (s: any) => Object.values(s.counts as Record<string, number>).reduce((a, b) => a + b, 0);
  async function toggle(s: any, enabled: boolean) {
    try {
      await api.patch(`/knowledge/sections/${s.id}`, { name: s.name, description: s.description, used_by: s.used_by, priority: s.priority, enabled, sort: 100 });
      onChanged();
    } catch (e) { setErr((e as Error).message); }
  }
  return (
    <Drawer open={open} title="Sections" subtitle="Sections organise sources, set who can read them and decide which source wins when answers disagree."
      onClose={onClose} footer={<><Button variant="ghost" onClick={onClose}>Close</Button><Button variant="primary" onClick={onNew}><Plus size={14} /> New section</Button></>}>
      {err && <Alert tone="error">{err}</Alert>}
      <ul className="divide-y divide-lightborder">
        {sections.map((s) => (
          <li key={s.id} className="flex items-start justify-between gap-4 py-3">
            <div className="min-w-0">
              <div className={cx("text-sm font-semibold", !s.enabled && "text-muted")}>{s.name}</div>
              <div className="text-sm text-muted">{total(s)} {total(s) === 1 ? "source" : "sources"} · {PRIORITY_NAMES[s.priority] || `Priority ${s.priority}`}</div>
              {s.description && <div className="text-sm text-muted">{s.description}</div>}
            </div>
            <Toggle label={`${s.name} enabled`} checked={s.enabled} onChange={(v) => toggle(s, v)} />
          </li>
        ))}
      </ul>
    </Drawer>
  );
}

function Approvals({ onChanged }: { onChanged: () => void }) {
  const list = useApi<any[]>("/knowledge/sources?status=Pending");
  const [open, setOpen] = useState<number | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [msg, setMsg] = useState<{ tone: "error" | "success"; text: string } | null>(null);
  const ready = (list.data || []).filter((s) => s.ingest_status === "Ready");
  const processing = (list.data || []).filter((s) => s.ingest_status !== "Ready");
  async function act(s: any, action: "approve" | "reject") {
    setBusy(s.id);
    try { await api.post(`/knowledge/sources/${s.id}/${action}`, { note: "" }); setMsg({ tone: "success", text: `"${s.title}" ${action === "approve" ? "approved" : "rejected"}.` }); list.reload(); onChanged(); }
    catch (e) { setMsg({ tone: "error", text: (e as Error).message }); } finally { setBusy(null); }
  }
  if (!list.data) return <Spinner />;
  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted">Only approved sources are used in answers. Check each document is current and official before approving.</p>
      {msg && <Alert tone={msg.tone}>{msg.text}</Alert>}
      {ready.length === 0 ? (
        <div className="rounded border border-lightborder"><EmptyState icon={<FileText size={20} />} title="All caught up" text="Nothing is waiting for approval. New uploads appear here once they have been processed." /></div>
      ) : (
        <ul className="border-t border-lightborder">
          {ready.map((s) => (
            <li key={s.id} className="flex flex-wrap items-center gap-3 border-b border-lightborder px-2 py-3">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded bg-mono-100 text-mono-600">{s.kind === "url" ? <Globe size={16} /> : <FileText size={16} />}</span>
              <button className="min-w-0 flex-1 text-left" onClick={() => setOpen(s.id)}>
                <span className="block truncate text-sm font-semibold hover:underline">{s.title}</span>
                <span className="block truncate text-sm text-muted">{[s.section, s.product, s.product_version, `Added ${fmtDate(s.created_at)}`].filter(Boolean).join(" · ")}</span>
              </button>
              {s.duplicate_of && <span className="text-sm text-warning">Possible duplicate</span>}
              <div className="flex gap-2">
                <Button variant="ghost" disabled={busy === s.id} onClick={() => act(s, "reject")}>Reject</Button>
                <Button variant="primary" loading={busy === s.id} onClick={() => act(s, "approve")}>Approve</Button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {processing.length > 0 && <p className="text-sm text-muted">{processing.length} more {processing.length === 1 ? "source is" : "sources are"} still being processed and will appear here when ready.</p>}
      <SourceDrawer id={open} onClose={() => setOpen(null)} onChanged={() => { list.reload(); onChanged(); }} />
    </div>
  );
}

function AddPanels({ panel, onClose, onDone }: { panel: Panel; onClose: () => void; onDone: () => void }) {
  const sections = useApi<any[]>("/knowledge/sections");
  const secOpts = (sections.data || []).filter((s) => s.enabled).map((s) => ({ value: String(s.id), label: s.name }));
  const blank = { section_id: "", title: "", product: "Both", product_version: "", document_type: "", publication_date: "", label: "", url: "" };
  const [f, setF] = useState<any>(blank);
  const [file, setFile] = useState<File | null>(null);
  const [sec, setSec] = useState({ name: "", description: "", priority: 1 });
  const [err, setErr] = useState("");
  const [warn, setWarn] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => { if (panel) { setF({ ...blank, section_id: secOpts[0]?.value || "" }); setFile(null); setErr(""); setWarn(""); setSec({ name: "", description: "", priority: 1 }); } },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [panel]);
  const isCompetitor = (sections.data || []).find((s) => String(s.id) === f.section_id)?.key === "competitor_information";

  async function submit() {
    setSaving(true); setErr("");
    try {
      if (panel === "upload") {
        if (!file) throw new Error("Choose a file to upload");
        const fd = new FormData();
        Object.entries(f).forEach(([k, v]) => { if (k !== "url" && v) fd.set(k, String(v)); });
        fd.set("file", file);
        const r = await api.upload("/knowledge/sources/upload", fd);
        if (r.warning) { setWarn(r.warning); setSaving(false); return; }
      } else if (panel === "url") {
        await api.post("/knowledge/sources/url", { ...f, section_id: Number(f.section_id), document_type: f.document_type || "Online documentation" });
      } else {
        await api.post("/knowledge/sections", { ...sec, used_by: "", enabled: true, sort: 200 });
      }
      onDone();
    } catch (e) { setErr((e as Error).message); } finally { setSaving(false); }
  }
  const footer = warn
    ? <><span className="mr-auto text-sm text-warning">{warn}</span><Button variant="primary" onClick={onDone}>Done</Button></>
    : <><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" loading={saving} onClick={submit}>
      {panel === "upload" ? "Upload" : panel === "url" ? "Add URL" : "Create section"}</Button></>;
  const meta = (
    <>
      <Field label="Section"><Select value={f.section_id} onChange={(e) => setF({ ...f, section_id: e.target.value })} options={secOpts} /></Field>
      <div className="grid grid-cols-2 gap-4">
        <Field label="Product"><Select value={f.product} onChange={(e) => setF({ ...f, product: e.target.value })} options={PRODUCTS} /></Field>
        <Field label="Product version"><Input value={f.product_version} placeholder="e.g. 8.2" onChange={(e) => setF({ ...f, product_version: e.target.value })} /></Field>
      </div>
      {isCompetitor && <Field label="Label" hint="Answers show whether a comparison is verified or an internal observation.">
        <Select value={f.label} onChange={(e) => setF({ ...f, label: e.target.value })} options={[{ value: "", label: "Choose" }, { value: "verified", label: "Verified" }, { value: "internal observation", label: "Internal observation" }]} /></Field>}
    </>
  );
  return (
    <Drawer open={!!panel} onClose={onClose} footer={footer}
      title={panel === "upload" ? "Upload a file" : panel === "url" ? "Add a documentation URL" : "New section"}
      subtitle={panel === "section" ? "Sections organise sources and control who can see them." : "The source is processed in the background and becomes searchable after approval."}>
      <div className="flex flex-col gap-4">
        {err && <Alert tone="error">{err}</Alert>}
        {panel === "upload" && <>
          <label className={cx("flex cursor-pointer flex-col items-center gap-2 rounded border border-dashed px-6 py-8 text-center", file ? "border-black" : "border-border hover:border-mono-500")}
            onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); const x = e.dataTransfer.files?.[0]; if (x) setFile(x); }}>
            <Upload size={20} className="text-muted" />
            {file ? <span className="text-sm font-semibold">{file.name}</span> : <span className="text-sm"><b>Choose a file</b> or drag it here</span>}
            <span className="text-sm text-muted">PDF (scanned PDFs are read with OCR), Word, Excel, CSV, TXT or Markdown</span>
            <input type="file" className="hidden" onChange={(e) => setFile(e.target.files?.[0] || null)} />
          </label>
          <Field label="Title" hint="Leave empty to use the file name."><Input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
          {meta}
          <div className="grid grid-cols-2 gap-4">
            <Field label="Document type"><Input value={f.document_type} placeholder="e.g. Datasheet" onChange={(e) => setF({ ...f, document_type: e.target.value })} /></Field>
            <Field label="Publication date"><Input type="date" value={f.publication_date} onChange={(e) => setF({ ...f, publication_date: e.target.value })} /></Field>
          </div>
        </>}
        {panel === "url" && <>
          <Field label="URL" hint="Only domains allowed in Administration > Settings can be fetched."><Input value={f.url} placeholder="https://docs.motadata.com/…" onChange={(e) => setF({ ...f, url: e.target.value })} /></Field>
          <Field label="Title" hint="Leave empty to use the URL."><Input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
          {meta}
        </>}
        {panel === "section" && <>
          <Field label="Name"><Input value={sec.name} onChange={(e) => setSec({ ...sec, name: e.target.value })} /></Field>
          <Field label="Description"><Input value={sec.description} onChange={(e) => setSec({ ...sec, description: e.target.value })} /></Field>
          <Field label="Priority when sources disagree"><Select value={sec.priority} onChange={(e) => setSec({ ...sec, priority: Number(e.target.value) })} options={PRIORITY_OPTS} /></Field>
        </>}
      </div>
    </Drawer>
  );
}

function SourceDrawer({ id, onClose, onChanged }: { id: number | null; onClose: () => void; onChanged: () => void }) {
  const { can } = useSession();
  const s = useApi<any>(id ? `/knowledge/sources/${id}` : null, [id]);
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");
  useEffect(() => { setNote(""); setErr(""); }, [id]);
  const act = async (a: string) => {
    try { await api.post(`/knowledge/sources/${id}/${a}`, { note }); setNote(""); s.reload(); onChanged(); } catch (e) { setErr((e as Error).message); }
  };
  const d = id && s.data?.id === id ? s.data : null;
  const fact = (k: string, v: ReactNode) => <div><dt className="text-muted">{k}</dt><dd>{v || "—"}</dd></div>;
  return (
    <Drawer open={!!id} title={d?.title || "Source"} subtitle={d ? `${d.section} · ${d.kind === "url" ? "Web page" : "File"}` : ""} onClose={onClose}>
      {!d ? <Spinner /> : (
        <div className="flex flex-col gap-6">
          {err && <Alert tone="error">{err}</Alert>}
          <div className="flex items-center gap-3"><StateLabel s={d} />{d.duplicate_of && <span className="text-sm text-warning">Same file as source #{d.duplicate_of}</span>}</div>
          {d.ingest_error && <Alert tone="error">{d.ingest_error}</Alert>}

          <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
            {fact("Product", `${d.product}${d.product_version ? ` ${d.product_version}` : ""}`)}
            {fact("Document type", d.document_type)}
            {fact("Searchable passages", d.chunks)}
            {fact("Version", d.current_version || "—")}
            {fact("Added", fmtDate(d.created_at))}
            {fact("Approved", d.approved_at ? fmtDate(d.approved_at) : "")}
            {d.label && fact("Label", d.label)}
          </dl>

          {d.kind === "url" && (
            <div className="text-sm">
              <a className="break-all underline" href={d.url} target="_blank" rel="noreferrer">{d.url}</a>
              <p className="mt-1 text-muted">Last fetched {fmtDate(d.last_fetch_ok_at, true) || "never"}{d.last_fetch_attempt_at && d.last_fetch_attempt_at !== d.last_fetch_ok_at ? ` · last attempt ${fmtDate(d.last_fetch_attempt_at, true)}` : ""}</p>
            </div>
          )}

          <div className="flex flex-wrap gap-2">
            {d.kind === "file" && <Button onClick={() => download(`/knowledge/sources/${id}/download`)}><Download size={14} /> Download</Button>}
            {d.kind === "url" && can("knowledge.register_url") && <Button onClick={() => act("resync")}><RefreshCw size={14} /> Fetch again</Button>}
            {d.kind === "file" && can("knowledge.upload") && (
              <label className={buttonClass("secondary")}>
                <Upload size={14} /> Upload new version
                <input type="file" className="hidden" onChange={async (e) => {
                  const x = e.target.files?.[0]; if (!x) return;
                  const fd = new FormData(); fd.set("file", x);
                  try { await api.upload(`/knowledge/sources/${id}/versions`, fd); s.reload(); onChanged(); } catch (y) { setErr((y as Error).message); }
                }} />
              </label>
            )}
          </div>

          {can("knowledge.approve") && d.ingest_status === "Ready" && (
            <section className="flex flex-col gap-2 border-t border-lightborder pt-4">
              <h3 className="text-sm font-semibold">Approval</h3>
              <Textarea rows={2} placeholder="Note for the record (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
              <div className="flex gap-2">
                {d.status === "Pending" && <><Button variant="primary" onClick={() => act("approve")}>Approve</Button><Button variant="ghost" onClick={() => act("reject")}>Reject</Button></>}
                {d.status === "Approved" && <Button variant="danger" onClick={() => act("disable")}>Disable</Button>}
                {["Disabled", "Rejected"].includes(d.status) && <Button onClick={() => act("approve")}>Approve again</Button>}
              </div>
            </section>
          )}

          {d.versions.length > 0 && (
            <section className="border-t border-lightborder pt-4">
              <h3 className="mb-2 text-sm font-semibold">Versions</h3>
              <ul className="divide-y divide-lightborder text-sm">
                {d.versions.map((v: any) => (
                  <li key={v.version} className="flex justify-between gap-3 py-2">
                    <span>Version {v.version}{v.version === d.current_version && <span className="text-muted"> · current</span>}</span>
                    <span className="text-muted">{[v.page_count ? `${v.page_count} pages` : "", v.used_ocr ? "OCR" : "", fmtDate(v.created_at)].filter(Boolean).join(" · ")}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {d.history.length > 0 && (
            <section className="border-t border-lightborder pt-4">
              <h3 className="mb-2 text-sm font-semibold">History</h3>
              <ul className="flex flex-col gap-1 text-sm text-muted">
                {d.history.map((h: any, i: number) => <li key={i}>{fmtDate(h.at, true)} · {cap(h.action)}{h.note && `: ${h.note}`}</li>)}
              </ul>
            </section>
          )}
        </div>
      )}
    </Drawer>
  );
}

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

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
        <div>
          <h2 className="text-sm font-semibold">{(data || []).length} sizing {(data || []).length === 1 ? "rule" : "rules"}</h2>
          <p className="text-sm text-muted">Hardware sizing answers come only from these rules, taken from the product team&apos;s sizing guide.</p>
        </div>
        {manage && <Button variant="primary" onClick={() => { setErr(""); setEdit(blank); }}><Plus size={14} /> Add rule</Button>}
      </div>
      {data && data.length === 0 ? (
        <div className="rounded border border-lightborder">
          <EmptyState icon={<Plus size={20} />} title="No sizing rules yet" text="Until rules are added, sizing questions are referred to the product team. Add one rule per component and size band from the sizing guide.">
            {manage && <Button variant="primary" onClick={() => { setErr(""); setEdit(blank); }}><Plus size={14} /> Add rule</Button>}
          </EmptyState>
        </div>
      ) : (
      <Table head={["Product", "Component", "Applies when", "Recommended hardware", "Source", ""]}>
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
      )}
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
  const [busy, setBusy] = useState(false);
  async function run(e: React.FormEvent) {
    e.preventDefault();
    if (!q.trim()) return;
    setBusy(true);
    try { setHits(await api.get(`/knowledge/search?q=${encodeURIComponent(q)}`)); } finally { setBusy(false); }
  }
  return (
    <div className="flex max-w-prose flex-col gap-4">
      <p className="text-sm text-muted">Type a question to see which approved passages the AI would read to answer it. Only sections you can see are searched.</p>
      <form className="flex gap-2" onSubmit={run}>
        <div className="relative flex-1">
          <Search size={14} className="absolute left-2 top-2 text-muted" />
          <Input className="pl-8" value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. Does ObserveOps support high availability?" />
        </div>
        <Button type="submit" variant="primary" loading={busy}>Search</Button>
      </form>
      {hits && (hits.length === 0 ? <p className="text-sm text-muted">No approved sources matched.</p> : (
        <ol className="border-t border-lightborder">
          {hits.map((h, i) => (
            <li key={h.id} className="border-b border-lightborder py-3">
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-sm font-semibold">{i + 1}. {h.title}</span>
                <span className="shrink-0 text-sm tabular-nums text-muted">{Math.round(h.score * 100)}% match</span>
              </div>
              <div className="text-sm text-muted">{[h.section, h.section_path, h.page].filter(Boolean).join(" › ")}</div>
              <p className="mt-1 line-clamp-4 whitespace-pre-wrap text-sm">{h.text}</p>
            </li>
          ))}
        </ol>
      ))}
    </div>
  );
}

export default function KnowledgePage() {
  return <Suspense><KnowledgeHome /></Suspense>;
}
