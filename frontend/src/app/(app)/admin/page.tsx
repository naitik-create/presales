"use client";
import { Activity, Bot, Briefcase, ChevronRight, ClipboardList, Image as ImageIcon, KeyRound, Plus, Search, Settings2, ShieldCheck, Users as UsersIcon, Wallet } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ReactNode, Suspense, useEffect, useMemo, useState } from "react";
import { Alert, Badge, Button, buttonClass, Card, Checkbox, cx, Drawer, Field, Input, Modal, NumberInput, PageHeader, Progress, SaveBar, Segmented, Select, SettingRow, Spinner, StatusBadge, Table, TagInput, Textarea, Toggle } from "@/components/ui";
import { api, fmtDate, money } from "@/lib/api";
import { refreshBranding, useBranding } from "@/lib/branding";
import { useApi } from "@/lib/hooks";
import { useSession } from "@/lib/session";

type Section = { key: string; label: string; perm: string; icon: ReactNode; title: string; description: string };
const GROUPS: { label: string; items: Section[] }[] = [
  { label: "People and access", items: [
    { key: "users", label: "Users", perm: "admin.users", icon: <UsersIcon size={16} />, title: "Users", description: "Create accounts, assign roles and manage sign-in." },
    { key: "roles", label: "Roles and permissions", perm: "admin.roles", icon: <ShieldCheck size={16} />, title: "Roles and permissions", description: "A role is a named set of permissions. Users can hold several roles." },
  ] },
  { label: "AI", items: [
    { key: "ai", label: "AI models", perm: "admin.ai_config", icon: <Bot size={16} />, title: "AI models", description: "Model, effort and limits for each agent, model prices and the embedding model." },
    { key: "keys", label: "API keys", perm: "admin.api_keys", icon: <KeyRound size={16} />, title: "API keys", description: "Keys for Claude and other AI services, stored encrypted in the database." },
    { key: "usage", label: "Usage and budget", perm: "admin.usage", icon: <Wallet size={16} />, title: "Usage and budget", description: "Calls, tokens and estimated cost by user, module and agent." },
  ] },
  { label: "Platform", items: [
    { key: "branding", label: "Branding", perm: "admin.branding", icon: <ImageIcon size={16} />, title: "Branding", description: "Logos used in the application and in exported documents." },
    { key: "settings", label: "Settings", perm: "admin.settings", icon: <Settings2 size={16} />, title: "Settings", description: "Security, processing limits, retrieval and allowed sources." },
  ] },
  { label: "Monitoring", items: [
    { key: "audit", label: "Audit log", perm: "admin.audit", icon: <ClipboardList size={16} />, title: "Audit log", description: "Every sign-in, permission change, approval and export. Records cannot be edited or deleted." },
    { key: "jobs", label: "Jobs", perm: "admin.settings", icon: <Activity size={16} />, title: "Background jobs", description: "Document ingestion, RFP analysis, re-indexing and other long-running work." },
  ] },
];

function AdminHome() {
  const { can } = useSession();
  const router = useRouter();
  const params = useSearchParams();
  const groups = GROUPS.map((g) => ({ ...g, items: g.items.filter((i) => can(i.perm)) })).filter((g) => g.items.length);
  const flat = groups.flatMap((g) => g.items);
  const tab = params.get("tab") || flat[0]?.key || "users";  // the URL is the source of truth, so links can switch sections
  const current = flat.find((s) => s.key === tab) || flat[0];
  const go = (k: string) => router.replace(`/admin?tab=${k}`, { scroll: false });
  if (!current) return <><PageHeader title="Administration" /><Alert tone="info">You have no administration permissions.</Alert></>;
  return (
    <>
      <div className="grid grid-cols-1 gap-8 lg:grid-cols-[192px_1fr]">
        <nav aria-label="Administration sections" className="flex flex-col gap-4 lg:sticky lg:top-16 lg:self-start">
          <div className="px-2 text-sm font-semibold">Administration</div>
          {groups.map((g) => (
            <div key={g.label}>
              <div className="mb-1 px-2 text-sm text-muted">{g.label}</div>
              <ul className="flex flex-col">
                {g.items.map((s) => (
                  <li key={s.key}>
                    <button onClick={() => go(s.key)} aria-current={s.key === current.key ? "page" : undefined}
                      className={cx("flex w-full items-center gap-2 rounded px-2 py-1 text-left text-sm",
                        s.key === current.key ? "bg-mono-100 font-semibold text-black" : "text-mono-600 hover:bg-offwhite hover:text-black")}>
                      {s.icon}{s.label}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>
        <section className="min-w-0">
          <header className="mb-6">
            <h1 className="text-h5">{current.title}</h1>
            <p className="text-sm text-muted">{current.description}</p>
          </header>
          {current.key === "users" && <Users />}
          {current.key === "roles" && <Roles />}
          {current.key === "ai" && <AI />}
          {current.key === "keys" && <ApiKeys />}
          {current.key === "branding" && <BrandingTab />}
          {current.key === "usage" && <Usage />}
          {current.key === "settings" && <Settings />}
          {current.key === "audit" && <Audit />}
          {current.key === "jobs" && <Jobs />}
        </section>
      </div>
    </>
  );
}

function initials(name: string) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]?.toUpperCase()).join("") || "?";
}

function Users() {
  const users = useApi<any[]>("/admin/users");
  const roles = useApi<any[]>("/admin/roles");
  const [edit, setEdit] = useState<any | null>(null);
  const [secret, setSecret] = useState("");
  const [err, setErr] = useState("");
  const [q, setQ] = useState("");
  const list = (users.data || []).filter((u) => !q || `${u.full_name} ${u.username} ${u.email}`.toLowerCase().includes(q.toLowerCase()));
  async function save() {
    setErr("");
    try {
      if (edit.id) await api.patch(`/admin/users/${edit.id}`, { full_name: edit.full_name, email: edit.email, role_ids: edit.role_ids, is_active: edit.is_active, is_scoring_participant: edit.is_scoring_participant });
      else { const r = await api.post("/admin/users", edit); setSecret(`Temporary password for ${r.username}: ${r.temporary_password}`); }
      setEdit(null); users.reload();
    } catch (e) { setErr((e as Error).message); }
  }
  return (
    <>
      {secret && <div className="mb-4"><Alert tone="info">{secret}. Share it securely; the user must change it at first sign-in.</Alert></div>}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
        <div className="relative w-full max-w-sm">
          <Search size={16} className="absolute left-3 top-3 text-muted" />
          <Input className="pl-8" placeholder="Search users" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <Button variant="primary" onClick={() => { setErr(""); setEdit({ username: "", full_name: "", email: "", role_ids: [], is_scoring_participant: false }); }}><Plus size={16} /> New user</Button>
      </div>
      <Table head={["User", "Roles", "Status", "Last sign-in", ""]} empty="No users match.">
        {list.map((u) => (
          <tr key={u.id}>
            <td>
              <div className="flex items-center gap-3">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-mono-100 text-sm font-semibold text-mono-700">{initials(u.full_name)}</span>
                <div><div className="font-semibold">{u.full_name}</div><div className="text-sm text-muted">{u.username}{u.email && ` · ${u.email}`}</div></div>
              </div>
            </td>
            <td>
              <div className="flex flex-wrap gap-1">
                {u.roles.map((r: any) => <span key={r.id} className="rounded border border-border bg-offwhite px-2 text-sm">{r.name}</span>)}
                {!u.roles.length && <span className="text-sm text-muted">No roles (no access)</span>}
                {u.is_scoring_participant && <span className="rounded border border-border px-2 text-sm text-muted">Scoring participant</span>}
              </div>
            </td>
            <td>{u.is_active ? (u.locked ? <Badge tone="warning">Locked</Badge> : <Badge tone="success">Active</Badge>) : <Badge>Deactivated</Badge>}</td>
            <td className="whitespace-nowrap text-muted">{fmtDate(u.last_login_at, true) || "Never"}</td>
            <td className="whitespace-nowrap text-right">
              <Button variant="ghost" onClick={() => { setErr(""); setEdit({ ...u, role_ids: u.roles.map((r: any) => r.id) }); }}>Edit</Button>
              <Button variant="ghost" onClick={async () => { const r = await api.post(`/admin/users/${u.id}/reset-password`); setSecret(`Temporary password for ${u.username}: ${r.temporary_password}`); }}>Reset password</Button>
            </td>
          </tr>
        ))}
      </Table>
      <Modal open={!!edit} title={edit?.id ? `Edit ${edit.full_name}` : "New user"} onClose={() => setEdit(null)}>
        {edit && <div className="flex flex-col gap-4">
          {err && <Alert tone="error">{err}</Alert>}
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {!edit.id && <Field label="Username"><Input value={edit.username} onChange={(e) => setEdit({ ...edit, username: e.target.value })} /></Field>}
            <Field label="Full name"><Input value={edit.full_name} onChange={(e) => setEdit({ ...edit, full_name: e.target.value })} /></Field>
            <Field label="Email"><Input type="email" value={edit.email} onChange={(e) => setEdit({ ...edit, email: e.target.value })} /></Field>
          </div>
          <div>
            <div className="mb-1 text-sm font-semibold">Roles</div>
            <p className="mb-2 text-sm text-muted">A user with no roles has no permissions.</p>
            <div className="rounded border border-border">
              {(roles.data || []).map((r) => (
                <div key={r.id} className="flex items-center justify-between gap-4 border-b border-lightborder px-3 py-2 last:border-b-0">
                  <div><div className="text-sm font-semibold">{r.name}</div><div className="text-sm text-muted">{r.description}</div></div>
                  <Toggle label={r.name} checked={edit.role_ids.includes(r.id)}
                    onChange={(on) => setEdit({ ...edit, role_ids: on ? [...edit.role_ids, r.id] : edit.role_ids.filter((x: number) => x !== r.id) })} />
                </div>
              ))}
            </div>
          </div>
          <SettingRow title="Scoring participant" help="Included in the Team Scorecard and sees their own score.">
            <Toggle label="Scoring participant" checked={edit.is_scoring_participant} onChange={(v) => setEdit({ ...edit, is_scoring_participant: v })} />
          </SettingRow>
          {edit.id && <SettingRow title="Account active" help="Deactivated users cannot sign in; their history is kept.">
            <Toggle label="Account active" checked={edit.is_active} onChange={(v) => setEdit({ ...edit, is_active: v })} />
          </SettingRow>}
          <div className="flex justify-end gap-2"><Button variant="ghost" onClick={() => setEdit(null)}>Cancel</Button><Button variant="primary" onClick={save}>{edit.id ? "Save changes" : "Create user"}</Button></div>
        </div>}
      </Modal>
    </>
  );
}

const EFFORT_INFO: Record<string, string> = {
  low: "Fastest and cheapest; for simple, well-defined tasks",
  medium: "Balanced quality and cost (recommended)",
  high: "More thorough reasoning; higher cost",
  xhigh: "Very thorough; for complex documents",
  max: "Maximum reasoning; slowest and most expensive",
};
const AGENT_INFO: Record<string, string> = {
  ask_motadata: "Answers product questions from approved sources with citations",
  demo_script: "Writes customer-specific demo storylines from the use-case library",
  requirement_extraction: "Finds and numbers every requirement in uploaded RFP documents",
  technical_compliance: "Drafts a compliance status and response for each requirement",
  rfp_analysis: "Summarises scope, dates, submission rules and mandatory conditions",
  architecture_sizing: "Recommends deployment architecture and extracts sizing inputs",
  risk_gap: "Lists product gaps, dependencies, penalties and unclear requirements",
  pq_tq: "Drafts PQ and TQ responses and lists missing credentials",
  boq_licensing: "Lists modules, licence metrics and quantities (no prices)",
  executive_synopsis: "Writes a short management overview",
  prebid_query: "Drafts clarification questions for the pre-bid meeting",
  proposal_generation: "Fills proposal template sections from the workspace",
};
const MODULE_NAMES: Record<string, string> = { ask: "Ask Motadata", rfp: "RFP Intelligence", demo: "Demo Intelligence" };
const PROVIDER_LABELS: Record<string, string> = { anthropic: "Anthropic Claude", openai: "OpenAI", google: "Google Gemini", azure_openai: "Azure OpenAI" };
const MODEL_ID_HINTS: Record<string, string> = {
  anthropic: "e.g. claude-sonnet-5-5", openai: "the model name from your OpenAI account",
  google: "the Gemini model name from Google AI Studio", azure_openai: "the deployment name in your Azure OpenAI resource",
};
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
const ktok = (n: number) => (n >= 1000 ? `${Math.round(n / 1000)}k` : String(n));

function Chip({ children, muted }: { children: ReactNode; muted?: boolean }) {
  return <span className={cx("inline-flex items-center whitespace-nowrap rounded border px-2 text-sm", muted ? "border-lightborder text-muted" : "border-border bg-offwhite text-mono-800")}>{children}</span>;
}

const AREA_HELP: Record<string, string> = {
  "RFP Intelligence": "RFP workspaces, compliance answers, proposals and exports",
  "Demo Intelligence": "Demo scripts and their exports",
  "Demo use cases": "The curated use-case library used for demo scripts",
  "Ask Motadata": "The product question assistant",
  "Knowledge Hub": "Uploading, approving and reading Knowledge Hub sources",
  "Submitted RFP repository": "Past RFPs and the answers that were submitted",
  "Team Scorecard": "The points ledger. Keep this to managers and participants",
  "Customer context": "Shared customer details used by RFP and demo work",
  "Administration": "Users, roles, AI settings, keys, budget and audit",
};

type RoleDraft = { id?: number; name: string; description: string; permissions: string[]; is_system?: boolean; user_count?: number };

function Roles() {
  const { can } = useSession();
  const roles = useApi<any[]>("/admin/roles");
  const perms = useApi<any[]>("/admin/permissions");
  const users = useApi<any[]>(can("admin.users") ? "/admin/users" : null);
  const [selected, setSelected] = useState<number | "new" | null>(null);
  const [draft, setDraft] = useState<RoleDraft | null>(null);
  const [view, setView] = useState<"permissions" | "members">("permissions");
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [filter, setFilter] = useState("");
  const [msg, setMsg] = useState<{ tone: "error" | "success"; text: string } | null>(null);
  const [saving, setSaving] = useState(false);

  const areas = useMemo(() => {
    const a: Record<string, any[]> = {};
    (perms.data || []).forEach((p) => { (a[p.area] ||= []).push(p); });
    return a;
  }, [perms.data]);
  const total = perms.data?.length || 0;
  const original = selected === "new" ? null : roles.data?.find((r) => r.id === selected) || null;

  // Select the first role once the list has loaded
  useEffect(() => {
    if (roles.data?.length && selected === null) pick(roles.data[0]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roles.data]);

  function pick(r: any) {
    setSelected(r.id); setDraft({ ...r, permissions: [...r.permissions] }); setView("permissions"); setMsg(null); setFilter("");
  }
  function newRole(copyFrom?: any) {
    setSelected("new");
    setDraft({ name: copyFrom ? `${copyFrom.name} (copy)` : "", description: copyFrom?.description || "", permissions: copyFrom ? [...copyFrom.permissions] : [] });
    setView("permissions"); setMsg(null);
  }
  const dirty = !!draft && (selected === "new" || JSON.stringify({ n: draft.name, d: draft.description, p: [...draft.permissions].sort() })
    !== JSON.stringify({ n: original?.name, d: original?.description, p: [...(original?.permissions || [])].sort() }));

  async function save() {
    if (!draft) return;
    setSaving(true); setMsg(null);
    try {
      const body = { name: draft.name.trim(), description: draft.description, permissions: draft.permissions };
      if (selected === "new") {
        const r = await api.post("/admin/roles", body);
        await roles.reload(); setSelected(r.id);
      } else {
        await api.put(`/admin/roles/${selected}`, body); await roles.reload();
      }
      setMsg({ tone: "success", text: `Role "${body.name}" saved.` });
    } catch (e) { setMsg({ tone: "error", text: (e as Error).message }); } finally { setSaving(false); }
  }
  async function remove() {
    if (!original || !confirm(`Delete the role "${original.name}"? Users lose the permissions it grants.`)) return;
    try { await api.del(`/admin/roles/${original.id}`); setSelected(null); setDraft(null); await roles.reload(); }
    catch (e) { setMsg({ tone: "error", text: (e as Error).message }); }
  }
  const setPerms = (codes: string[], on: boolean) => draft && setDraft({
    ...draft, permissions: on ? Array.from(new Set([...draft.permissions, ...codes])) : draft.permissions.filter((c) => !codes.includes(c)),
  });

  // keep the draft in step with the saved role after a reload
  useEffect(() => {
    if (typeof selected === "number" && roles.data) {
      const r = roles.data.find((x) => x.id === selected);
      if (r && !dirty) setDraft({ ...r, permissions: [...r.permissions] });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roles.data]);

  if (!roles.data || !perms.data) return <Spinner />;
  const members = (users.data || []).filter((u) => typeof selected === "number" && u.roles.some((r: any) => r.id === selected));
  const f = filter.trim().toLowerCase();

  return (
    <div className="grid grid-cols-1 gap-8 lg:grid-cols-[240px_1fr]">
      {/* role list */}
      <aside className="flex flex-col gap-1">
        <div className="mb-1 flex items-center justify-between px-2">
          <span className="text-sm text-muted">{roles.data.length} roles</span>
          <Button variant="primary" onClick={() => newRole()}><Plus size={14} /> New role</Button>
        </div>
        {roles.data.map((r) => (
          <button key={r.id} onClick={() => { if (!dirty || confirm("Discard unsaved changes?")) pick(r); }}
            className={cx("flex w-full flex-col rounded px-2 py-2 text-left", selected === r.id ? "bg-mono-100" : "hover:bg-offwhite")}>
            <span className={cx("text-sm", selected === r.id && "font-semibold")}>{r.name}</span>
            <span className="text-sm text-muted">{r.permissions.length} {r.permissions.length === 1 ? "permission" : "permissions"} · {r.user_count ?? 0} {r.user_count === 1 ? "user" : "users"}{r.is_system ? "" : " · custom"}</span>
          </button>
        ))}
        {selected === "new" && (
          <div className="rounded bg-mono-100 px-2 py-2"><div className="text-sm font-semibold">New role</div><div className="text-sm text-muted">Not saved</div></div>
        )}
      </aside>

      {/* role detail */}
      {draft && (
        <section className="min-w-0">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="grid min-w-0 flex-1 grid-cols-1 gap-3 md:grid-cols-[240px_1fr]">
              <Field label="Name"><Input value={draft.name} disabled={!!draft.is_system} onChange={(e) => setDraft({ ...draft, name: e.target.value })} placeholder="e.g. Bid desk" /></Field>
              <Field label="Description"><Input value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} placeholder="What this role is for" /></Field>
            </div>
            <div className="flex gap-1 pt-6">
              {typeof selected === "number" && <Button variant="secondary" onClick={() => newRole(original)}>Duplicate</Button>}
              {original && !original.is_system && <Button variant="danger" onClick={remove}>Delete</Button>}
            </div>
          </div>
          {draft.is_system && <p className="mt-2 text-sm text-muted">Built-in role: the name is fixed, permissions can be changed.</p>}

          <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-b border-lightborder pb-3">
            <Segmented active={view} onChange={(k) => setView(k as any)} items={[
              { key: "permissions", label: "Permissions", count: draft.permissions.length },
              ...(can("admin.users") && typeof selected === "number" ? [{ key: "members", label: "Members", count: members.length }] : []),
            ]} />
            {view === "permissions" && (
              <div className="flex items-center gap-2">
                <div className="relative">
                  <Search size={14} className="absolute left-2 top-2 text-muted" />
                  <Input className="w-48 pl-8" placeholder="Filter" value={filter} onChange={(e) => setFilter(e.target.value)} />
                </div>
                <Button variant="ghost" onClick={() => setOpen(Object.fromEntries(Object.keys(areas).map((a) => [a, !Object.values(open).some(Boolean)])))}>
                  {Object.values(open).some(Boolean) ? "Collapse all" : "Expand all"}
                </Button>
              </div>
            )}
          </div>

          {view === "permissions" && (
            <ul>
              {Object.entries(areas).map(([area, list]) => {
                const shown = f ? list.filter((p) => `${area} ${p.label}`.toLowerCase().includes(f)) : list;
                if (!shown.length) return null;
                const codes = list.map((p) => p.code);
                const on = codes.filter((c) => draft.permissions.includes(c)).length;
                const isOpen = !!f || !!open[area];
                return (
                  <li key={area} className="border-b border-lightborder">
                    <div className="flex items-center gap-3 py-2">
                      <Checkbox label={`All ${area} permissions`} checked={on === codes.length} indeterminate={on > 0} onChange={(v) => setPerms(codes, v)} />
                      <button className="flex min-w-0 flex-1 items-center justify-between gap-4 text-left" onClick={() => setOpen({ ...open, [area]: !open[area] })} aria-expanded={isOpen}>
                        <span className="text-sm">{area}</span>
                        <span className="flex shrink-0 items-center gap-2 text-sm text-muted">
                          {on === codes.length ? "All" : on ? `${on} of ${codes.length}` : "None"}
                          <ChevronRight size={16} className={cx("transition-transform", isOpen && "rotate-90")} />
                        </span>
                      </button>
                    </div>
                    {isOpen && (
                      <div className="pb-3 pl-8">
                        {AREA_HELP[area] && <p className="mb-2 text-sm text-muted">{AREA_HELP[area]}</p>}
                        <div className="grid grid-cols-1 gap-x-8 gap-y-1 md:grid-cols-2">
                          {shown.map((p) => (
                            <label key={p.code} className="flex cursor-pointer items-center gap-2 py-1 text-sm">
                              <Checkbox label={`${area}: ${p.label}`} checked={draft.permissions.includes(p.code)} onChange={(v) => setPerms([p.code], v)} />
                              {p.label}
                            </label>
                          ))}
                        </div>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}

          {view === "members" && (
            <div className="py-2">
              {members.length === 0 ? <p className="py-2 text-sm text-muted">No active users have this role.</p> : (
                <ul className="divide-y divide-lightborder">
                  {members.map((u) => (
                    <li key={u.id} className="flex items-center gap-3 py-2">
                      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-mono-100 text-sm font-semibold text-mono-700">{initials(u.full_name)}</span>
                      <span className="text-sm">{u.full_name}</span>
                      <span className="text-sm text-muted">{u.username}</span>
                    </li>
                  ))}
                </ul>
              )}
              <Link href="/admin?tab=users" className="mt-2 inline-flex items-center gap-1 text-sm text-mono-700 underline">Manage users</Link>
            </div>
          )}

          {(dirty || msg) && (
            <div className="sticky bottom-4 mt-6 flex items-center justify-end gap-3 rounded border border-border bg-white px-4 py-2 shadow-sm">
              <span className={cx("mr-auto text-sm", msg?.tone === "error" ? "text-error" : msg ? "text-success" : "text-muted")}>{msg ? msg.text : "Unsaved changes"}</span>
              {dirty && <Button variant="ghost" disabled={saving} onClick={() => selected === "new" ? (roles.data!.length ? pick(roles.data![0]) : setDraft(null)) : original && pick(original)}>Discard</Button>}
              {dirty && <Button variant="primary" loading={saving} disabled={!draft.name.trim()} onClick={save}>{selected === "new" ? "Create role" : "Save"}</Button>}
            </div>
          )}
        </section>
      )}
    </div>
  );
}

function AI() {
  const agents = useApi<any[]>("/admin/ai/agents");
  const models = useApi<any[]>("/admin/ai/models");
  const emb = useApi<any>("/admin/ai/embedding");
  const keys = useApi<any[]>("/admin/api-keys");
  const [view, setView] = useState<"agents" | "models" | "embeddings">("agents");
  const [msg, setMsg] = useState<{ tone: "error" | "success" | "warning"; text: string } | null>(null);
  const [configure, setConfigure] = useState<any | null>(null);
  const [modelEdit, setModelEdit] = useState<any | null>(null);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkModel, setBulkModel] = useState("");
  const [saving, setSaving] = useState(false);
  if (!agents.data || !models.data || !emb.data) return <Spinner />;

  const label = (id: string) => models.data!.find((m) => m.model_id === id)?.label || id;
  const providerOf = (id: string) => models.data!.find((m) => m.model_id === id)?.provider || "anthropic";
  const hasKey = (p: string) => !keys.data || keys.data.some((k) => k.provider === p && k.source !== "none");
  const modelOpts = models.data.filter((m) => m.active).map((m) => ({
    value: m.model_id, label: `${m.label} (${PROVIDER_LABELS[m.provider] || m.provider})${hasKey(m.provider) ? "" : " – no key"}`,
  }));
  const active = emb.data.configurations.find((c: any) => c.is_active);
  const byModule: Record<string, any[]> = {};
  agents.data.forEach((a) => { (byModule[a.module] ||= []).push(a); });
  const enabledCount = agents.data.filter((a) => a.enabled).length;

  // One banner for every provider that enabled agents depend on but has no key
  const missing = Object.entries(agents.data.filter((a) => a.enabled).reduce((acc: Record<string, number>, a) => {
    const p = providerOf(a.model_id);
    if (!hasKey(p)) acc[p] = (acc[p] || 0) + 1;
    return acc;
  }, {}));

  const patch = async (key: string, body: any, ok: string) => {
    try { await api.patch(`/admin/ai/agents/${key}`, body); agents.reload(); setMsg({ tone: "success", text: ok }); return true; }
    catch (e) { setMsg({ tone: "error", text: (e as Error).message }); return false; }
  };
  async function applyAll() {
    setSaving(true);
    try {
      for (const a of agents.data!) await api.patch(`/admin/ai/agents/${a.agent_key}`, { model_id: bulkModel });
      agents.reload(); setBulkOpen(false); setMsg({ tone: "success", text: `All agents now use ${label(bulkModel)}.` });
    } catch (e) { setMsg({ tone: "error", text: (e as Error).message }); } finally { setSaving(false); }
  }
  async function saveAgent() {
    setSaving(true);
    const { model_id, effort, max_output_tokens, timeout_seconds, max_retries } = configure;
    if (await patch(configure.agent_key, { model_id, effort, max_output_tokens, timeout_seconds, max_retries }, `${configure.label} saved.`)) setConfigure(null);
    setSaving(false);
  }
  async function saveModel() {
    setSaving(true);
    try {
      await api.put("/admin/ai/models", { ...modelEdit, input_per_mtok: Number(modelEdit.input_per_mtok || 0), output_per_mtok: Number(modelEdit.output_per_mtok || 0) });
      setModelEdit(null); models.reload(); setMsg({ tone: "success", text: "Model saved." });
    } catch (e) { setMsg({ tone: "error", text: (e as Error).message }); } finally { setSaving(false); }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <Segmented active={view} onChange={(k) => setView(k as any)} items={[
          { key: "agents", label: "Agents", count: agents.data.length },
          { key: "models", label: "Models", count: models.data.length },
          { key: "embeddings", label: "Embeddings" },
        ]} />
        {view === "agents" && <Button onClick={() => { setBulkModel(""); setBulkOpen(true); }}>Change model for all agents</Button>}
        {view === "models" && <Button variant="primary" onClick={() => setModelEdit({ model_id: "", label: "", provider: "openai", endpoint: "", input_per_mtok: "", output_per_mtok: "", active: true, isNew: true })}><Plus size={16} /> Add model</Button>}
      </div>

      {missing.map(([p, n]) => (
        <div key={p} className="flex flex-wrap items-center justify-between gap-4 rounded border border-warning bg-white px-4 py-3">
          <div className="flex items-start gap-3">
            <KeyRound size={20} className="mt-1 text-warning" />
            <div>
              <div className="text-sm font-semibold">{PROVIDER_LABELS[p] || p} is not connected</div>
              <div className="text-sm text-muted">{n} {n === 1 ? "agent uses" : "agents use"} this provider, but no API key is saved. These agents will fail until a key is added.</div>
            </div>
          </div>
          <Link href="/admin?tab=keys" className={buttonClass("primary")}>Add API key <ChevronRight size={16} /></Link>
        </div>
      ))}
      {msg && <Alert tone={msg.tone}>{msg.text}</Alert>}

      {view === "agents" && (
        <div className="overflow-x-auto rounded border border-border">
          <div className="flex items-center justify-between border-b border-border bg-offwhite px-4 py-3 text-sm text-muted">
            <span>{enabledCount} of {agents.data.length} agents on</span>
            <span>Select a row to change its model and limits</span>
          </div>
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-border text-left text-mono-600">
                <th className="px-4 py-2 font-semibold">Agent</th>
                <th className="px-4 py-2 font-semibold">Model</th>
                <th className="px-4 py-2 font-semibold">Effort</th>
                <th className="px-4 py-2 font-semibold">Output limit</th>
                <th className="px-4 py-2 font-semibold">Status</th>
                <th className="w-12 px-4 py-2"><span className="sr-only">Edit</span></th>
              </tr>
            </thead>
            {Object.entries(byModule).map(([mod, list]) => (
              <tbody key={mod}>
                <tr><td colSpan={6} className="bg-white px-4 pb-1 pt-4 text-sm font-semibold uppercase text-mono-600">{MODULE_NAMES[mod] || mod}</td></tr>
                {list.map((a) => {
                  const p = providerOf(a.model_id);
                  return (
                    <tr key={a.agent_key} onClick={() => setConfigure({ ...a })} className="cursor-pointer border-t border-lightborder hover:bg-offwhite">
                      <td className="px-4 py-3">
                        <div className={cx("font-semibold", !a.enabled && "text-muted")}>{a.label}</div>
                        <div className="text-sm text-muted">{AGENT_INFO[a.agent_key] || ""}</div>
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <div>{label(a.model_id)}</div>
                        <div className={cx("text-sm", hasKey(p) ? "text-muted" : "text-error")}>{PROVIDER_LABELS[p]}{hasKey(p) ? "" : " · no key"}</div>
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">{p === "anthropic" ? cap(a.effort) : <span className="text-muted">Not used</span>}</td>
                      <td className="whitespace-nowrap px-4 py-3">{ktok(a.max_output_tokens)} tokens</td>
                      <td className="whitespace-nowrap px-4 py-3" onClick={(e) => e.stopPropagation()}>
                        <span className="flex items-center gap-2">
                          <Toggle label={`${a.label} enabled`} checked={a.enabled} onChange={(v) => patch(a.agent_key, { enabled: v }, `${a.label} turned ${v ? "on" : "off"}.`)} />
                          <span className={a.enabled ? "" : "text-muted"}>{a.enabled ? "On" : "Off"}</span>
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right text-muted"><ChevronRight size={20} /></td>
                    </tr>
                  );
                })}
              </tbody>
            ))}
          </table>
        </div>
      )}

      {view === "models" && (
        <>
          <p className="max-w-prose text-sm text-muted">Models from Anthropic, OpenAI, Google Gemini and Azure OpenAI can be added here and then chosen for any agent. Each provider needs its key in API keys. Prices are per million tokens and are only used to estimate cost.</p>
          <Table head={["Model", "Provider", "Input / 1M tokens", "Output / 1M tokens", "Used by", "Available", ""]}>
            {models.data.map((m) => {
              const used = agents.data!.filter((a) => a.model_id === m.model_id).length;
              return (
                <tr key={m.model_id}>
                  <td><div className="font-semibold">{m.label}</div><div className="text-sm text-muted">{m.model_id}</div></td>
                  <td className="whitespace-nowrap">{PROVIDER_LABELS[m.provider] || m.provider}<div className={cx("text-sm", hasKey(m.provider) ? "text-success" : "text-error")}>{hasKey(m.provider) ? "Key saved" : "No key"}</div></td>
                  <td>{money(Number(m.input_per_mtok))}</td>
                  <td>{money(Number(m.output_per_mtok))}</td>
                  <td className="whitespace-nowrap">{used ? `${used} ${used === 1 ? "agent" : "agents"}` : <span className="text-muted">None</span>}</td>
                  <td><Toggle label={`${m.label} available`} checked={m.active} onChange={(v) => api.put("/admin/ai/models", { ...m, active: v }).then(models.reload)} /></td>
                  <td className="text-right"><Button variant="ghost" onClick={() => setModelEdit({ ...m })}>Edit</Button></td>
                </tr>
              );
            })}
          </Table>
        </>
      )}

      {view === "embeddings" && (
        <>
          <p className="max-w-prose text-sm text-muted">The embedding model turns Knowledge Hub documents into vectors for search. Vectors from different models cannot be mixed, so switching re-indexes every document in the background. Search keeps using the current index until the re-index finishes.</p>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {Object.entries(emb.data.options).map(([k, o]: any) => {
              const isActive = active?.provider === k;
              return (
                <div key={k} className={cx("flex flex-col gap-3 rounded border p-6", isActive ? "border-black" : "border-border")}>
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <h3 className="text-h6">{k === "local" ? "Local model" : "Voyage AI"}</h3>
                      <p className="text-sm text-muted">{k === "local" ? "Runs on this server" : "External service"}</p>
                    </div>
                    {isActive ? <Badge tone="success">In use</Badge> : null}
                  </div>
                  <dl className="grid grid-cols-2 gap-2 rounded bg-offwhite p-3 text-sm">
                    <div><dt className="text-muted">Model</dt><dd className="font-semibold">{o.model_name}</dd></div>
                    <div><dt className="text-muted">Dimensions</dt><dd className="font-semibold">{o.dimension}</dd></div>
                  </dl>
                  <p className="text-sm text-muted">{k === "local" ? "Document text never leaves the server and no extra account is needed." : "Needs a Voyage AI key in API keys. Document text is sent to Voyage AI for embedding."}</p>
                  {!isActive && <div><Button onClick={() => confirm(`Switch to ${o.model_name} and re-index every document?`) &&
                    api.post("/admin/ai/embedding/switch", { provider: k, confirm: true }).then(emb.reload).catch((e) => setMsg({ tone: "error", text: e.message }))}>Switch and re-index</Button></div>}
                </div>
              );
            })}
          </div>
          {emb.data.reindex_job && ["Queued", "Processing"].includes(emb.data.reindex_job.status) && (
            <div className="text-sm">Re-index in progress: {emb.data.reindex_job.message}<Progress value={emb.data.reindex_job.progress} /></div>
          )}
        </>
      )}

      <Drawer open={!!configure} title={configure?.label || ""} subtitle={configure ? AGENT_INFO[configure.agent_key] : ""} onClose={() => setConfigure(null)}
        footer={<><Button variant="ghost" onClick={() => setConfigure(null)}>Cancel</Button><Button variant="primary" loading={saving} onClick={saveAgent}>Save changes</Button></>}>
        {configure && <div className="flex flex-col gap-6">
          <section className="flex flex-col gap-3">
            <h3 className="text-h6">Model</h3>
            <Field label="Model" hint="Any available model from the Models list can be used.">
              <Select value={configure.model_id} onChange={(e) => setConfigure({ ...configure, model_id: e.target.value })}
                options={modelOpts.some((m) => m.value === configure.model_id) ? modelOpts : [{ value: configure.model_id, label: configure.model_id }, ...modelOpts]} />
            </Field>
            {!hasKey(providerOf(configure.model_id)) && <Alert tone="warning">No {PROVIDER_LABELS[providerOf(configure.model_id)]} key is saved. Add it in API keys, or this agent will fail.</Alert>}
            {providerOf(configure.model_id) === "anthropic" ? (
              <Field label="Effort" hint={EFFORT_INFO[configure.effort]}>
                <Select value={configure.effort} onChange={(e) => setConfigure({ ...configure, effort: e.target.value })}
                  options={Object.keys(EFFORT_INFO).map((k) => ({ value: k, label: cap(k) }))} />
              </Field>
            ) : <p className="text-sm text-muted">Effort applies to Claude models only.</p>}
          </section>
          <section className="flex flex-col gap-1">
            <h3 className="text-h6">Limits</h3>
            <SettingRow title="Maximum output" help="Raise it if long answers are cut off.">
              <NumberInput value={configure.max_output_tokens} unit="tokens" min={256} max={128000} step={1000} onChange={(v) => setConfigure({ ...configure, max_output_tokens: v })} />
            </SettingRow>
            <SettingRow title="Time limit" help="Slower calls are stopped and retried.">
              <NumberInput value={configure.timeout_seconds} unit="sec" min={10} max={3600} onChange={(v) => setConfigure({ ...configure, timeout_seconds: v })} />
            </SettingRow>
            <SettingRow title="Retries" help="After a temporary error such as a rate limit.">
              <NumberInput value={configure.max_retries} min={0} max={5} onChange={(v) => setConfigure({ ...configure, max_retries: v })} />
            </SettingRow>
          </section>
        </div>}
      </Drawer>

      <Drawer open={!!modelEdit} title={modelEdit?.isNew ? "Add model" : modelEdit?.label || ""} subtitle={modelEdit?.isNew ? "Make a model from any supported provider available to agents." : modelEdit?.model_id}
        onClose={() => setModelEdit(null)}
        footer={<><Button variant="ghost" onClick={() => setModelEdit(null)}>Cancel</Button>
          <Button variant="primary" loading={saving} disabled={!modelEdit?.model_id || !modelEdit?.label} onClick={saveModel}>Save model</Button></>}>
        {modelEdit && <div className="flex flex-col gap-4">
          <Field label="Provider"><Select value={modelEdit.provider || "anthropic"} disabled={!modelEdit.isNew}
            onChange={(e) => setModelEdit({ ...modelEdit, provider: e.target.value })}
            options={Object.entries(PROVIDER_LABELS).map(([value, l]) => ({ value, label: l }))} /></Field>
          {!hasKey(modelEdit.provider || "anthropic") && <Alert tone="warning">No {PROVIDER_LABELS[modelEdit.provider || "anthropic"]} key is saved yet. Add it in API keys.</Alert>}
          <Field label={modelEdit.provider === "azure_openai" ? "Deployment name" : "Model ID"} hint={`Exactly as the provider names it: ${MODEL_ID_HINTS[modelEdit.provider || "anthropic"]}.`}>
            <Input value={modelEdit.model_id} disabled={!modelEdit.isNew} onChange={(e) => setModelEdit({ ...modelEdit, model_id: e.target.value })} /></Field>
          {modelEdit.provider === "azure_openai" && <Field label="Resource endpoint" hint="For example https://myresource.openai.azure.com">
            <Input value={modelEdit.endpoint || ""} onChange={(e) => setModelEdit({ ...modelEdit, endpoint: e.target.value })} /></Field>}
          <Field label="Display name" hint="Shown to administrators when choosing a model."><Input value={modelEdit.label} onChange={(e) => setModelEdit({ ...modelEdit, label: e.target.value })} /></Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Input price" hint="USD per 1M tokens"><Input type="number" step="any" value={modelEdit.input_per_mtok} onChange={(e) => setModelEdit({ ...modelEdit, input_per_mtok: e.target.value })} /></Field>
            <Field label="Output price" hint="USD per 1M tokens"><Input type="number" step="any" value={modelEdit.output_per_mtok} onChange={(e) => setModelEdit({ ...modelEdit, output_per_mtok: e.target.value })} /></Field>
          </div>
        </div>}
      </Drawer>

      <Modal open={bulkOpen} title="Change model for all agents" onClose={() => setBulkOpen(false)}>
        <div className="flex flex-col gap-4">
          <p className="text-sm text-muted">Every agent ({agents.data.length}) will use the selected model. Effort and limits stay as they are.</p>
          <Field label="Model"><Select value={bulkModel} onChange={(e) => setBulkModel(e.target.value)} options={[{ value: "", label: "Select a model" }, ...modelOpts]} /></Field>
          {bulkModel && !hasKey(providerOf(bulkModel)) && <Alert tone="warning">No {PROVIDER_LABELS[providerOf(bulkModel)]} key is saved.</Alert>}
          <div className="flex justify-end gap-2"><Button variant="ghost" onClick={() => setBulkOpen(false)}>Cancel</Button>
            <Button variant="primary" disabled={!bulkModel} loading={saving} onClick={applyAll}>Apply to all agents</Button></div>
        </div>
      </Modal>
    </div>
  );
}


function keyStatus(k: any): { tone: "success" | "warning" | "error" | "neutral" | "info"; text: string } {
  if (k.source === "none") return { tone: "neutral", text: "Not configured" };
  if (k.last_test_ok === false) return { tone: "error", text: "Test failed" };
  if (k.last_test_ok === true) return { tone: "success", text: "Connected" };
  return k.testable ? { tone: "warning", text: "Not tested" } : { tone: "info", text: "Saved" };
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
      setMsg({ tone: "success", text: `${label || edit.label || edit.provider} key saved and encrypted.` });
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
  const open = (k: any) => { setEdit(k); setValue(""); setLabel(k.custom ? k.label : ""); };
  if (!data) return <Spinner />;
  const primary = data.filter((k) => k.testable);
  const others = data.filter((k) => !k.testable);

  const actions = (k: any) => (
    <div className="flex flex-wrap gap-2">
      <Button variant={k.masked ? "secondary" : "primary"} onClick={() => open(k)}>{k.masked ? "Replace key" : "Add key"}</Button>
      {k.testable && k.source !== "none" && <Button loading={busy === k.provider} onClick={() => test(k.provider)}>Test connection</Button>}
      {k.masked && <Button variant="ghost" onClick={() => confirm(`Remove the stored ${k.label} key?`) && api.del(`/admin/api-keys/${k.provider}`).then(reload)}>Remove</Button>}
    </div>
  );

  return (
    <div className="flex flex-col gap-8">
      {msg && <Alert tone={msg.tone}>{msg.text}</Alert>}
      <section>
        <h3 className="mb-1 text-h6">Used by the platform</h3>
        <p className="mb-4 text-sm text-muted">Keys are encrypted before they are saved and are never shown again; only the last four characters are displayed. A key saved here replaces the one in the server&apos;s configuration file and applies immediately.</p>
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          {primary.map((k) => {
            const s = keyStatus(k);
            return (
              <article key={k.provider} className="flex flex-col gap-4 rounded border border-border p-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-start gap-3">
                    <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded bg-offwhite"><KeyRound size={24} /></span>
                    <div><h4 className="text-h6">{k.label}</h4><p className="text-sm text-muted">{k.used_for}</p></div>
                  </div>
                  <Badge tone={s.tone}>{s.text}</Badge>
                </div>
                <dl className="grid grid-cols-2 gap-4 rounded bg-offwhite p-3 text-sm">
                  <div><dt className="text-muted">Key</dt><dd className="font-semibold">{k.masked ? `••••••••${k.masked.replace("…", "")}` : "—"}</dd></div>
                  <div><dt className="text-muted">Stored in</dt><dd className="font-semibold">{k.source === "database" ? "Database (encrypted)" : k.source === "environment" ? "Server configuration file" : "—"}</dd></div>
                  <div><dt className="text-muted">Last tested</dt><dd className="font-semibold">{k.last_tested_at ? fmtDate(k.last_tested_at, true) : "Never"}</dd></div>
                  <div><dt className="text-muted">Updated</dt><dd className="font-semibold">{k.updated_at ? fmtDate(k.updated_at, true) : "—"}</dd></div>
                </dl>
                {k.last_test_ok === false && k.last_test_message && <p className="text-sm text-error">{k.last_test_message}</p>}
                {actions(k)}
              </article>
            );
          })}
        </div>
      </section>
      <section>
        <div className="mb-4 flex items-end justify-between gap-4">
          <div><h3 className="mb-1 text-h6">Other providers</h3><p className="text-sm text-muted">Stored for future use. No feature uses these keys yet.</p></div>
          <Button onClick={() => { setEdit({ provider: "", label: "", custom: true, isNew: true }); setValue(""); setLabel(""); }}><Plus size={16} /> Add provider</Button>
        </div>
        <ul className="rounded border border-border">
          {others.map((k) => {
            const s = keyStatus(k);
            return (
              <li key={k.provider} className="flex flex-col gap-3 border-b border-lightborder px-4 py-3 last:border-b-0 md:flex-row md:items-center md:justify-between">
                <div className="flex items-center gap-3">
                  <KeyRound size={20} className="text-muted" />
                  <div><div className="font-semibold">{k.label}</div><div className="text-sm text-muted">{k.masked ? `Key ending ${k.masked.replace("…", "")}` : "No key saved"}</div></div>
                </div>
                <div className="flex items-center gap-4"><Badge tone={s.tone}>{s.text}</Badge>{actions(k)}</div>
              </li>
            );
          })}
        </ul>
      </section>
      <Modal open={!!edit} title={edit?.isNew ? "Add a provider key" : `${edit?.masked ? "Replace" : "Add"} ${edit?.label} key`} onClose={() => setEdit(null)}>
        {edit && <div className="flex flex-col gap-4">
          {edit.isNew && <Field label="Provider ID" hint="Lower-case letters, digits and underscores, for example mistral">
            <Input value={edit.provider} onChange={(e) => setEdit({ ...edit, provider: e.target.value.toLowerCase() })} /></Field>}
          {edit.custom && <Field label="Display name"><Input value={label} onChange={(e) => setLabel(e.target.value)} /></Field>}
          <Field label="API key" hint={edit.masked ? "The current key is replaced when you save." : "Paste the key exactly as the provider shows it."}>
            <Input type="password" autoComplete="off" value={value} onChange={(e) => setValue(e.target.value)} placeholder="Paste the key" />
          </Field>
          <div className="flex justify-end gap-2"><Button variant="ghost" onClick={() => setEdit(null)}>Cancel</Button>
            <Button variant="primary" disabled={!value.trim() || !edit.provider} onClick={save}>Save encrypted</Button></div>
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
              <label className={buttonClass("secondary")}>
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

const PRESETS = [
  { key: "month", label: "This month" }, { key: "30", label: "Last 30 days" }, { key: "90", label: "Last 90 days" }, { key: "all", label: "All time" },
];
const iso = (d: Date) => d.toISOString().slice(0, 10);
function presetRange(key: string): { start?: string; end?: string } {
  const now = new Date();
  if (key === "month") return { start: iso(new Date(now.getFullYear(), now.getMonth(), 1)), end: iso(now) };
  if (key === "30" || key === "90") return { start: iso(new Date(now.getTime() - (Number(key) - 1) * 86400000)), end: iso(now) };
  return {};
}
const compact = (n: number) => n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e4 ? `${Math.round(n / 1e3)}k` : n >= 1e3 ? `${(n / 1e3).toFixed(1)}k` : String(n);
const humanize = (k: string) => k ? cap(k.replace(/_/g, " ")) : "System";
const fmtDay = (d: string) => new Date(`${d}T00:00:00`).toLocaleDateString("en-GB", { day: "numeric", month: "short" });

function Usage() {
  const { can } = useSession();
  const [preset, setPreset] = useState("month");
  const [dims, setDims] = useState({ module: "", agent: "", user_id: "" });
  const [breakdown, setBreakdown] = useState<"by_agent" | "by_user" | "by_module" | "by_model">("by_agent");
  const [showAll, setShowAll] = useState(false);
  const [budgetOpen, setBudgetOpen] = useState(false);
  const range = presetRange(preset);
  const qs = new URLSearchParams(Object.entries({ ...range, ...dims }).filter(([, v]) => v) as [string, string][]).toString();
  const { data, reload } = useApi<any>(`/admin/usage?${qs}`, [qs]);
  if (!data) return <Spinner />;

  const t = data.totals;
  const rows: any[] = data[breakdown];
  const maxCost = Math.max(...rows.map((r) => r.cost), 0);
  const filtered = Object.values(dims).some(Boolean);
  const recent = showAll ? data.recent : data.recent.slice(0, 15);
  const labelFor = (r: any) => breakdown === "by_agent" ? humanize(r.key) : breakdown === "by_module" ? (MODULE_NAMES[r.key] || humanize(r.key)) : (r.key || "System");

  return (
    <div className="flex flex-col gap-8">
      {/* filters: one row above everything they control */}
      <div className="flex flex-wrap items-center gap-3">
        <Segmented items={PRESETS} active={preset} onChange={setPreset} />
        <Select className="w-40" value={dims.module} onChange={(e) => setDims({ ...dims, module: e.target.value })}
          options={[{ value: "", label: "All modules" }, ...Object.entries(MODULE_NAMES).map(([value, label]) => ({ value, label })), { value: "knowledge", label: "Knowledge Hub" }]} />
        <Select className="w-48" value={dims.agent} onChange={(e) => setDims({ ...dims, agent: e.target.value })}
          options={[{ value: "", label: "All agents" }, ...Object.keys(AGENT_INFO).map((k) => ({ value: k, label: humanize(k) }))]} />
        <Select className="w-40" value={dims.user_id} onChange={(e) => setDims({ ...dims, user_id: e.target.value })}
          options={[{ value: "", label: "All users" }, ...data.by_user.filter((u: any) => u.id).map((u: any) => ({ value: String(u.id), label: u.key }))]} />
        {filtered && <Button variant="ghost" onClick={() => setDims({ module: "", agent: "", user_id: "" })}>Clear filters</Button>}
      </div>

      {/* headline numbers */}
      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <StatTile label="Estimated cost" value={money(t.cost)} />
        <StatTile label="AI calls" value={t.calls.toLocaleString()} />
        <StatTile label="Input tokens" value={compact(t.input_tokens)} />
        <StatTile label="Output tokens" value={compact(t.output_tokens)} />
      </div>

      <div className="grid grid-cols-1 gap-8 xl:grid-cols-[1fr_360px]">
        <DailyCost days={data.by_day} range={range} />
        <BudgetMeter budget={data.budget} canEdit={can("admin.budget")} onEdit={() => setBudgetOpen(true)} />
      </div>

      {/* breakdown */}
      <section>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-sm font-semibold">Cost breakdown</h3>
          <Segmented active={breakdown} onChange={(k) => setBreakdown(k as any)} items={[
            { key: "by_agent", label: "Agent" }, { key: "by_user", label: "User" }, { key: "by_module", label: "Module" }, { key: "by_model", label: "Model" },
          ]} />
        </div>
        {rows.length === 0 ? <p className="border-t border-lightborder py-6 text-center text-sm text-muted">No AI usage in this period.</p> : (
          <table className="w-full text-sm">
            <thead><tr className="border-b border-lightborder text-left text-mono-600">
              <th className="py-2 font-semibold">Name</th><th className="py-2 text-right font-semibold">Calls</th>
              <th className="py-2 text-right font-semibold">Tokens in / out</th><th className="py-2 text-right font-semibold">Cost</th>
              <th className="w-1/3 py-2 pl-6 font-semibold">Share of cost</th>
            </tr></thead>
            <tbody>
              {rows.map((r, i) => {
                const share = t.cost ? (100 * r.cost) / t.cost : 0;
                return (
                  <tr key={i} className="border-b border-lightborder">
                    <td className="py-2">{labelFor(r)}</td>
                    <td className="py-2 text-right tabular-nums">{r.calls.toLocaleString()}</td>
                    <td className="py-2 text-right tabular-nums text-muted">{compact(r.input_tokens)} / {compact(r.output_tokens)}</td>
                    <td className="py-2 text-right tabular-nums">{money(r.cost)}</td>
                    <td className="py-2 pl-6">
                      <div className="flex items-center gap-3" title={`${labelFor(r)}: ${money(r.cost)} (${share.toFixed(1)}%)`}>
                        <div className="h-2 flex-1 rounded-full bg-mono-100">
                          <div className="h-2 rounded-full bg-mono-800" style={{ width: `${maxCost ? Math.max(2, (100 * r.cost) / maxCost) : 0}%` }} />
                        </div>
                        <span className="w-12 text-right tabular-nums text-muted">{share.toFixed(0)}%</span>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>

      {/* log */}
      <section>
        <div className="mb-3 flex items-center justify-between gap-3">
          <h3 className="text-sm font-semibold">Recent calls</h3>
          <span className="text-sm text-muted">Prompts and answers are never stored, only these figures.</span>
        </div>
        {data.recent.length === 0 ? <p className="border-t border-lightborder py-6 text-center text-sm text-muted">No calls yet.</p> : (
          <>
            <table className="w-full text-sm">
              <thead><tr className="border-b border-lightborder text-left text-mono-600">
                <th className="py-2 font-semibold">When</th><th className="py-2 font-semibold">User</th><th className="py-2 font-semibold">Agent</th>
                <th className="py-2 font-semibold">Model</th><th className="py-2 text-right font-semibold">Tokens</th>
                <th className="py-2 text-right font-semibold">Time</th><th className="py-2 pl-4 font-semibold">Result</th><th className="py-2 text-right font-semibold">Cost</th>
              </tr></thead>
              <tbody>
                {recent.map((r: any, i: number) => {
                  const ok = ["ok", "end_turn", "stop_sequence"].includes(r.status);
                  return (
                    <tr key={i} className="border-b border-lightborder">
                      <td className="whitespace-nowrap py-2 text-muted">{fmtDate(r.at, true)}</td>
                      <td className="py-2">{r.user}</td>
                      <td className="py-2">{humanize(r.agent)}</td>
                      <td className="py-2 text-muted">{r.model}</td>
                      <td className="whitespace-nowrap py-2 text-right tabular-nums text-muted">{compact(r.input_tokens)} / {compact(r.output_tokens)}</td>
                      <td className="py-2 text-right tabular-nums text-muted">{(r.duration_ms / 1000).toFixed(1)}s</td>
                      <td className="py-2 pl-4">{ok ? <span className="text-muted">Completed</span> : <Badge tone="error">{humanize(r.status)}</Badge>}</td>
                      <td className="py-2 text-right tabular-nums">{money(r.cost)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {data.recent.length > 15 && <div className="mt-3"><Button variant="ghost" onClick={() => setShowAll(!showAll)}>{showAll ? "Show fewer" : `Show all ${data.recent.length}`}</Button></div>}
          </>
        )}
      </section>

      <BudgetDrawer open={budgetOpen} budget={data.budget} onClose={() => setBudgetOpen(false)} onSaved={() => { setBudgetOpen(false); reload(); }} />
    </div>
  );
}

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-lightborder px-4 py-3">
      <div className="text-sm text-muted">{label}</div>
      <div className="mt-1 text-h4 tabular-nums">{value}</div>
    </div>
  );
}

/** Single-series daily cost bars; the hovered bar takes the accent and its values show in the caption. */
function DailyCost({ days, range }: { days: any[]; range: { start?: string; end?: string } }) {
  const [hover, setHover] = useState<number | null>(null);
  const series = useMemo(() => {
    const byDay = Object.fromEntries(days.map((d) => [d.day, d]));
    if (!range.start || !range.end) return days;
    const out = [];
    for (let d = new Date(`${range.start}T00:00:00`); iso(d) <= range.end; d = new Date(d.getTime() + 86400000)) {
      const k = iso(d);
      out.push(byDay[k] || { day: k, calls: 0, cost: 0 });
    }
    return out;
  }, [days, range.start, range.end]);
  const max = Math.max(...series.map((d) => d.cost), 0);
  const total = series.reduce((s, d) => s + d.cost, 0);
  const h = series[hover ?? -1];
  const W = 100, H = 40, gap = series.length > 60 ? 0.15 : 0.35;
  const bw = series.length ? W / series.length : W;
  return (
    <section>
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-semibold">Cost per day</h3>
        <span className="text-sm tabular-nums text-muted">
          {h ? `${fmtDay(h.day)} · ${money(h.cost)} · ${h.calls} ${h.calls === 1 ? "call" : "calls"}` : series.length ? `${fmtDay(series[0].day)} – ${fmtDay(series[series.length - 1].day)} · ${money(total)}` : ""}
        </span>
      </div>
      {series.length === 0 || max === 0 ? (
        <div className="flex h-40 items-center justify-center rounded border border-dashed border-border text-sm text-muted">No AI usage in this period.</div>
      ) : (
        <div className="relative">
          <span className="absolute left-0 top-0 text-sm tabular-nums text-muted">{money(max)}</span>
          <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="h-40 w-full" role="img"
            aria-label={`Daily AI cost, highest ${money(max)}`} onMouseLeave={() => setHover(null)}>
            <line x1="0" x2={W} y1={H - 0.1} y2={H - 0.1} stroke="var(--border-gray)" strokeWidth="0.2" vectorEffect="non-scaling-stroke" />
            {series.map((d, i) => {
              const bh = max ? Math.max(d.cost > 0 ? 0.6 : 0, ((H - 6) * d.cost) / max) : 0;
              return (
                <g key={d.day} onMouseEnter={() => setHover(i)}>
                  <rect x={i * bw} y="0" width={bw} height={H} fill="transparent" />
                  <rect x={i * bw + (bw * gap) / 2} y={H - bh} width={bw * (1 - gap)} height={bh} rx="0.4"
                    fill={hover === i ? "var(--accent)" : "var(--mono-800)"}>
                    <title>{`${fmtDay(d.day)}: ${money(d.cost)}, ${d.calls} calls`}</title>
                  </rect>
                </g>
              );
            })}
          </svg>
          <div className="mt-1 flex justify-between text-sm text-muted"><span>{fmtDay(series[0].day)}</span><span>{fmtDay(series[series.length - 1].day)}</span></div>
        </div>
      )}
    </section>
  );
}

function BudgetMeter({ budget, canEdit, onEdit }: { budget: any; canEdit: boolean; onEdit: () => void }) {
  const month = new Date(`${budget.month}-01T00:00:00`).toLocaleDateString("en-GB", { month: "long", year: "numeric" });
  if (!budget.amount) {
    return (
      <section className="flex flex-col justify-between gap-4 rounded border border-lightborder p-4">
        <div>
          <h3 className="text-sm font-semibold">Monthly budget</h3>
          <p className="mt-1 text-sm text-muted">No budget is set for {month}. Spent so far: {money(budget.spent)}.</p>
        </div>
        {canEdit && <div><Button variant="primary" onClick={onEdit}>Set a budget</Button></div>}
      </section>
    );
  }
  const pct = (100 * budget.spent) / budget.amount;
  const thresholds: number[] = budget.thresholds || [];
  const crossed = thresholds.filter((x) => pct >= x);
  const tone = pct >= 100 ? "error" : crossed.length ? "warning" : "success";
  const fill = tone === "error" ? "bg-error" : tone === "warning" ? "bg-warning" : "bg-black";
  return (
    <section className="flex flex-col gap-4 rounded border border-lightborder p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold">Monthly budget</h3>
          <p className="text-sm text-muted">{month}</p>
        </div>
        {canEdit && <Button variant="ghost" onClick={onEdit}>Edit</Button>}
      </div>
      <div>
        <div className="flex items-baseline gap-2">
          <span className="text-h4 tabular-nums">{money(budget.spent)}</span>
          <span className="text-sm text-muted">of {money(budget.amount)}</span>
        </div>
        <div className="relative mt-3 h-2 rounded-full bg-mono-100" role="meter" aria-valuemin={0} aria-valuemax={budget.amount} aria-valuenow={budget.spent} aria-label="Budget used">
          <div className={cx("h-2 rounded-full", fill)} style={{ width: `${Math.min(100, pct)}%` }} />
          {thresholds.filter((x) => x < 100).map((x) => (
            <span key={x} className="absolute -top-1 h-4 w-px bg-mono-500" style={{ left: `${x}%` }} title={`Alert at ${x}%`} />
          ))}
        </div>
        <div className="mt-2 flex justify-between text-sm text-muted">
          <span>{pct.toFixed(0)}% used</span>
          <span>{budget.remaining >= 0 ? `${money(budget.remaining)} left` : `${money(-budget.remaining)} over`}</span>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2 border-t border-lightborder pt-3 text-sm text-muted">
        <StatusBadge status={tone === "error" ? "Failed" : tone === "warning" ? "Pending" : "Completed"} />
        <span>{tone === "error" ? "Budget reached" : tone === "warning" ? `Past the ${crossed[crossed.length - 1]}% alert` : "Within budget"}</span>
        <span className="ml-auto">Alerts at {thresholds.join("%, ")}%{budget.hard_stop ? " · hard stop on" : ""}</span>
      </div>
    </section>
  );
}

function BudgetDrawer({ open, budget, onClose, onSaved }: { open: boolean; budget: any; onClose: () => void; onSaved: () => void }) {
  const [amount, setAmount] = useState<number>(budget.amount || 0);
  const [thresholds, setThresholds] = useState<string[]>((budget.thresholds || [80, 100]).map(String));
  const [hardStop, setHardStop] = useState<boolean>(!!budget.hard_stop);
  const [err, setErr] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    if (open) { setAmount(budget.amount || 0); setThresholds((budget.thresholds || [80, 100]).map(String)); setHardStop(!!budget.hard_stop); setErr(""); }
  }, [open, budget]);
  async function save() {
    if (!amount || amount <= 0) return setErr("Enter a budget greater than zero");
    setSaving(true);
    try {
      await api.put("/admin/budget", { amount, thresholds: thresholds.map(Number).filter((n) => n > 0 && n <= 200), hard_stop: hardStop });
      onSaved();
    } catch (e) { setErr((e as Error).message); } finally { setSaving(false); }
  }
  return (
    <Drawer open={open} title="Monthly budget" subtitle="Spending is estimated from this application's own usage logs and the model prices."
      onClose={onClose} footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" loading={saving} onClick={save}>Save budget</Button></>}>
      <div className="flex flex-col gap-2">
        {err && <Alert tone="error">{err}</Alert>}
        <SettingRow title="Budget for this month" help="Shown against spend on the usage page.">
          <NumberInput value={amount} unit="USD" min={1} step={10} onChange={setAmount} />
        </SettingRow>
        <div className="border-b border-lightborder py-3">
          <div className="text-sm">Alert thresholds</div>
          <div className="mb-2 text-sm text-muted">Administrators are notified once when spend passes each percentage.</div>
          <TagInput values={thresholds} onChange={(v) => setThresholds([...v].sort((a, b) => Number(a) - Number(b)))} placeholder="e.g. 50"
            validate={(v) => /^\d{1,3}$/.test(v) && Number(v) > 0 && Number(v) <= 200 ? null : "Enter a percentage between 1 and 200"} />
        </div>
        <SettingRow title="Hard stop at 100%" help="Block new AI calls once the budget is used up.">
          <Toggle label="Hard stop" checked={hardStop} onChange={setHardStop} />
        </SettingRow>
      </div>
    </Drawer>
  );
}


type FieldDef = { key: string; title: string; help: string; kind: "number" | "bool"; unit?: string; min?: number; max?: number };
const SETTING_SECTIONS: { key: string; title: string; description: string; fields: FieldDef[] }[] = [
  { key: "session", title: "Sign-in and sessions", description: "How long people stay signed in and how failed sign-ins are handled.", fields: [
    { key: "hours", title: "Session length", help: "People are signed out after this long.", kind: "number", unit: "hours", min: 1, max: 168 },
    { key: "max_login_attempts", title: "Failed sign-in limit", help: "The account is locked after this many failed attempts in a row.", kind: "number", unit: "attempts", min: 3, max: 20 },
    { key: "lockout_minutes", title: "Lock-out period", help: "How long a locked account stays locked.", kind: "number", unit: "minutes", min: 1, max: 1440 },
  ] },
  { key: "password_policy", title: "Password policy", description: "Applies when users set or change their password.", fields: [
    { key: "min_length", title: "Minimum length", help: "Shortest password allowed.", kind: "number", unit: "characters", min: 8, max: 64 },
    { key: "require_upper", title: "Upper-case letter", help: "Require at least one A–Z.", kind: "bool" },
    { key: "require_lower", title: "Lower-case letter", help: "Require at least one a–z.", kind: "bool" },
    { key: "require_digit", title: "Digit", help: "Require at least one 0–9.", kind: "bool" },
    { key: "require_symbol", title: "Symbol", help: "Require at least one character such as ! or #.", kind: "bool" },
  ] },
  { key: "rfp_limits", title: "RFP processing", description: "Capacity and limits for RFP analysis jobs.", fields: [
    { key: "max_concurrent_jobs", title: "Concurrent RFP jobs", help: "RFP jobs that can run at the same time.", kind: "number", unit: "jobs", min: 1, max: 10 },
    { key: "max_queued_jobs", title: "Queue size", help: "New jobs are refused when this many are waiting.", kind: "number", unit: "jobs", min: 1, max: 200 },
    { key: "job_timeout_seconds", title: "Job time limit", help: "A job that runs longer than this is stopped.", kind: "number", unit: "seconds", min: 300, max: 86400 },
    { key: "max_retries", title: "Automatic retries", help: "Times a failed job is retried before it is marked Failed.", kind: "number", unit: "retries", min: 0, max: 5 },
    { key: "max_document_mb", title: "Maximum document size", help: "Largest single file accepted in a workspace.", kind: "number", unit: "MB", min: 1, max: 500 },
    { key: "max_documents_per_rfp", title: "Documents per workspace", help: "Most files one RFP workspace can hold.", kind: "number", unit: "files", min: 1, max: 200 },
  ] },
  { key: "retrieval", title: "Knowledge retrieval", description: "How documents are split and how many passages are given to the AI. Chunk changes apply to newly ingested documents.", fields: [
    { key: "top_k", title: "Passages per question", help: "Approved passages sent to the AI for each question.", kind: "number", unit: "passages", min: 1, max: 30 },
    { key: "chunk_chars", title: "Passage size", help: "Length of each stored passage.", kind: "number", unit: "characters", min: 300, max: 8000 },
    { key: "chunk_overlap", title: "Passage overlap", help: "Text repeated between neighbouring passages so nothing is cut mid-thought.", kind: "number", unit: "characters", min: 0, max: 1000 },
  ] },
];

function Settings() {
  const { data, reload } = useApi<any>("/admin/settings");
  if (!data) return <Spinner />;
  return (
    <div className="flex flex-col gap-6">
      {SETTING_SECTIONS.map((s) => <SettingsSection key={s.key} section={s} value={data[s.key]} onSaved={reload} />)}
      <DomainsSection value={data.url_fetch_allowed_domains || []} onSaved={reload} />
    </div>
  );
}

function SettingsSection({ section, value, onSaved }: { section: (typeof SETTING_SECTIONS)[number]; value: any; onSaved: () => void }) {
  const [draft, setDraft] = useState<any>(value);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");
  const [savedAt, setSavedAt] = useState("");
  useEffect(() => { setDraft(value); }, [value]);
  const dirty = JSON.stringify(draft) !== JSON.stringify(value);
  async function save() {
    setSaving(true); setErr("");
    try {
      for (const f of section.fields) {
        if (f.kind === "number" && (draft[f.key] < (f.min ?? -Infinity) || draft[f.key] > (f.max ?? Infinity))) {
          throw new Error(`${f.title} must be between ${f.min} and ${f.max}`);
        }
      }
      await api.put(`/admin/settings/${section.key}`, draft);
      setSavedAt(new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }));
      onSaved();
    } catch (e) { setErr((e as Error).message); } finally { setSaving(false); }
  }
  return (
    <Card title={section.title}>
      <p className="-mt-1 mb-2 text-sm text-muted">{section.description}</p>
      {err && <Alert tone="error">{err}</Alert>}
      {section.fields.map((f) => (
        <SettingRow key={f.key} title={f.title} help={f.help}>
          {f.kind === "bool"
            ? <Toggle label={f.title} checked={!!draft[f.key]} onChange={(v) => setDraft({ ...draft, [f.key]: v })} />
            : <NumberInput value={draft[f.key] ?? ""} unit={f.unit} min={f.min} max={f.max} onChange={(v) => setDraft({ ...draft, [f.key]: v })} />}
        </SettingRow>
      ))}
      <SaveBar dirty={dirty} saving={saving} savedAt={savedAt} onSave={save} onReset={() => { setDraft(value); setErr(""); }} />
    </Card>
  );
}

function DomainsSection({ value, onSaved }: { value: string[]; onSaved: () => void }) {
  const [draft, setDraft] = useState<string[]>(value);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");
  const [savedAt, setSavedAt] = useState("");
  useEffect(() => { setDraft(value); }, [value]);
  const dirty = JSON.stringify(draft) !== JSON.stringify(value);
  async function save() {
    setSaving(true); setErr("");
    try {
      await api.put("/admin/settings/url_fetch_allowed_domains", draft);
      setSavedAt(new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }));
      onSaved();
    } catch (e) { setErr((e as Error).message); } finally { setSaving(false); }
  }
  return (
    <Card title="Allowed websites for URL sources">
      <p className="-mt-1 mb-4 text-sm text-muted">The Knowledge Hub fetches web pages only from these domains and their sub-domains.</p>
      {err && <Alert tone="error">{err}</Alert>}
      <TagInput values={draft} onChange={setDraft} placeholder="e.g. docs.motadata.com"
        validate={(v) => /^(?!-)[a-z0-9-]+(\.[a-z0-9-]+)+$/.test(v) ? null : "Enter a domain name such as docs.motadata.com, without https://"} />
      <SaveBar dirty={dirty} saving={saving} savedAt={savedAt} onSave={save} onReset={() => { setDraft(value); setErr(""); }} />
    </Card>
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
