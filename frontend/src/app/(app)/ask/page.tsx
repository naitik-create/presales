"use client";
import { Plus, Send, ThumbsDown, ThumbsUp, Trash2 } from "lucide-react";
import { FormEvent, useEffect, useRef, useState } from "react";
import { Alert, Badge, Button, Card, Input, PageHeader, Select, Spinner, StatusBadge, Table, Tabs } from "@/components/ui";
import { api, fmtDate } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useSession } from "@/lib/session";

export default function AskPage() {
  const { can } = useSession();
  const [tab, setTab] = useState("chat");
  const tabs = [{ key: "chat", label: "Ask" }, ...(can("ask.view_gaps") ? [{ key: "gaps", label: "Gap log" }] : [])];
  return (
    <>
      <PageHeader title="Ask Motadata" subtitle="Answers come only from approved Knowledge Hub sources, with citations." />
      <Tabs tabs={tabs} active={tab} onChange={setTab} />
      {tab === "chat" ? <Chat /> : <Gaps />}
    </>
  );
}

function Chat() {
  const convs = useApi<any[]>("/ask/conversations");
  const [cid, setCid] = useState<number | null>(null);
  const [messages, setMessages] = useState<any[]>([]);
  const [q, setQ] = useState("");
  const [product, setProduct] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!cid) { setMessages([]); return; }
    api.get(`/ask/conversations/${cid}`).then((c) => setMessages(c.messages));
  }, [cid]);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  async function ask(e: FormEvent) {
    e.preventDefault();
    if (!q.trim()) return;
    const question = q;
    setQ("");
    setBusy(true);
    setError("");
    setMessages((m) => [...m, { id: `tmp`, role: "user", content: question }]);
    try {
      const r = await api.post("/ask", { question, conversation_id: cid, product: product || null });
      if (!cid) { setCid(r.conversation_id); convs.reload(); }
      setMessages((m) => [...m.filter((x) => x.id !== "tmp"), { id: `u${Date.now()}`, role: "user", content: question }, r.message]);
    } catch (err) {
      setError((err as Error).message);
      setMessages((m) => m.filter((x) => x.id !== "tmp"));
      setQ(question);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[256px_1fr]">
      <div className="flex flex-col gap-2">
        <Button onClick={() => setCid(null)}><Plus size={16} /> New conversation</Button>
        {(convs.data || []).map((c) => (
          <div key={c.id} className={`flex items-center justify-between rounded px-3 py-2 text-sm ${c.id === cid ? "bg-offwhite font-semibold" : "hover:bg-offwhite"}`}>
            <button className="min-w-0 flex-1 truncate text-left" onClick={() => setCid(c.id)}>{c.title}</button>
            <button aria-label="Delete conversation" onClick={() => api.del(`/ask/conversations/${c.id}`).then(() => { if (cid === c.id) setCid(null); convs.reload(); })}><Trash2 size={16} /></button>
          </div>
        ))}
      </div>
      <div className="flex min-h-[60vh] flex-col rounded border border-border">
        <div className="flex-1 overflow-y-auto p-4">
          {messages.length === 0 && <p className="text-sm text-muted">Ask about ObserveOps or ServiceOps capabilities, architecture, prerequisites, integrations, licensing or sizing.</p>}
          <div className="flex flex-col gap-4">
            {messages.map((m) => m.role === "user"
              ? <div key={m.id} className="ml-auto max-w-prose rounded bg-black px-4 py-2 text-sm text-white">{m.content}</div>
              : <Answer key={m.id} m={m} />)}
            {busy && <Spinner />}
          </div>
          <div ref={end} />
        </div>
        {error && <div className="px-4"><Alert tone="error">{error}</Alert></div>}
        <form onSubmit={ask} className="flex gap-2 border-t border-lightborder p-3">
          <Select className="w-40" value={product} onChange={(e) => setProduct(e.target.value)} options={[{ value: "", label: "Both products" }, "ObserveOps", "ServiceOps"]} />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Type a question" />
          <Button variant="primary" type="submit" loading={busy}><Send size={16} /> Ask</Button>
        </form>
      </div>
    </div>
  );
}

function Answer({ m }: { m: any }) {
  const [fb, setFb] = useState<boolean | null>(null);
  const [comment, setComment] = useState("");
  const meta = m.meta || {};
  async function send(helpful: boolean) {
    setFb(helpful);
    await api.post(`/ask/messages/${m.id}/feedback`, { helpful, comment });
  }
  return (
    <Card className="max-w-prose">
      <div className="mb-2 flex flex-wrap items-center gap-2 text-sm">
        {meta.not_found && <Badge tone="warning">Not found in approved documentation</Badge>}
        {meta.product && <Badge>{meta.product}</Badge>}
        {meta.module && <Badge>{meta.module}</Badge>}
        {meta.classification && meta.classification !== "Not applicable" && <StatusBadge status={meta.classification} />}
        {meta.sizing && <Badge tone="info">Sizing from rule table</Badge>}
      </div>
      <div className="prose-plain whitespace-pre-wrap text-sm">{m.content}</div>
      {meta.limitations && <p className="mt-2 text-sm"><b>Limitations:</b> {meta.limitations}</p>}
      {meta.clarification_needed && <p className="mt-2 text-sm"><b>Clarification needed:</b> {meta.clarification_needed}</p>}
      {meta.conflicts && <Alert tone="warning">Sources disagree: {meta.conflicts}</Alert>}
      {m.citations?.length > 0 && (
        <div className="mt-4 border-t border-lightborder pt-2">
          <div className="text-sm font-semibold">Sources</div>
          <ol className="text-sm">
            {m.citations.map((c: any) => (
              <li key={c.id}>[{c.id}] {c.url ? <a href={c.url} target="_blank" rel="noreferrer" className="underline">{c.title}</a>
                : <a href={`/api/knowledge/sources/${c.source_id}/download`} className="underline">{c.title}</a>}
                <span className="text-muted"> · {c.section}{c.section_path && ` › ${c.section_path}`}{c.page && ` · ${c.page}`}{c.product_version && ` · v${c.product_version}`}{c.label && ` · ${c.label}`}</span></li>
            ))}
          </ol>
        </div>
      )}
      {m.id && typeof m.id === "number" && (
        <div className="mt-2 flex items-center gap-2">
          {fb === null ? <>
            <Input className="max-w-sm" placeholder="Optional comment" value={comment} onChange={(e) => setComment(e.target.value)} />
            <button aria-label="Helpful" className="rounded p-2 hover:bg-offwhite" onClick={() => send(true)}><ThumbsUp size={16} /></button>
            <button aria-label="Not helpful" className="rounded p-2 hover:bg-offwhite" onClick={() => send(false)}><ThumbsDown size={16} /></button>
          </> : <span className="text-sm text-muted">Thanks for the feedback.</span>}
        </div>
      )}
    </Card>
  );
}

function Gaps() {
  const [resolved, setResolved] = useState(false);
  const { data, reload } = useApi<any[]>(`/ask/gaps?resolved=${resolved}`, [resolved]);
  return (
    <>
      <label className="mb-4 flex items-center gap-2 text-sm"><input type="checkbox" checked={resolved} onChange={(e) => setResolved(e.target.checked)} /> Show resolved</label>
      <Table head={["Question", "Reason", "Comment", "When", ""]} empty="No gaps logged.">
        {(data || []).map((g) => (
          <tr key={g.id}><td className="max-w-prose">{g.question}</td><td>{g.reason === "not_found" ? "Not found" : "Not helpful"}</td><td>{g.comment}</td>
            <td>{fmtDate(g.at, true)}</td><td>{!g.resolved && <Button variant="ghost" onClick={() => api.post(`/ask/gaps/${g.id}/resolve`).then(reload)}>Resolve</Button>}</td></tr>
        ))}
      </Table>
    </>
  );
}
