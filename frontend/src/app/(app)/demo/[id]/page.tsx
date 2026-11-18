"use client";
import { Download, Save, Sparkles } from "lucide-react";
import { use, useEffect, useState } from "react";
import { Alert, Badge, Button, Card, Field, Input, PageHeader, Progress, Select, Spinner, Textarea } from "@/components/ui";
import { api, download, fmtDate } from "@/lib/api";
import { useApi, useJobPoll } from "@/lib/hooks";
import { useSession } from "@/lib/session";

export default function DemoProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { can } = useSession();
  const [version, setVersion] = useState<number | null>(null);
  const p = useApi<any>(`/demo/projects/${id}${version ? `?version=${version}` : ""}`, [version]);
  const useCases = useApi<any[]>("/demo/use-cases");
  const templates = useApi<any[]>("/demo/templates");
  const [inputs, setInputs] = useState<any>(null);
  const [content, setContent] = useState<any>(null);
  const [msg, setMsg] = useState<{ tone: "error" | "success" | "info"; text: string } | null>(null);
  const running = p.data?.job && ["Queued", "Processing"].includes(p.data.job.status) ? p.data.job.id : null;
  const job = useJobPoll(running, () => { setVersion(null); p.reload(); });

  useEffect(() => {
    if (p.data) { setInputs(p.data.inputs || {}); setContent(p.data.script?.content || null); }
  }, [p.data]);
  if (!p.data || !inputs) return <Spinner />;
  const set = (k: string, v: any) => setInputs({ ...inputs, [k]: v });
  const flagged = new Set((p.data.script?.unverified_steps || []).map((f: any) => `${f.use_case}:${f.step}`));
  const act = async (fn: () => Promise<any>, ok: string) => {
    try { await fn(); setMsg({ tone: "success", text: ok }); p.reload(); } catch (e) { setMsg({ tone: "error", text: (e as Error).message }); }
  };
  const approved = (useCases.data || []).filter((u) => u.status === "Approved");
  const toggleList = (k: string, idv: string, on: boolean) => set(k, on ? [...(inputs[k] || []), idv] : (inputs[k] || []).filter((x: string) => x !== idv));
  const setUc = (i: number, k: string, v: any) => setContent({ ...content, use_cases: content.use_cases.map((u: any, j: number) => j === i ? { ...u, [k]: v } : u) });

  return (
    <>
      <PageHeader title={p.data.title} subtitle={p.data.current_version ? `Version ${p.data.script?.version} of ${p.data.current_version}` : "No script yet"}
        actions={<>
          {can("demo.edit") && <Button onClick={() => act(() => api.put(`/demo/projects/${id}`, { title: p.data.title, customer_id: p.data.customer_id, inputs }), "Inputs saved")}>Save inputs</Button>}
          {can("demo.create", "demo.edit") && <Button variant="primary" loading={!!running} onClick={() => act(async () => {
            await api.put(`/demo/projects/${id}`, { title: p.data.title, customer_id: p.data.customer_id, inputs });
            await api.post(`/demo/projects/${id}/generate`);
          }, "Generating the demo script")}><Sparkles size={16} /> Generate script</Button>}
        </>} />
      {msg && <div className="mb-4"><Alert tone={msg.tone}>{msg.text}</Alert></div>}
      {running && job && <div className="mb-4"><Card title="Generating"><div className="mb-2 text-sm">{job.message}</div><Progress value={job.progress} /></Card></div>}
      {p.data.job?.status === "Failed" && <div className="mb-4"><Alert tone="error">{p.data.job.error}</Alert></div>}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[380px_1fr]">
        <div className="flex flex-col gap-4">
          <Card title="Inputs">
            <div className="flex flex-col gap-3">
              <Field label="Products"><div className="flex gap-4">{["ObserveOps", "ServiceOps"].map((x) => (
                <label key={x} className="flex items-center gap-1 text-sm"><input type="checkbox" checked={(inputs.products || []).includes(x)} onChange={(e) => toggleList("products", x, e.target.checked)} />{x}</label>))}</div></Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Duration (minutes)"><Input type="number" value={inputs.duration_minutes || 45} onChange={(e) => set("duration_minutes", Number(e.target.value))} /></Field>
                <Field label="Technical depth"><Select value={inputs.technical_depth || "Medium"} onChange={(e) => set("technical_depth", e.target.value)} options={["Low", "Medium", "High"]} /></Field>
              </div>
              <Field label="Audience"><Input value={inputs.audience || ""} onChange={(e) => set("audience", e.target.value)} /></Field>
              <Field label="Pain points and requirements" hint="Leave blank to use the customer context."><Textarea rows={3} value={inputs.pain_points || ""} onChange={(e) => set("pain_points", e.target.value)} /></Field>
              <Field label="Special requirements"><Textarea rows={2} value={inputs.special_requirements || ""} onChange={(e) => set("special_requirements", e.target.value)} /></Field>
              <Field label="Use cases (include / exclude)">
                <div className="flex max-h-64 flex-col gap-1 overflow-y-auto">
                  {approved.map((u) => (
                    <div key={u.id} className="flex items-center justify-between gap-2 text-sm">
                      <span>{u.name}</span>
                      <Select className="w-32" value={(inputs.include_use_cases || []).includes(String(u.id)) ? "include" : (inputs.exclude_use_cases || []).includes(String(u.id)) ? "exclude" : "auto"}
                        onChange={(e) => {
                          const idv = String(u.id);
                          setInputs({ ...inputs, include_use_cases: (inputs.include_use_cases || []).filter((x: string) => x !== idv).concat(e.target.value === "include" ? [idv] : []),
                            exclude_use_cases: (inputs.exclude_use_cases || []).filter((x: string) => x !== idv).concat(e.target.value === "exclude" ? [idv] : []) });
                        }} options={["auto", "include", "exclude"]} />
                    </div>
                  ))}
                  {!approved.length && <span className="text-sm text-muted">No approved use cases yet.</span>}
                </div>
              </Field>
            </div>
          </Card>
          {(templates.data || []).length > 0 && can("demo.edit") && (
            <Card title="Start from a winning script">
              <div className="flex flex-col gap-2">{templates.data!.map((t) => (
                <Button key={t.id} variant="ghost" onClick={() => act(() => api.post(`/demo/projects/${id}/from-template/${t.id}`), "Template loaded as a new version")}>{t.name} {t.industry && `(${t.industry})`}</Button>))}</div>
            </Card>
          )}
          {p.data.versions.length > 0 && (
            <Card title="Versions"><div className="flex flex-wrap gap-2">{p.data.versions.map((v: number) => (
              <Button key={v} variant={v === p.data.script?.version ? "primary" : "secondary"} onClick={() => setVersion(v)}>v{v}</Button>))}</div></Card>
          )}
        </div>
        <div className="flex min-w-0 flex-col gap-4">
          {!content ? <Alert tone="info">Generate a script to start. Product steps come from approved use cases only.</Alert> : (
            <>
              {p.data.script.unverified_steps.length > 0 && <Alert tone="warning">{p.data.script.unverified_steps.length} navigation step(s) are not in the use-case library or approved documentation. Validate them manually before the demo.</Alert>}
              <Card title="Opening">
                <Textarea rows={3} value={content.opening.customer_context} onChange={(e) => setContent({ ...content, opening: { ...content.opening, customer_context: e.target.value } })} />
                <ul className="mt-2 list-disc pl-5 text-sm">{content.opening.challenges.map((c: string, i: number) => <li key={i}>{c}</li>)}</ul>
              </Card>
              <Card title="The end result first">
                <Textarea rows={2} value={content.end_result_first.outcome} onChange={(e) => setContent({ ...content, end_result_first: { ...content.end_result_first, outcome: e.target.value } })} />
                <p className="mt-2 text-sm">{content.end_result_first.how_to_show}</p>
              </Card>
              <Card title="Agenda"><ol className="list-decimal pl-5 text-sm">{content.agenda.map((a: any, i: number) => <li key={i}><b>{a.title}</b> · {a.pain} · {a.minutes} min</li>)}</ol></Card>
              {content.use_cases.map((u: any, i: number) => (
                <Card key={i} title={u.title}>
                  <div className="flex flex-col gap-3 text-sm">
                    <div><b>Pain:</b> {u.pain}</div>
                    <div><b>Navigation and screens</b>
                      <ol className="mt-1 list-decimal pl-5">{u.navigation.map((s: string, j: number) => (
                        <li key={j}>{s} {flagged.has(`${i}:${j}`) && <Badge tone="warning">Validate</Badge>}</li>))}</ol></div>
                    <Field label="What to show"><Textarea rows={2} value={u.what_to_show} onChange={(e) => setUc(i, "what_to_show", e.target.value)} /></Field>
                    <Field label="Value statement"><Textarea rows={2} value={u.value_statement} onChange={(e) => setUc(i, "value_statement", e.target.value)} /></Field>
                    {u.differentiator && <div><b>Differentiator</b> <Badge tone={u.differentiator_label === "verified" ? "success" : "warning"}>{u.differentiator_label || "unsourced"}</Badge><div>{u.differentiator}</div></div>}
                    <div><b>Check-in:</b> {u.check_in_question}</div>
                    {u.transition && <div className="text-muted">Transition: {u.transition}</div>}
                  </div>
                </Card>
              ))}
              <Card title="Objections"><ul className="flex flex-col gap-2 text-sm">{content.objections.map((o: any, i: number) => <li key={i}><b>{o.objection}</b><div>{o.answer}</div></li>)}</ul></Card>
              <Card title="Closing and next steps"><p className="text-sm">{content.closing.summary}</p><ul className="mt-2 list-disc pl-5 text-sm">{content.closing.next_steps.map((s: string, i: number) => <li key={i}>{s}</li>)}</ul></Card>
              <Card title="Pre-demo checklist"><ul className="list-disc pl-5 text-sm">{content.checklist.map((s: string, i: number) => <li key={i}>{s}</li>)}</ul></Card>
              <div className="flex flex-wrap gap-2">
                {can("demo.edit") && <Button variant="primary" onClick={() => act(() => api.post(`/demo/projects/${id}/versions`, { content }).then(() => setVersion(null)), "Saved as a new version")}><Save size={16} /> Save as new version</Button>}
                {can("demo.export") && <><Button onClick={() => download(`/demo/projects/${id}/export?fmt=docx&version=${p.data.script.version}`)}><Download size={16} /> Word</Button>
                  <Button onClick={() => download(`/demo/projects/${id}/export?fmt=pdf&version=${p.data.script.version}`)}><Download size={16} /> PDF</Button></>}
                {can("demo.edit") && <Select className="w-40" value={p.data.outcome || ""} onChange={(e) => act(() => api.post(`/demo/projects/${id}/outcome`, { outcome: e.target.value }), "Outcome recorded")}
                  options={[{ value: "", label: "Outcome: open" }, { value: "Won", label: "Won" }, { value: "Lost", label: "Lost" }]} />}
                {can("demo.manage_templates") && p.data.outcome === "Won" && <Button onClick={() => act(() => api.post(`/demo/projects/${id}/save-template`, { name: p.data.title }), "Saved as a reusable template")}>Save as template</Button>}
              </div>
              <p className="text-sm text-muted">Script saved {fmtDate(p.data.script.at, true)} ({p.data.script.origin}).</p>
            </>
          )}
        </div>
      </div>
    </>
  );
}
