"use client";
import { Plus } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Templates } from "@/components/Templates";
import { Alert, Button, Field, Input, Modal, PageHeader, Select, Spinner, StatusBadge, Table, Tabs, Textarea } from "@/components/ui";
import { api, fmtDate } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useSession } from "@/lib/session";

const MODULES = [["IM", "Infra monitoring"], ["NC", "NCCM"], ["FA", "Flow analytics"], ["SV", "Server/VM/DB monitoring"], ["LM", "Log management"],
  ["AP", "APM + RUM"], ["SD", "Service desk"], ["AM", "Asset management"], ["CM", "CMDB"], ["PM", "Patch management"], ["VM", "Vulnerability management"]];

function DemoHome() {
  const { can } = useSession();
  const [tab, setTab] = useState(useSearchParams().get("tab") || (can("demo.view") ? "scripts" : "usecases"));
  const tabs = [
    ...(can("demo.view") ? [{ key: "scripts", label: "Demo scripts" }] : []),
    ...(can("usecases.view", "demo.view") ? [{ key: "usecases", label: "Use-case library" }] : []),
    ...(can("demo.manage_templates") ? [{ key: "templates", label: "Word templates" }] : []),
  ];
  return (
    <>
      <PageHeader title="Demo Intelligence" subtitle="Customer-specific demo storylines built from the curated use-case library." />
      <Tabs tabs={tabs} active={tab} onChange={setTab} />
      {tab === "scripts" && <Scripts />}
      {tab === "usecases" && <UseCases />}
      {tab === "templates" && <Templates module="demo" />}
    </>
  );
}

function Scripts() {
  const { can } = useSession();
  const router = useRouter();
  const { data, loading } = useApi<any[]>("/demo/projects");
  const customers = useApi<any[]>("/customers");
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ title: "", customer_id: "" });
  async function create() {
    const r = await api.post("/demo/projects", { title: f.title, customer_id: f.customer_id ? Number(f.customer_id) : null,
      inputs: { products: ["ObserveOps", "ServiceOps"], duration_minutes: 45, audience: "IT operations heads", technical_depth: "Medium" } });
    router.push(`/demo/${r.id}`);
  }
  return (
    <>
      <div className="mb-4 flex justify-end">{can("demo.create") && <Button variant="primary" onClick={() => setOpen(true)}><Plus size={16} /> New demo script</Button>}</div>
      {loading ? <Spinner /> : (
        <Table head={["Title", "Customer", "Version", "Outcome", "Updated"]} empty="No demo scripts yet.">
          {(data || []).map((p) => (
            <tr key={p.id}><td><Link href={`/demo/${p.id}`} className="font-semibold hover:underline">{p.title}</Link></td><td>{p.customer}</td>
              <td>{p.current_version || "-"}</td><td>{p.outcome && <StatusBadge status={p.outcome} />}</td><td>{fmtDate(p.updated_at)}</td></tr>
          ))}
        </Table>
      )}
      <Modal open={open} title="New demo script" onClose={() => setOpen(false)}>
        <div className="flex flex-col gap-4">
          <Field label="Title"><Input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
          <Field label="Customer context"><Select value={f.customer_id} onChange={(e) => setF({ ...f, customer_id: e.target.value })}
            options={[{ value: "", label: "None" }, ...(customers.data || []).map((c) => ({ value: c.id, label: c.name }))]} /></Field>
          <div><Button variant="primary" disabled={!f.title} onClick={create}>Create</Button></div>
        </div>
      </Modal>
    </>
  );
}

const EMPTY_UC = { name: "", product: "ObserveOps", module_key: "IM", pain: "", industries: [], navigation: [], what_to_show: "", expected_result: "",
  talk_track: "", value_statement: "", differentiator: "", objections: [], prerequisites: "", minutes: 10 };

function UseCases() {
  const { can } = useSession();
  const { data, loading, reload } = useApi<any[]>("/demo/use-cases");
  const [edit, setEdit] = useState<any | null>(null);
  return (
    <>
      <div className="mb-4 flex items-center justify-between">
        <p className="text-sm text-muted">Navigation and screen names come only from here or approved documentation. Target 20 to 30 use cases, approved by the Presales Manager.</p>
        {can("usecases.create") && <Button variant="primary" onClick={() => setEdit(EMPTY_UC)}><Plus size={16} /> New use case</Button>}
      </div>
      {loading ? <Spinner /> : (
        <Table head={["Use case", "Product", "Module", "Pain", "Minutes", "Status", ""]}>
          {(data || []).map((u) => (
            <tr key={u.id}><td className="font-semibold">{u.name}</td><td>{u.product}</td><td>{u.module_key}</td><td className="max-w-prose">{u.pain}</td>
              <td>{u.minutes}</td><td><StatusBadge status={u.status} /></td>
              <td className="whitespace-nowrap"><Button variant="ghost" onClick={() => setEdit(u)}>Open</Button>
                {u.status !== "Approved" && can("usecases.approve") && <Button variant="ghost" onClick={() => api.post(`/demo/use-cases/${u.id}/approve`).then(reload)}>Approve</Button>}</td></tr>
          ))}
        </Table>
      )}
      {edit && <UseCaseModal uc={edit} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); reload(); }} />}
    </>
  );
}

function UseCaseModal({ uc, onClose, onSaved }: { uc: any; onClose: () => void; onSaved: () => void }) {
  const { can } = useSession();
  const [u, setU] = useState({ ...uc, navigation_text: (uc.navigation || []).join("\n"), industries_text: (uc.industries || []).join(", "),
    objections_text: (uc.objections || []).map((o: any) => `${o.objection} => ${o.answer}`).join("\n") });
  const [err, setErr] = useState("");
  const editable = uc.id ? can("usecases.edit") : can("usecases.create");
  const s = (k: string, v: any) => setU({ ...u, [k]: v });
  async function save() {
    const body = { ...u, navigation: u.navigation_text.split("\n").map((x: string) => x.trim()).filter(Boolean),
      industries: u.industries_text.split(",").map((x: string) => x.trim()).filter(Boolean),
      objections: u.objections_text.split("\n").filter((x: string) => x.includes("=>")).map((x: string) => { const [o, a] = x.split("=>"); return { objection: o.trim(), answer: a.trim() }; }) };
    for (const k of ["navigation_text", "industries_text", "objections_text", "id", "status"]) delete body[k];
    try { if (uc.id) await api.put(`/demo/use-cases/${uc.id}`, body); else await api.post("/demo/use-cases", body); onSaved(); }
    catch (e) { setErr((e as Error).message); }
  }
  return (
    <Modal open title={uc.id ? uc.name : "New use case"} onClose={onClose} wide>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {err && <div className="lg:col-span-2"><Alert tone="error">{err}</Alert></div>}
        <Field label="Name"><Input disabled={!editable} value={u.name} onChange={(e) => s("name", e.target.value)} /></Field>
        <div className="grid grid-cols-3 gap-2">
          <Field label="Product"><Select disabled={!editable} value={u.product} onChange={(e) => s("product", e.target.value)} options={["ObserveOps", "ServiceOps"]} /></Field>
          <Field label="Module"><Select disabled={!editable} value={u.module_key} onChange={(e) => s("module_key", e.target.value)} options={MODULES.map(([v, l]) => ({ value: v, label: l }))} /></Field>
          <Field label="Minutes"><Input disabled={!editable} type="number" value={u.minutes} onChange={(e) => s("minutes", Number(e.target.value))} /></Field>
        </div>
        <Field label="Pain addressed"><Textarea disabled={!editable} rows={2} value={u.pain} onChange={(e) => s("pain", e.target.value)} /></Field>
        <Field label="Industries (comma separated)"><Input disabled={!editable} value={u.industries_text} onChange={(e) => s("industries_text", e.target.value)} /></Field>
        <Field label="Navigation and screens, in order (one per line)" hint="Use exact menu and screen names."><Textarea disabled={!editable} rows={6} value={u.navigation_text} onChange={(e) => s("navigation_text", e.target.value)} /></Field>
        <Field label="What to show"><Textarea disabled={!editable} rows={6} value={u.what_to_show} onChange={(e) => s("what_to_show", e.target.value)} /></Field>
        <Field label="Expected result"><Textarea disabled={!editable} rows={2} value={u.expected_result} onChange={(e) => s("expected_result", e.target.value)} /></Field>
        <Field label="Talk track"><Textarea disabled={!editable} rows={2} value={u.talk_track} onChange={(e) => s("talk_track", e.target.value)} /></Field>
        <Field label="Value statement"><Textarea disabled={!editable} rows={2} value={u.value_statement} onChange={(e) => s("value_statement", e.target.value)} /></Field>
        <Field label="Differentiator"><Textarea disabled={!editable} rows={2} value={u.differentiator} onChange={(e) => s("differentiator", e.target.value)} /></Field>
        <Field label="Objections (one per line: objection => answer)"><Textarea disabled={!editable} rows={3} value={u.objections_text} onChange={(e) => s("objections_text", e.target.value)} /></Field>
        <Field label="Demo environment prerequisites"><Textarea disabled={!editable} rows={3} value={u.prerequisites} onChange={(e) => s("prerequisites", e.target.value)} /></Field>
        {editable && <div className="lg:col-span-2"><Button variant="primary" onClick={save}>Save{uc.id ? " (needs approval again)" : ""}</Button></div>}
      </div>
    </Modal>
  );
}

export default function DemoPage() {
  return <Suspense><DemoHome /></Suspense>;
}
