"use client";
import { Download, Plus, Upload } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Alert, Badge, Button, Field, Input, Modal, PageHeader, Select, Spinner, StatusBadge, Table, Tabs } from "@/components/ui";
import { api, download, fmtDate, money } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { Templates } from "@/components/Templates";

export default function RfpHome() {
  const { can } = useSession();
  const [tab, setTab] = useState(can("rfp.view") ? "workspaces" : "submitted");
  const tabs = [
    ...(can("rfp.view") ? [{ key: "workspaces", label: "Workspaces" }] : []),
    ...(can("submitted.view") ? [{ key: "submitted", label: "Submitted RFP repository" }] : []),
    ...(can("rfp.view") ? [{ key: "templates", label: "Templates and samples" }] : []),
  ];
  return (
    <>
      <PageHeader title="RFP Intelligence" subtitle="Analyse RFPs and prepare compliance responses, proposals, PQ/TQ responses and pre-bid queries." />
      <Tabs tabs={tabs} active={tab} onChange={setTab} />
      {tab === "workspaces" && <Workspaces />}
      {tab === "submitted" && <Submitted />}
      {tab === "templates" && <Templates module="rfp" />}
    </>
  );
}

function Workspaces() {
  const { can } = useSession();
  const router = useRouter();
  const { data, loading } = useApi<any[]>("/rfp/workspaces");
  const customers = useApi<any[]>("/customers");
  const [open, setOpen] = useState(false);
  const [f, setF] = useState<any>({ name: "", customer_id: "", product_version: "", due_date: "", products: ["ObserveOps", "ServiceOps"] });
  async function create() {
    const r = await api.post("/rfp/workspaces", { ...f, customer_id: f.customer_id ? Number(f.customer_id) : null, due_date: f.due_date || null });
    router.push(`/rfp/${r.id}`);
  }
  return (
    <>
      <div className="mb-4 flex justify-end">{can("rfp.create") && <Button variant="primary" onClick={() => setOpen(true)}><Plus size={16} /> New workspace</Button>}</div>
      {loading ? <Spinner /> : (
        <Table head={["Workspace", "Customer", "Status", "Due", "Revision", "Est. cost", "Updated"]} empty="No RFP workspaces yet.">
          {(data || []).map((w) => (
            <tr key={w.id}>
              <td><Link className="font-semibold hover:underline" href={`/rfp/${w.id}`}>{w.name}</Link></td>
              <td>{w.customer}</td><td><StatusBadge status={w.status} /></td><td>{fmtDate(w.due_date)}</td><td>{w.revision}</td>
              <td>{money(w.estimated_cost)}</td><td>{fmtDate(w.updated_at)}</td>
            </tr>
          ))}
        </Table>
      )}
      <Modal open={open} title="New RFP workspace" onClose={() => setOpen(false)}>
        <div className="flex flex-col gap-4">
          <Field label="Name"><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
          <Field label="Customer context"><Select value={f.customer_id} onChange={(e) => setF({ ...f, customer_id: e.target.value })}
            options={[{ value: "", label: "None" }, ...(customers.data || []).map((c) => ({ value: c.id, label: c.name }))]} /></Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Product version answered against"><Input value={f.product_version} onChange={(e) => setF({ ...f, product_version: e.target.value })} /></Field>
            <Field label="Submission due"><Input type="date" value={f.due_date} onChange={(e) => setF({ ...f, due_date: e.target.value })} /></Field>
          </div>
          <Field label="Products">
            <div className="flex gap-4">{["ObserveOps", "ServiceOps"].map((p) => (
              <label key={p} className="flex items-center gap-1 text-sm"><input type="checkbox" checked={f.products.includes(p)}
                onChange={(e) => setF({ ...f, products: e.target.checked ? [...f.products, p] : f.products.filter((x: string) => x !== p) })} />{p}</label>))}
            </div>
          </Field>
          <div><Button variant="primary" disabled={!f.name} onClick={create}>Create</Button></div>
        </div>
      </Modal>
    </>
  );
}

function Submitted() {
  const { can } = useSession();
  const { data, loading, reload } = useApi<any[]>("/knowledge/submitted");
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<number | null>(null);
  const detail = useApi<any>(view ? `/knowledge/submitted/${view}` : null, [view]);
  const [error, setError] = useState("");
  async function upload(form: FormData) {
    try { await api.upload("/knowledge/submitted", form); setOpen(false); reload(); } catch (e) { setError((e as Error).message); }
  }
  return (
    <>
      <div className="mb-4 flex items-center justify-between">
        <p className="text-sm text-muted">Past RFPs with the responses Motadata submitted. Ranked below current documentation when answers are reused. Hold back at least three for testing.</p>
        {can("submitted.upload") && <Button variant="primary" onClick={() => setOpen(true)}><Upload size={16} /> Add past RFP</Button>}
      </div>
      {loading ? <Spinner /> : (
        <Table head={["Customer", "Industry", "Submitted", "Version", "Pairs", "Test set", ""]} empty="No submitted RFPs yet.">
          {(data || []).map((r) => (
            <tr key={r.id}>
              <td className="font-semibold">{r.customer}<div className="text-sm text-muted">{r.title}</div></td><td>{r.industry}</td>
              <td>{fmtDate(r.submitted_on)}</td><td>{r.product_version}</td><td>{r.pairs}</td>
              <td>{r.held_back_for_testing ? <Badge tone="warning">Held back</Badge> : ""}
                {can("submitted.manage") && <Button variant="ghost" className="ml-2" onClick={() => api.patch(`/knowledge/submitted/${r.id}?held_back_for_testing=${!r.held_back_for_testing}`).then(reload)}>
                  {r.held_back_for_testing ? "Release" : "Hold back"}</Button>}</td>
              <td><Button variant="ghost" onClick={() => setView(r.id)}>Open</Button></td>
            </tr>
          ))}
        </Table>
      )}
      <Modal open={open} title="Add past RFP" onClose={() => setOpen(false)}>
        <form className="flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); upload(new FormData(e.currentTarget)); }}>
          {error && <Alert tone="error">{error}</Alert>}
          <div className="grid grid-cols-2 gap-4">
            <Field label="Customer"><Input name="customer" required /></Field>
            <Field label="Industry"><Input name="industry" /></Field>
            <Field label="Submitted on"><Input name="submitted_on" type="date" /></Field>
            <Field label="Product version"><Input name="product_version" /></Field>
          </div>
          <Field label="Title"><Input name="title" /></Field>
          <Field label="Compliance sheet (XLSX/XLS/CSV)" hint="Stored as requirement and response pairs, each searchable on its own."><input type="file" name="compliance_sheet" accept=".xlsx,.xls,.csv" /></Field>
          <Field label="RFP and response documents"><input type="file" name="documents" multiple /></Field>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" name="held_back_for_testing" value="true" /> Hold back for testing (not used for answers)</label>
          <div><Button variant="primary" type="submit">Save</Button></div>
        </form>
      </Modal>
      <Modal open={!!view} title={detail.data ? `${detail.data.customer} Â· ${fmtDate(detail.data.submitted_on)}` : "Submitted RFP"} onClose={() => setView(null)} wide>
        {detail.data && (
          <div className="flex flex-col gap-4">
            <div className="flex flex-wrap gap-2">{detail.data.files.map((f: any) => (
              <Button key={f.file_id} onClick={() => download(`/knowledge/submitted/files/${f.file_id}`)}><Download size={16} /> {f.name}</Button>))}</div>
            <Table head={["Requirement", "Status", "Response", "Ref"]}>
              {detail.data.pairs.map((p: any) => <tr key={p.id}><td>{p.requirement}</td><td>{p.status}</td><td>{p.response}</td><td>{p.reference}</td></tr>)}
            </Table>
            {can("submitted.manage") && <div><Button variant="danger" onClick={() => api.del(`/knowledge/submitted/${view}`).then(() => { setView(null); reload(); })}>Delete</Button></div>}
          </div>
        )}
      </Modal>
    </>
  );
}
