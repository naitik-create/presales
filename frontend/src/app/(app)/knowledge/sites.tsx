"use client";
/** Documentation sites (whole-site crawl or ZIP import) and past pre-bid query sheets. */
import { Download, FileSpreadsheet, Globe, Loader2, RefreshCw, Search, Upload } from "lucide-react";
import { ReactNode, useEffect, useState } from "react";
import { Alert, Badge, Button, buttonClass, Drawer, Field, Input, Select, Spinner, Table, Textarea, Toggle } from "@/components/ui";
import { api, download, fmtDate } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useSession } from "@/lib/session";

const PRODUCTS = ["Both", "ObserveOps", "ServiceOps"];
const LABELS = [{ value: "", label: "Current product" }, { value: "Older product", label: "Older product (answers say so)" }];
const SUGGESTED = [
  { url: "https://docs.motadata.com/observeops-docs/", title: "ObserveOps documentation", product: "ObserveOps", label: "" },
  { url: "https://docs.motadata.com/serviceops-docs/", title: "ServiceOps documentation", product: "ServiceOps", label: "" },
  { url: "https://docs.motadata.com/motadata-aiops-docs/", title: "AIOps documentation (older)", product: "ObserveOps", label: "Older product" },
  { url: "https://docs.motadata.com/nms-docs/", title: "NMS documentation (older)", product: "ObserveOps", label: "Older product" },
];

export function siteState(s: any): { tone: "success" | "warning" | "error" | "info" | "neutral"; label: string; busy?: boolean } {
  if (s.job && ["Queued", "Processing"].includes(s.job.status)) return { tone: "info", label: s.job.status === "Queued" ? "Sync queued" : "Syncing", busy: true };
  if (s.ingest_status === "Failed") return { tone: "error", label: "Sync failed" };
  if (!s.current_version) return { tone: "neutral", label: "Not synced yet" };
  if (s.status === "Pending") return { tone: "warning", label: "Awaiting approval" };
  if (s.status === "Approved") return { tone: "success", label: "Approved" };
  return { tone: "neutral", label: s.status };
}

function SiteState({ s }: { s: any }) {
  const st = siteState(s);
  if (st.busy) return <span className="inline-flex items-center gap-2 text-sm text-info"><Loader2 size={14} className="animate-spin" />{st.label}</span>;
  return <Badge tone={st.tone}>{st.label}</Badge>;
}

/** List of docs sites with their page counts; opens the site drawer. */
export function Sites({ onAdd, open, setOpen }: { onAdd: () => void; open: number | null; setOpen: (id: number | null) => void }) {
  const { can } = useSession();
  const list = useApi<any[]>("/knowledge/sites");
  const busy = (list.data || []).some((s) => s.job && ["Queued", "Processing"].includes(s.job.status));
  useEffect(() => {
    if (!busy) return;
    const t = setInterval(() => list.reload(), 4000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [busy]);
  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted">Whole documentation sites, such as docs.motadata.com. Every page is found from the site's sitemap (or its links),
        indexed and cited on its own. Sync again to pick up changes: only changed pages are processed. Approve a site once to use all its pages.</p>
      {list.loading && !list.data ? <Spinner /> : (
        <Table head={["Site", "Product", "Pages", "Last sync", "Status", ""]} empty="No docs sites yet.">
          {(list.data || []).map((s) => (
            <tr key={s.id} className="cursor-pointer" onClick={() => setOpen(s.id)}>
              <td><div className="font-semibold">{s.title}</div><div className="text-sm text-muted break-all">{s.url}</div></td>
              <td className="whitespace-nowrap">{s.product}{s.product_version && ` ${s.product_version}`}{s.label && <div><Badge tone="neutral">{s.label}</Badge></div>}</td>
              <td className="whitespace-nowrap text-sm">{s.pages.total}{s.pages.failed > 0 && <span className="text-error"> · {s.pages.failed} failed</span>}</td>
              <td className="whitespace-nowrap text-sm text-muted">{s.job && ["Queued", "Processing"].includes(s.job.status) ? s.job.message : fmtDate(s.last_fetch_ok_at, true) || "never"}</td>
              <td><SiteState s={s} /></td>
              <td><Button variant="ghost">Open</Button></td>
            </tr>
          ))}
        </Table>
      )}
      {can("knowledge.register_url") && !(list.data || []).length && <div><Button variant="primary" onClick={onAdd}><Globe size={14} /> Add docs site</Button></div>}
      <SiteDrawer id={open} onClose={() => setOpen(null)} onChanged={list.reload} />
    </div>
  );
}

export function AddSiteDrawer({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: (id: number) => void }) {
  const sections = useApi<any[]>(open ? "/knowledge/sections" : null, [open]);
  const docsSection = (sections.data || []).find((s) => s.key === "online_documentation") || (sections.data || [])[0];
  const blank = { url: "", title: "", product: "ObserveOps", product_version: "", label: "", page_limit: 3000, delay_ms: 300, fetch_now: true, section_id: "" };
  const [f, setF] = useState<any>(blank);
  const [err, setErr] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => { if (open) { setF({ ...blank, section_id: docsSection ? String(docsSection.id) : "" }); setErr(""); } },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [open, docsSection?.id]);
  async function save() {
    setSaving(true); setErr("");
    try {
      const r = await api.post<any>("/knowledge/sites", { ...f, section_id: Number(f.section_id), page_limit: Number(f.page_limit), delay_ms: Number(f.delay_ms) });
      onDone(r.id);
    } catch (e) { setErr((e as Error).message); } finally { setSaving(false); }
  }
  return (
    <Drawer open={open} onClose={onClose} title="Add a documentation site"
      subtitle="Every page under the address is fetched, indexed and cited on its own. Nothing is used in answers until the site is approved."
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" loading={saving} onClick={save}>{f.fetch_now ? "Add and sync" : "Add"}</Button></>}>
      <div className="flex flex-col gap-4">
        {err && <Alert tone="error">{err}</Alert>}
        <div className="flex flex-wrap gap-2">{SUGGESTED.map((x) => (
          <button key={x.url} type="button" className="rounded border border-border px-2 py-1 text-sm hover:bg-mono-50"
            onClick={() => setF({ ...f, url: x.url, title: x.title, product: x.product, label: x.label })}>{x.title}</button>))}</div>
        <Field label="Site address" hint="Pages must start with this address, e.g. https://docs.motadata.com/observeops-docs/">
          <Input value={f.url} onChange={(e) => setF({ ...f, url: e.target.value })} placeholder="https://docs.motadata.com/…" /></Field>
        <Field label="Name"><Input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
        <Field label="Section"><Select value={f.section_id} onChange={(e) => setF({ ...f, section_id: e.target.value })}
          options={(sections.data || []).filter((s) => s.enabled).map((s) => ({ value: String(s.id), label: s.name }))} /></Field>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Product"><Select value={f.product} onChange={(e) => setF({ ...f, product: e.target.value })} options={PRODUCTS} /></Field>
          <Field label="Product version"><Input value={f.product_version} placeholder="e.g. 8.2" onChange={(e) => setF({ ...f, product_version: e.target.value })} /></Field>
        </div>
        <Field label="Label" hint="Older-product pages are still searchable; answers say they are from an older product.">
          <Select value={f.label} onChange={(e) => setF({ ...f, label: e.target.value })} options={LABELS} /></Field>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Page limit"><Input inputMode="numeric" value={f.page_limit} onChange={(e) => setF({ ...f, page_limit: e.target.value.replace(/\D/g, "") })} /></Field>
          <Field label="Pause between pages (ms)" hint="Keeps the load on the site low."><Input inputMode="numeric" value={f.delay_ms} onChange={(e) => setF({ ...f, delay_ms: e.target.value.replace(/\D/g, "") })} /></Field>
        </div>
        <Toggle checked={f.fetch_now} onChange={(v) => setF({ ...f, fetch_now: v })} label="Fetch the pages from this server now" />
        {!f.fetch_now && <Alert tone="info">Use this when the server has no internet access: after adding, download the crawl script from the site, run it on a laptop with internet, and import the ZIP it makes.</Alert>}
      </div>
    </Drawer>
  );
}

function SiteDrawer({ id, onClose, onChanged }: { id: number | null; onClose: () => void; onChanged: () => void }) {
  const { can } = useSession();
  const site = useApi<any>(id ? "/knowledge/sites" : null, [id]);
  const s = (site.data || []).find((x: any) => x.id === id);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [note, setNote] = useState("");
  const [edit, setEdit] = useState<any | null>(null);
  const running = s?.job && ["Queued", "Processing"].includes(s.job.status);
  useEffect(() => { setErr(""); setMsg(""); setEdit(null); }, [id]);
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => { site.reload(); onChanged(); }, 4000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running]);
  const act = async (fn: () => Promise<any>, ok: string) => {
    setErr(""); setMsg("");
    try { await fn(); setMsg(ok); site.reload(); onChanged(); } catch (e) { setErr((e as Error).message); }
  };
  const r = s?.report;
  const stat = (k: string, v: ReactNode) => <div><dt className="text-muted">{k}</dt><dd className="font-semibold">{v}</dd></div>;
  return (
    <Drawer open={!!id} onClose={onClose} title={s?.title || "Docs site"} subtitle={s?.url}>
      {!s ? <Spinner /> : (
        <div className="flex flex-col gap-6">
          {err && <Alert tone="error">{err}</Alert>}
          {msg && <Alert tone="success">{msg}</Alert>}
          <div className="flex flex-wrap items-center gap-3"><SiteState s={s} />{s.label && <Badge tone="neutral">{s.label}</Badge>}
            <span className="text-sm text-muted">{s.product}{s.product_version && ` ${s.product_version}`} · {s.section}</span></div>
          {running && <Alert tone="info">{s.job.message || "Starting"} ({s.job.progress}%)</Alert>}
          {s.ingest_error && <Alert tone="error">{s.ingest_error}</Alert>}

          <dl className="grid grid-cols-3 gap-x-6 gap-y-3 text-sm">
            {stat("Pages", s.pages.total)}{stat("Approved", s.pages.approved)}{stat("Failed", s.pages.failed)}
          </dl>
          {r && (
            <section className="flex flex-col gap-2 border-t border-lightborder pt-4 text-sm">
              <h3 className="font-semibold">Last sync · {fmtDate(r.at, true)} · {r.how}</h3>
              <p>{r.pages_found} pages found: <b>{r.new}</b> new, <b>{r.changed}</b> changed, {r.unchanged} unchanged, {r.removed} removed, <span className={r.failed ? "text-error" : ""}>{r.failed} failed</span>.</p>
              {r.truncated && <Alert tone="warning">The page limit ({s.page_limit}) was reached, so some pages were not read and none were marked removed. Raise the limit and sync again.</Alert>}
              {r.changed_pages?.length > 0 && <details><summary className="cursor-pointer">Changed pages</summary>
                <ul className="mt-1 list-disc pl-5 text-muted">{r.changed_pages.map((u: string) => <li key={u} className="break-all">{decodeURI(u)}</li>)}</ul></details>}
              {r.failed_pages?.length > 0 && <details><summary className="cursor-pointer text-error">Pages that could not be read</summary>
                <ul className="mt-1 list-disc pl-5 text-muted">{r.failed_pages.map((p: any) => <li key={p.url} className="break-all">{decodeURI(p.url)}: {p.error}</li>)}</ul></details>}
            </section>
          )}

          <div className="flex flex-wrap gap-2">
            {can("knowledge.register_url") && <Button disabled={running} onClick={() => act(() => api.post(`/knowledge/sites/${s.id}/sync`), "Sync started.")}><RefreshCw size={14} /> Sync now</Button>}
            {can("knowledge.upload") && (
              <label className={buttonClass("secondary")}>
                <Upload size={14} /> Import ZIP
                <input type="file" accept=".zip" className="hidden" disabled={running} onChange={async (e) => {
                  const x = e.target.files?.[0]; e.target.value = ""; if (!x) return;
                  const fd = new FormData(); fd.set("file", x);
                  await act(() => api.upload(`/knowledge/sites/${s.id}/import`, fd), "ZIP accepted; the pages are being indexed.");
                }} />
              </label>)}
            {can("knowledge.upload") && <Button variant="ghost" onClick={() => download("/knowledge/sites-crawl-script").catch((e: Error) => setErr(e.message))}><Download size={14} /> Crawl script</Button>}
            {can("knowledge.register_url") && !edit && <Button variant="ghost" onClick={() => setEdit({ title: s.title, product: s.product, product_version: s.product_version, label: s.label, page_limit: s.page_limit, delay_ms: s.delay_ms })}>Settings</Button>}
          </div>
          <p className="-mt-4 text-sm text-muted">No internet on the server? Run the crawl script on a laptop: <code>python3 docs_crawl_to_zip.py {s.url}</code>, then Import ZIP.</p>

          {edit && (
            <section className="flex flex-col gap-3 border-t border-lightborder pt-4">
              <Field label="Name"><Input value={edit.title} onChange={(e) => setEdit({ ...edit, title: e.target.value })} /></Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Product"><Select value={edit.product} onChange={(e) => setEdit({ ...edit, product: e.target.value })} options={PRODUCTS} /></Field>
                <Field label="Product version"><Input value={edit.product_version} onChange={(e) => setEdit({ ...edit, product_version: e.target.value })} /></Field>
                <Field label="Label"><Select value={edit.label} onChange={(e) => setEdit({ ...edit, label: e.target.value })} options={LABELS} /></Field>
                <Field label="Page limit"><Input value={edit.page_limit} onChange={(e) => setEdit({ ...edit, page_limit: e.target.value.replace(/\D/g, "") })} /></Field>
                <Field label="Pause between pages (ms)"><Input value={edit.delay_ms} onChange={(e) => setEdit({ ...edit, delay_ms: e.target.value.replace(/\D/g, "") })} /></Field>
              </div>
              <div className="flex gap-2"><Button variant="primary" onClick={() => act(() => api.patch(`/knowledge/sites/${s.id}`, { ...edit, page_limit: Number(edit.page_limit), delay_ms: Number(edit.delay_ms) }).then(() => setEdit(null)), "Settings saved; pages updated.")}>Save</Button>
                <Button variant="ghost" onClick={() => setEdit(null)}>Cancel</Button></div>
            </section>)}

          {can("knowledge.approve") && s.current_version > 0 && (
            <section className="flex flex-col gap-2 border-t border-lightborder pt-4">
              <h3 className="text-sm font-semibold">Approval</h3>
              <p className="text-sm text-muted">Approving the site approves all its pages. Pages that change on the site later stay approved (they are the official documentation) and are listed after each sync.</p>
              <Textarea rows={2} placeholder="Note for the record (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
              <div className="flex gap-2">
                {s.status === "Pending" && <><Button variant="primary" onClick={() => act(() => api.post(`/knowledge/sources/${s.id}/approve`, { note }), "Site approved.")}>Approve site</Button>
                  <Button variant="ghost" onClick={() => act(() => api.post(`/knowledge/sources/${s.id}/reject`, { note }), "Site rejected.")}>Reject</Button></>}
                {s.status === "Approved" && <Button variant="danger" onClick={() => act(() => api.post(`/knowledge/sources/${s.id}/disable`, { note }), "Site disabled; its pages are no longer used.")}>Disable</Button>}
                {["Disabled", "Rejected"].includes(s.status) && <Button onClick={() => act(() => api.post(`/knowledge/sources/${s.id}/approve`, { note }), "Site approved.")}>Approve again</Button>}
              </div>
            </section>)}

          <Pages id={s.id} version={`${s.current_version}-${s.status}`} />
        </div>
      )}
    </Drawer>
  );
}

function Pages({ id, version }: { id: number; version: string }) {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const qs = new URLSearchParams({ q, status, offset: String(offset) }).toString();
  const pages = useApi<any>(`/knowledge/sites/${id}/pages?${qs}`, [qs, version]);
  return (
    <section className="flex flex-col gap-2 border-t border-lightborder pt-4">
      <h3 className="text-sm font-semibold">Pages {pages.data && `(${pages.data.total})`}</h3>
      <div className="flex gap-2">
        <div className="relative flex-1"><Search size={14} className="absolute left-2 top-2 text-muted" />
          <Input className="pl-8" placeholder="Search title or address" value={q} onChange={(e) => { setQ(e.target.value); setOffset(0); }} /></div>
        <Select className="w-40" value={status} onChange={(e) => { setStatus(e.target.value); setOffset(0); }}
          options={[{ value: "", label: "All" }, "Approved", "Pending", "Disabled", { value: "Failed", label: "Failed" }]} />
      </div>
      {!pages.data ? <Spinner /> : (
        <ul className="divide-y divide-lightborder text-sm">
          {pages.data.pages.map((p: any) => (
            <li key={p.id} className="py-2">
              <a className="font-semibold underline-offset-2 hover:underline" href={p.url} target="_blank" rel="noreferrer">{p.title}</a>
              <div className="flex flex-wrap gap-2 text-muted"><span>{p.status}</span>{p.version > 1 && <span>· version {p.version}</span>}
                <span>· {fmtDate(p.fetched_at)}</span>{p.error && <span className="text-error">· {p.error}</span>}</div>
            </li>))}
        </ul>)}
      {pages.data && pages.data.total > 100 && (
        <div className="flex items-center gap-2 text-sm">
          <Button variant="ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 100))}>Previous</Button>
          <span>{offset + 1}–{Math.min(offset + 100, pages.data.total)} of {pages.data.total}</span>
          <Button variant="ghost" disabled={offset + 100 >= pages.data.total} onClick={() => setOffset(offset + 100)}>Next</Button>
        </div>)}
    </section>
  );
}

/** Past pre-bid query sheet: check the columns read, then import as knowledge (awaiting approval). */
export function PrebidImport({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [meta, setMeta] = useState({ customer: "", tender: "", date_text: "", outcome: "", product: "Both" });
  const [preview, setPreview] = useState<any | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) { setFile(null); setPreview(null); setErr(""); setMeta({ customer: "", tender: "", date_text: "", outcome: "", product: "Both" }); } }, [open]);
  async function check(f: File) {
    setFile(f); setPreview(null); setErr("");
    const fd = new FormData(); fd.set("file", f);
    try { setPreview(await api.upload("/knowledge/prebid/preview", fd)); } catch (e) { setErr((e as Error).message); }
  }
  async function save() {
    if (!file) return;
    setBusy(true); setErr("");
    const fd = new FormData(); fd.set("file", file);
    Object.entries(meta).forEach(([k, v]) => fd.set(k, v));
    try { await api.upload("/knowledge/prebid", fd); onDone(); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }
  const FIELD_LABEL: Record<string, string> = { query: "Query", reply: "Authority's reply", clause_text: "RFP clause", suggested_change: "Change requested",
    clause_no: "Clause no.", page: "Page", sl_no: "Sl. no." };
  return (
    <Drawer open={open} onClose={onClose} title="Import past pre-bid queries"
      subtitle="Queries raised in an earlier tender, with the authority's replies. New pre-bid queries reuse wording that worked."
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button>
        <Button variant="primary" loading={busy} disabled={!preview?.queries || !meta.customer.trim()} onClick={save}>Import {preview?.queries || ""} queries</Button></>}>
      <div className="flex flex-col gap-4">
        {err && <Alert tone="error">{err}</Alert>}
        <label className="flex cursor-pointer flex-col items-center gap-2 rounded border border-dashed border-border px-6 py-6 text-center hover:border-mono-500">
          <FileSpreadsheet size={20} className="text-muted" />
          {file ? <span className="text-sm font-semibold">{file.name}</span> : <span className="text-sm"><b>Choose the pre-bid query sheet</b> (Excel, or Word with a table)</span>}
          <input type="file" accept=".xlsx,.xls,.csv,.docx" className="hidden" onChange={(e) => { const x = e.target.files?.[0]; if (x) check(x); }} />
        </label>
        {preview && (preview.queries ? (
          <div className="flex flex-col gap-2 text-sm">
            <Alert tone="success">{preview.queries} queries found. Check the columns were read correctly.</Alert>
            {preview.columns.map((c: any, i: number) => (
              <div key={i} className="flex flex-wrap gap-1"><span className="text-muted">{c.sheet}:</span>
                {Object.entries(c).filter(([k]) => k !== "sheet").map(([k, v]) => <Badge key={k} tone="neutral">{FIELD_LABEL[k] || k} ← “{String(v)}”</Badge>)}</div>))}
            <Table head={["Query", "Reply"]}>{preview.sample.map((q: any, i: number) => <tr key={i}><td className="text-xs">{q.query}</td><td className="text-xs text-muted">{q.reply}</td></tr>)}</Table>
          </div>) : <Alert tone="warning">No queries found. The sheet needs a header row with a Query or Clarification column (and ideally Clause, Reply).</Alert>)}
        <Field label="Customer"><Input value={meta.customer} onChange={(e) => setMeta({ ...meta, customer: e.target.value })} /></Field>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Tender"><Input value={meta.tender} placeholder="name or number" onChange={(e) => setMeta({ ...meta, tender: e.target.value })} /></Field>
          <Field label="Date"><Input value={meta.date_text} placeholder="e.g. Mar 2025" onChange={(e) => setMeta({ ...meta, date_text: e.target.value })} /></Field>
          <Field label="Outcome"><Select value={meta.outcome} onChange={(e) => setMeta({ ...meta, outcome: e.target.value })} options={["", "Won", "Lost", "Not known"]} /></Field>
          <Field label="Product"><Select value={meta.product} onChange={(e) => setMeta({ ...meta, product: e.target.value })} options={PRODUCTS} /></Field>
        </div>
        <p className="text-sm text-muted">Stored in Internal presales knowledge as “Past pre-bid queries - {meta.customer || "customer"}”, awaiting approval like any other source.</p>
      </div>
    </Drawer>
  );
}
