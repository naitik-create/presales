"use client";
import { Plus } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Alert, Badge, Button, Card, Field, Input, Modal, PageHeader, Progress, Select, Spinner, StatusBadge, Table, Tabs, Textarea } from "@/components/ui";
import { api, fmtDate, money } from "@/lib/api";
import { refreshBranding, useBranding } from "@/lib/branding";
import { useApi } from "@/lib/hooks";
import { useSession } from "@/lib/session";

function AdminHome() {
  const { can } = useSession();
  const all = [
    ["users", "Users", "admin.users"], ["roles", "Roles and permissions", "admin.roles"], ["ai", "AI models", "admin.ai_config"],
    ["keys", "API keys", "admin.api_keys"], ["usage", "Usage and budget", "admin.usage"],
    ["branding", "Branding", "admin.branding"], ["settings", "Settings", "admin.settings"], ["audit", "Audit log", "admin.audit"], ["jobs", "Jobs", "admin.settings"],
  ].filter(([, , p]) => can(p)).map(([key, label]) => ({ key, label }));
  const [tab, setTab] = useState(useSearchParams().get("tab") || all[0]?.key || "users");
  return (
    <>
      <PageHeader title="Administration" />
      <Tabs tabs={all} active={tab} onChange={setTab} />
      {tab === "users" && <Users />}
      {tab === "roles" && <Roles />}
      {tab === "ai" && <AI />}
      {tab === "keys" && <ApiKeys />}
      {tab === "branding" && <BrandingTab />}
      {tab === "usage" && <Usage />}
      {tab === "settings" && <Settings />}
      {tab === "audit" && <Audit />}
      {tab === "jobs" && <Jobs />}
    </>
  );
}

function Users() {
  const users = useApi<any[]>("/admin/users");
  const roles = useApi<any[]>("/admin/roles");
  const [edit, setEdit] = useState<any | null>(null);
  const [secret, setSecret] = useState("");
  const [err, setErr] = useState("");
  async function save() {
    try {
      if (edit.id) await api.patch(`/admin/users/${edit.id}`, { full_name: edit.full_name, email: edit.email, role_ids: edit.role_ids, is_active: edit.is_active, is_scoring_participant: edit.is_scoring_participant });
      else { const r = await api.post("/admin/users", edit); setSecret(`Temporary password for ${r.username}: ${r.temporary_password}`); }
      setEdit(null); users.reload();
    } catch (e) { setErr((e as Error).message); }
  }
  return (
    <>
      {secret && <div className="mb-4"><Alert tone="info">{secret} — share it securely; the user must change it at first sign-in.</Alert></div>}
      <div className="mb-4 flex justify-end"><Button variant="primary" onClick={() => setEdit({ username: "", full_name: "", email: "", role_ids: [], is_scoring_participant: false })}><Plus size={16} /> New user</Button></div>
      <Table head={["User", "Roles", "Scoring participant", "Status", "Last sign-in", ""]}>
        {(users.data || []).map((u) => (
          <tr key={u.id}><td className="font-semibold">{u.full_name}<div className="text-sm font-normal text-muted">{u.username} {u.email}</div></td>
            <td>{u.roles.map((r: any) => r.name).join(", ") || <span className="text-muted">No roles (no access)</span>}</td>
            <td>{u.is_scoring_participant ? "Yes" : ""}</td>
            <td>{u.is_active ? (u.locked ? <Badge tone="warning">Locked</Badge> : <Badge tone="success">Active</Badge>) : <Badge>Deactivated</Badge>}</td>
            <td>{fmtDate(u.last_login_at, true)}</td>
            <td className="whitespace-nowrap"><Button variant="ghost" onClick={() => setEdit({ ...u, role_ids: u.roles.map((r: any) => r.id) })}>Edit</Button>
              <Button variant="ghost" onClick={async () => { const r = await api.post(`/admin/users/${u.id}/reset-password`); setSecret(`Temporary password for ${u.username}: ${r.temporary_password}`); }}>Reset password</Button></td></tr>
        ))}
      </Table>
      <Modal open={!!edit} title={edit?.id ? `Edit ${edit.username}` : "New user"} onClose={() => setEdit(null)}>
        {edit && <div className="flex flex-col gap-4">
          {err && <Alert tone="error">{err}</Alert>}
          {!edit.id && <Field label="Username"><Input value={edit.username} onChange={(e) => setEdit({ ...edit, username: e.target.value })} /></Field>}
          <Field label="Full name"><Input value={edit.full_name} onChange={(e) => setEdit({ ...edit, full_name: e.target.value })} /></Field>
          <Field label="Email"><Input value={edit.email} onChange={(e) => setEdit({ ...edit, email: e.target.value })} /></Field>
          <Field label="Roles" hint="A user with no roles has no permissions.">
            <div className="flex flex-col gap-1">{(roles.data || []).map((r) => (
              <label key={r.id} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={edit.role_ids.includes(r.id)}
                onChange={(e) => setEdit({ ...edit, role_ids: e.target.checked ? [...edit.role_ids, r.id] : edit.role_ids.filter((x: number) => x !== r.id) })} />{r.name}</label>))}</div>
          </Field>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={edit.is_scoring_participant} onChange={(e) => setEdit({ ...edit, is_scoring_participant: e.target.checked })} /> Scoring participant</label>
          {edit.id && <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={edit.is_active} onChange={(e) => setEdit({ ...edit, is_active: e.target.checked })} /> Active</label>}
          <div><Button variant="primary" onClick={save}>Save</Button></div>
        </div>}
      </Modal>
    </>
  );
}

function Roles() {
  const roles = useApi<any[]>("/admin/roles");
  const perms = useApi<any[]>("/admin/permissions");
  const [edit, setEdit] = useState<any | null>(null);
  const [err, setErr] = useState("");
  const areas: Record<string, any[]> = {};
  (perms.data || []).forEach((p) => { (areas[p.area] ||= []).push(p); });
  async function save() {
    try {
      const body = { name: edit.name, description: edit.description, permissions: edit.permissions };
      if (edit.id) await api.put(`/admin/roles/${edit.id}`, body); else await api.post("/admin/roles", body);
      setEdit(null); roles.reload();
    } catch (e) { setErr((e as Error).message); }
  }
  return (
    <>
      <div className="mb-4 flex justify-end"><Button variant="primary" onClick={() => setEdit({ name: "", description: "", permissions: [] })}><Plus size={16} /> Custom role</Button></div>
      <Table head={["Role", "Description", "Permissions", ""]}>
        {(roles.data || []).map((r) => (
          <tr key={r.id}><td className="font-semibold">{r.name}{r.is_system && <div><Badge>Default</Badge></div>}</td><td>{r.description}</td><td>{r.permissions.length}</td>
            <td className="whitespace-nowrap"><Button variant="ghost" onClick={() => setEdit(r)}>Edit</Button>
              {!r.is_system && <Button variant="ghost" onClick={() => api.del(`/admin/roles/${r.id}`).then(roles.reload)}>Delete</Button>}</td></tr>
        ))}
      </Table>
      <Modal open={!!edit} title={edit?.id ? `Edit role: ${edit.name}` : "New role"} onClose={() => setEdit(null)} wide>
        {edit && <div className="flex flex-col gap-4">
          {err && <Alert tone="error">{err}</Alert>}
          <div className="grid grid-cols-2 gap-4">
            <Field label="Name"><Input value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></Field>
            <Field label="Description"><Input value={edit.description} onChange={(e) => setEdit({ ...edit, description: e.target.value })} /></Field>
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {Object.entries(areas).map(([area, list]) => (
              <Card key={area} title={area}>
                {list.map((p) => (
                  <label key={p.code} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={edit.permissions.includes(p.code)}
                    onChange={(e) => setEdit({ ...edit, permissions: e.target.checked ? [...edit.permissions, p.code] : edit.permissions.filter((x: string) => x !== p.code) })} />{p.label}</label>
                ))}
              </Card>
            ))}
          </div>
          <div><Button variant="primary" onClick={save}>Save role</Button></div>
        </div>}
      </Modal>
    </>
  );
}

function AI() {
  const agents = useApi<any[]>("/admin/ai/agents");
  const models = useApi<any[]>("/admin/ai/models");
  const emb = useApi<any>("/admin/ai/embedding");
  const [msg, setMsg] = useState<{ tone: "error" | "success" | "warning"; text: string } | null>(null);
  const [newModel, setNewModel] = useState({ model_id: "", label: "", input_per_mtok: "", output_per_mtok: "" });
  const upd = async (key: string, patch: any) => {
    try { await api.patch(`/admin/ai/agents/${key}`, patch); agents.reload(); setMsg({ tone: "success", text: "Agent updated" }); } catch (e) { setMsg({ tone: "error", text: (e as Error).message }); }
  };
  const modelOpts = (models.data || []).filter((m) => m.active).map((m) => ({ value: m.model_id, label: m.label }));
  const active = emb.data?.configurations.find((c: any) => c.is_active);
  return (
    <div className="flex flex-col gap-6">
      {msg && <Alert tone={msg.tone}>{msg.text}</Alert>}
      <Card title="Agents">
        <Table head={["Agent", "Module", "Model", "Effort", "Max output tokens", "Timeout (s)", "Retries", "Enabled"]}>
          {(agents.data || []).map((a) => (
            <tr key={a.agent_key}><td className="font-semibold">{a.label}</td><td>{a.module}</td>
              <td><Select value={a.model_id} onChange={(e) => upd(a.agent_key, { model_id: e.target.value })} options={modelOpts.some((m) => m.value === a.model_id) ? modelOpts : [{ value: a.model_id, label: a.model_id }, ...modelOpts]} /></td>
              <td><Select value={a.effort} onChange={(e) => upd(a.agent_key, { effort: e.target.value })} options={["low", "medium", "high", "xhigh", "max"]} /></td>
              <td><Input type="number" defaultValue={a.max_output_tokens} onBlur={(e) => Number(e.target.value) !== a.max_output_tokens && upd(a.agent_key, { max_output_tokens: Number(e.target.value) })} /></td>
              <td><Input type="number" defaultValue={a.timeout_seconds} onBlur={(e) => Number(e.target.value) !== a.timeout_seconds && upd(a.agent_key, { timeout_seconds: Number(e.target.value) })} /></td>
              <td><Input type="number" defaultValue={a.max_retries} onBlur={(e) => Number(e.target.value) !== a.max_retries && upd(a.agent_key, { max_retries: Number(e.target.value) })} /></td>
              <td><input type="checkbox" checked={a.enabled} onChange={(e) => upd(a.agent_key, { enabled: e.target.checked })} aria-label="Enabled" /></td></tr>
          ))}
        </Table>
      </Card>
      <Card title="Models and prices (per million tokens, used for cost estimates)">
        <Table head={["Model", "Model ID", "Input", "Output", "Active"]}>
          {(models.data || []).map((m) => (
            <tr key={m.model_id}><td>{m.label}</td><td>{m.model_id}</td><td>{m.input_per_mtok}</td><td>{m.output_per_mtok}</td>
              <td><input type="checkbox" checked={m.active} aria-label="Active" onChange={(e) => api.put("/admin/ai/models", { ...m, active: e.target.checked }).then(models.reload)} /></td></tr>
          ))}
        </Table>
        <div className="mt-4 flex flex-wrap items-end gap-2">
          <Field label="Model ID"><Input value={newModel.model_id} onChange={(e) => setNewModel({ ...newModel, model_id: e.target.value })} /></Field>
          <Field label="Label"><Input value={newModel.label} onChange={(e) => setNewModel({ ...newModel, label: e.target.value })} /></Field>
          <Field label="Input $/M"><Input type="number" step="any" value={newModel.input_per_mtok} onChange={(e) => setNewModel({ ...newModel, input_per_mtok: e.target.value })} /></Field>
          <Field label="Output $/M"><Input type="number" step="any" value={newModel.output_per_mtok} onChange={(e) => setNewModel({ ...newModel, output_per_mtok: e.target.value })} /></Field>
          <Button disabled={!newModel.model_id} onClick={() => api.put("/admin/ai/models", { ...newModel, input_per_mtok: Number(newModel.input_per_mtok || 0), output_per_mtok: Number(newModel.output_per_mtok || 0), active: true })
            .then(() => { setNewModel({ model_id: "", label: "", input_per_mtok: "", output_per_mtok: "" }); models.reload(); })}>Add or update</Button>
        </div>
      </Card>
      <Card title="Embeddings">
        {emb.data && <>
          <p className="text-sm">Active: <b>{active ? `${active.provider} · ${active.model_name} (${active.dimension} dimensions)` : "none"}</b></p>
          {emb.data.reindex_job && <div className="mt-2 text-sm">Re-index job #{emb.data.reindex_job.id}: <StatusBadge status={emb.data.reindex_job.status} /> {emb.data.reindex_job.message}<Progress value={emb.data.reindex_job.progress} /></div>}
          <Alert tone="warning">Vectors from different models are not compatible. Switching runs a full re-index as a background job; search keeps using the current index until it completes.</Alert>
          <div className="mt-2 flex gap-2">
            {Object.entries(emb.data.options).filter(([k]) => k !== active?.provider).map(([k, o]: any) => (
              <Button key={k} onClick={() => confirm(`Switch to ${o.model_name} and re-index every document?`) &&
                api.post("/admin/ai/embedding/switch", { provider: k, confirm: true }).then(emb.reload).catch((e) => setMsg({ tone: "error", text: e.message }))}>
                Switch to {k} ({o.model_name})</Button>))}
          </div>
        </>}
      </Card>
    </div>
  );
}

function ApiKeys() {
  const { data, reload } = useApi<any[]>("/admin/api-keys");
  const [edit, setEdit] = useState<any | null>(null);
  const [value, setValue] = useState("");
  const [label, setLabel] = useState("");
  const [msg, setMsg] = useState<{ tone: "error" | "success" | "warning"; text: string } | null>(null);
  const [busy, setBusy] = useState<string>("");

  async function save() {
    try {
      await api.put(`/admin/api-keys/${edit.provider}`, { value, label });
      setMsg({ tone: "success", text: `${edit.label || edit.provider} key saved (encrypted).` });
      setEdit(null); setValue(""); setLabel(""); reload();
    } catch (e) { setMsg({ tone: "error", text: (e as Error).message }); }
  }
  async function test(p: string) {
    setBusy(p);
    try {
      const r = await api.post(`/admin/api-keys/${p}/test`);
      setMsg({ tone: r.ok ? "success" : "error", text: r.message });
      reload();
    } catch (e) { setMsg({ tone: "error", text: (e as Error).message }); } finally { setBusy(""); }
  }
  return (
    <div className="flex flex-col gap-4">
      <Alert tone="info">
        Keys are encrypted before they are stored in the database and are never shown again after saving; only the last four
        characters are displayed. A key saved here takes precedence over the server&apos;s environment file and applies immediately.
      </Alert>
      {msg && <Alert tone={msg.tone}>{msg.text}</Alert>}
      <div className="flex justify-end"><Button onClick={() => { setEdit({ provider: "", label: "", custom: true, isNew: true }); setValue(""); setLabel(""); }}><Plus size={16} /> Other provider</Button></div>
      <Table head={["Provider", "Used for", "Key", "Source", "Last test", ""]}>
        {(data || []).map((k) => (
          <tr key={k.provider}>
            <td className="font-semibold">{k.label}<div className="text-sm font-normal text-muted">{k.provider}</div></td>
            <td>{k.used_for}</td>
            <td>{k.masked || <span className="text-muted">Not set</span>}</td>
            <td>{k.source === "database" ? <Badge tone="success">Stored encrypted</Badge> : k.source === "environment" ? <Badge tone="info">Environment file</Badge> : <Badge>None</Badge>}</td>
            <td>{k.last_tested_at ? <>{k.last_test_ok ? <Badge tone="success">Passed</Badge> : <Badge tone="error">Failed</Badge>}<div className="text-sm text-muted">{fmtDate(k.last_tested_at, true)}</div></> : ""}</td>
            <td className="whitespace-nowrap">
              <Button variant="ghost" onClick={() => { setEdit(k); setValue(""); setLabel(k.custom ? k.label : ""); }}>{k.masked ? "Replace" : "Add key"}</Button>
              {k.testable && k.source !== "none" && <Button variant="ghost" loading={busy === k.provider} onClick={() => test(k.provider)}>Test</Button>}
              {k.masked && <Button variant="ghost" onClick={() => confirm(`Delete the stored ${k.label} key?`) && api.del(`/admin/api-keys/${k.provider}`).then(reload)}>Delete</Button>}
            </td>
          </tr>
        ))}
      </Table>
      <Modal open={!!edit} title={edit?.isNew ? "Add API key for another provider" : `${edit?.masked ? "Replace" : "Add"} ${edit?.label} key`} onClose={() => setEdit(null)}>
        {edit && <div className="flex flex-col gap-4">
          {edit.isNew && <Field label="Provider ID" hint="Lower-case letters, digits and underscores, e.g. mistral">
            <Input value={edit.provider} onChange={(e) => setEdit({ ...edit, provider: e.target.value.toLowerCase() })} /></Field>}
          {edit.custom && <Field label="Display name"><Input value={label} onChange={(e) => setLabel(e.target.value)} /></Field>}
          <Field label="API key"><Input type="password" autoComplete="off" value={value} onChange={(e) => setValue(e.target.value)} placeholder="Paste the key" /></Field>
          <div><Button variant="primary" disabled={!value.trim() || !edit.provider} onClick={save}>Save encrypted</Button></div>
        </div>}
      </Modal>
    </div>
  );
}

function BrandingTab() {
  const { raw } = useBranding();
  const [msg, setMsg] = useState<{ tone: "error" | "success"; text: string } | null>(null);
  async function upload(kind: string, file: File) {
    const fd = new FormData();
    fd.set("file", file);
    try {
      await api.upload(`/admin/branding/${kind}`, fd);
      await refreshBranding();
      setMsg({ tone: "success", text: "Logo uploaded." });
    } catch (e) { setMsg({ tone: "error", text: (e as Error).message }); }
  }
  async function remove(kind: string) {
    try { await api.del(`/admin/branding/${kind}`); await refreshBranding(); setMsg({ tone: "success", text: "Logo removed." }); }
    catch (e) { setMsg({ tone: "error", text: (e as Error).message }); }
  }
  if (!raw) return <Spinner />;
  return (
    <div className="flex flex-col gap-4">
      <Alert tone="info">Use the official logo files only. Never redraw, recolour, rotate, stretch or add effects to the logo. Files up to 2 MB; SVG files must not contain scripts.</Alert>
      {msg && <Alert tone={msg.tone}>{msg.text}</Alert>}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {(["logo", "logomark", "export"] as const).map((k) => (
          <Card key={k} title={raw[k].label}>
            <p className="mb-4 text-sm text-muted">{raw[k].use}</p>
            <div className="mb-4 flex h-16 items-center justify-center rounded border border-lightborder bg-white p-2">
              {raw[k].set || k !== "export"
                // eslint-disable-next-line @next/next/no-img-element
                ? <img src={raw[k].url} alt={raw[k].label} className="max-h-12 max-w-full object-contain" />
                : <span className="text-sm text-muted">Not uploaded</span>}
            </div>
            <div className="flex items-center gap-2">
              <label className="inline-flex cursor-pointer items-center gap-2 rounded border border-border px-4 py-2 text-sm font-semibold hover:bg-offwhite">
                Upload
                <input type="file" className="hidden" accept={k === "export" ? ".png,.jpg,.jpeg" : ".svg,.png,.jpg,.jpeg"}
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(k, f); e.target.value = ""; }} />
              </label>
              {raw[k].set ? <Button variant="ghost" onClick={() => remove(k)}>Remove</Button> : <span className="text-sm text-muted">Using placeholder</span>}
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}

function Usage() {
  const { can } = useSession();
  const [f, setF] = useState({ start: "", end: "", module: "", agent: "", user_id: "" });
  const qs = new URLSearchParams(Object.entries(f).filter(([, v]) => v) as [string, string][]).toString();
  const { data, reload } = useApi<any>(`/admin/usage?${qs}`, [qs]);
  const [budget, setBudget] = useState<any>(null);
  if (!data) return <Spinner />;
  const b = budget || { amount: data.budget.amount ?? "", thresholds: data.budget.thresholds.join(","), hard_stop: data.budget.hard_stop };
  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card title={`Budget ${data.budget.month}`}>
          <div className="text-h3">{money(data.budget.spent)}</div>
          <div className="text-sm text-muted">{data.budget.amount ? `of ${money(data.budget.amount)} · remaining ${money(data.budget.remaining)}` : "No budget set"}</div>
          {data.budget.amount && <div className="mt-2"><Progress value={(100 * data.budget.spent) / data.budget.amount} /></div>}
          <p className="mt-2 text-sm text-muted">Calculated from this application&apos;s own logs, not the Anthropic account balance.</p>
          {can("admin.budget") && <div className="mt-4 flex flex-col gap-2">
            <Field label="Monthly budget (USD)"><Input type="number" value={b.amount} onChange={(e) => setBudget({ ...b, amount: e.target.value })} /></Field>
            <Field label="Alert thresholds (%)"><Input value={b.thresholds} onChange={(e) => setBudget({ ...b, thresholds: e.target.value })} /></Field>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={b.hard_stop} onChange={(e) => setBudget({ ...b, hard_stop: e.target.checked })} /> Hard stop at 100%</label>
            <div><Button onClick={() => api.put("/admin/budget", { amount: Number(b.amount), thresholds: String(b.thresholds).split(",").map((x: string) => Number(x.trim())).filter(Boolean), hard_stop: b.hard_stop }).then(() => { setBudget(null); reload(); })}>Save budget</Button></div>
          </div>}
        </Card>
        <Card title="Totals (filtered)" className="lg:col-span-2">
          <div className="flex flex-wrap gap-8"><Stat label="Calls" v={data.totals.calls} /><Stat label="Input tokens" v={data.totals.input_tokens.toLocaleString()} />
            <Stat label="Output tokens" v={data.totals.output_tokens.toLocaleString()} /><Stat label="Estimated cost" v={money(data.totals.cost)} /></div>
          <div className="mt-4 grid grid-cols-2 gap-4 md:grid-cols-5">
            <Field label="From"><Input type="date" value={f.start} onChange={(e) => setF({ ...f, start: e.target.value })} /></Field>
            <Field label="To"><Input type="date" value={f.end} onChange={(e) => setF({ ...f, end: e.target.value })} /></Field>
            <Field label="Module"><Select value={f.module} onChange={(e) => setF({ ...f, module: e.target.value })} options={["", "ask", "rfp", "demo", "knowledge"]} /></Field>
            <Field label="Agent"><Select value={f.agent} onChange={(e) => setF({ ...f, agent: e.target.value })} options={["", ...data.by_agent.map((a: any) => a.key)]} /></Field>
            <Field label="User"><Select value={f.user_id} onChange={(e) => setF({ ...f, user_id: e.target.value })} options={[{ value: "", label: "" }, ...data.by_user.map((u: any) => ({ value: u.id ?? "", label: u.key || "system" }))]} /></Field>
          </div>
        </Card>
      </div>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {(["by_user", "by_module", "by_agent", "by_model"] as const).map((k) => (
          <Card key={k} title={k.replace("by_", "By ")}>
            <Table head={["", "Calls", "Tokens in/out", "Cost"]}>
              {data[k].map((r: any, i: number) => <tr key={i}><td>{r.key || "system"}</td><td>{r.calls}</td><td>{r.input_tokens.toLocaleString()} / {r.output_tokens.toLocaleString()}</td><td>{money(r.cost)}</td></tr>)}
            </Table>
          </Card>
        ))}
      </div>
      <Card title="Recent calls">
        <Table head={["When", "User", "Module", "Agent", "Model", "Tokens in/out", "ms", "Status", "Job", "Cost"]}>
          {data.recent.map((r: any, i: number) => <tr key={i}><td>{fmtDate(r.at, true)}</td><td>{r.user}</td><td>{r.module}</td><td>{r.agent}</td><td>{r.model}</td>
            <td>{r.input_tokens}/{r.output_tokens}</td><td>{r.duration_ms}</td><td>{r.status}</td><td>{r.job_id || ""}</td><td>{money(r.cost)}</td></tr>)}
        </Table>
      </Card>
    </div>
  );
}

function Stat({ label, v }: { label: string; v: any }) {
  return <div><div className="text-sm text-muted">{label}</div><div className="text-h4">{v}</div></div>;
}

function Settings() {
  const { data, reload } = useApi<any>("/admin/settings");
  const [texts, setTexts] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState<{ tone: "error" | "success"; text: string } | null>(null);
  if (!data) return <Spinner />;
  const labels: Record<string, string> = { rfp_limits: "RFP processing limits", password_policy: "Password policy", session: "Sessions and sign-in",
    url_fetch_allowed_domains: "Domains allowed for URL sources", retrieval: "Retrieval and chunking" };
  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      {msg && <div className="lg:col-span-2"><Alert tone={msg.tone}>{msg.text}</Alert></div>}
      {Object.keys(data).map((k) => (
        <Card key={k} title={labels[k] || k}>
          <Textarea rows={8} value={texts[k] ?? JSON.stringify(data[k], null, 2)} onChange={(e) => setTexts({ ...texts, [k]: e.target.value })} />
          <div className="mt-2"><Button onClick={async () => {
            try { await api.put(`/admin/settings/${k}`, JSON.parse(texts[k] ?? JSON.stringify(data[k]))); setMsg({ tone: "success", text: `${labels[k]} saved` }); reload(); }
            catch (e) { setMsg({ tone: "error", text: (e as Error).message }); }
          }}>Save</Button></div>
        </Card>
      ))}
    </div>
  );
}

function Audit() {
  const [f, setF] = useState({ action: "", actor: "", start: "", end: "" });
  const qs = new URLSearchParams(Object.entries(f).filter(([, v]) => v) as [string, string][]).toString();
  const { data } = useApi<any[]>(`/admin/audit?${qs}`, [qs]);
  return (
    <>
      <div className="mb-4 grid grid-cols-2 gap-4 md:grid-cols-4">
        <Field label="Action contains"><Input value={f.action} onChange={(e) => setF({ ...f, action: e.target.value })} /></Field>
        <Field label="Actor"><Input value={f.actor} onChange={(e) => setF({ ...f, actor: e.target.value })} /></Field>
        <Field label="From"><Input type="date" value={f.start} onChange={(e) => setF({ ...f, start: e.target.value })} /></Field>
        <Field label="To"><Input type="date" value={f.end} onChange={(e) => setF({ ...f, end: e.target.value })} /></Field>
      </div>
      <p className="mb-2 text-sm text-muted">Audit records cannot be edited or deleted.</p>
      <Table head={["When", "Actor", "Action", "Record", "Details"]}>
        {(data || []).map((r) => <tr key={r.id}><td className="whitespace-nowrap">{fmtDate(r.at, true)}</td><td>{r.actor}</td><td>{r.action}</td>
          <td>{r.entity} {r.entity_id}</td><td className="max-w-prose break-all text-sm text-muted">{JSON.stringify(r.details)}</td></tr>)}
      </Table>
    </>
  );
}

function Jobs() {
  const [status, setStatus] = useState("");
  const { data, reload } = useApi<any[]>(`/admin/jobs${status ? `?status=${status}` : ""}`, [status]);
  return (
    <>
      <div className="mb-4 flex items-end gap-2">
        <Field label="Status"><Select value={status} onChange={(e) => setStatus(e.target.value)} options={["", "Queued", "Processing", "Completed", "Failed", "Cancelled"]} /></Field>
        <Button onClick={reload}>Refresh</Button>
      </div>
      <Table head={["#", "Kind", "Queue", "Status", "Progress", "Message / error", "Created", ""]}>
        {(data || []).map((j) => (
          <tr key={j.id}><td>{j.id}</td><td>{j.kind}</td><td>{j.queue}</td><td><StatusBadge status={j.status} /></td><td className="w-32"><Progress value={j.progress} /></td>
            <td className="max-w-prose text-sm">{j.error || j.message}</td><td>{fmtDate(j.created_at, true)}</td>
            <td className="whitespace-nowrap">{["Queued", "Processing"].includes(j.status) && <Button variant="ghost" onClick={() => api.post(`/admin/jobs/${j.id}/cancel`).then(reload)}>Cancel</Button>}
              {["Failed", "Cancelled"].includes(j.status) && <Button variant="ghost" onClick={() => api.post(`/admin/jobs/${j.id}/retry`).then(reload)}>Retry</Button>}</td></tr>
        ))}
      </Table>
    </>
  );
}

export default function AdminPage() {
  return <Suspense><AdminHome /></Suspense>;
}
