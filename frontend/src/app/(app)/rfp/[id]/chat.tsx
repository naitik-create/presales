"use client";
/** "Ask this RFP": questions about one tender, answered from its documents, requirements and the team's working
 *  outputs with references; change requests come back as proposed changes to apply or discard. */
import { Check, MessageSquare, Send, Sparkles, X } from "lucide-react";
import { Fragment, ReactNode, useEffect, useRef, useState } from "react";
import { Alert, Badge, Button, Spinner, Table, Textarea } from "@/components/ui";
import { api, fmtDate } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useSession } from "@/lib/session";

const SUGGESTIONS = [
  "What are the EMD, PBG and tender fee?",
  "Is the penalty for delay capped?",
  "Which requirements are Non-Compliant, and why?",
  "Do we meet the OEM eligibility criteria?",
  "Add a pre-bid query asking to relax log retention to 1 year",
];

export function RfpChat({ wid, open, onClose, onChanged }: { wid: string; open: boolean; onClose: () => void; onChanged: () => void }) {
  const msgs = useApi<any[]>(open ? `/rfp/workspaces/${wid}/chat` : null, [open]);
  const [q, setQ] = useState("");
  const [asking, setAsking] = useState<string | null>(null);
  const [err, setErr] = useState("");
  const end = useRef<HTMLDivElement>(null);
  const list = msgs.data || [];
  const preparing = list.some((m) => (m.actions || []).some((a: any) => a.state === "preparing"));

  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [list.length, asking]);
  useEffect(() => {  // a change is being prepared by the revision job: check again until it is ready
    if (!open || !preparing) return;
    const t = setTimeout(() => msgs.reload(), 3000);
    return () => clearTimeout(t);
  }, [open, preparing, msgs]);

  async function send(text: string) {
    const question = text.trim();
    if (!question || asking) return;
    setAsking(question); setQ(""); setErr("");
    try { await api.post(`/rfp/workspaces/${wid}/chat`, { question }); }
    catch (e) { setErr((e as Error).message); setQ(question); }
    finally { setAsking(null); msgs.reload(); }
  }
  async function act(mid: number, index: number, what: "prepare" | "apply" | "discard") {
    setErr("");
    try {
      await api.post(`/rfp/workspaces/${wid}/chat/${mid}/actions/${index}/${what}`);
      if (what !== "prepare") onChanged();
    } catch (e) { setErr((e as Error).message); }
    msgs.reload();
  }
  if (!open) return null;
  return (
    <aside aria-label="Ask this RFP" className="fixed inset-y-0 right-0 z-40 flex w-full flex-col border-l border-border bg-white shadow-lg sm:w-[460px]">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="flex items-center gap-2 font-semibold"><MessageSquare size={16} /> Ask this RFP</div>
        <Button variant="ghost" aria-label="Close" onClick={onClose}><X size={16} /></Button>
      </div>
      <div className="flex-1 overflow-y-auto px-4 py-3">
        {msgs.loading && !msgs.data ? <Spinner /> : !list.length && !asking ? (
          <div className="flex flex-col gap-3 text-sm">
            <p className="text-muted">Ask anything about this tender. Answers come from the RFP documents, requirements and your
              working outputs, with page references. You can also ask for changes, for example a new pre-bid query; they come
              back as a proposal to apply or discard.</p>
            {SUGGESTIONS.map((s) => <button key={s} type="button" onClick={() => send(s)}
              className="rounded border border-border px-3 py-2 text-left hover:bg-mono-50">{s}</button>)}
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            {list.map((m) => m.role === "user"
              ? <div key={m.id} className="ml-8 self-end rounded bg-mono-100 px-3 py-2 text-sm">
                  <div className="whitespace-pre-wrap">{m.content}</div><div className="mt-1 text-xs text-muted">{m.by} · {fmtDate(m.at, true)}</div></div>
              : <Answer key={m.id} m={m} act={act} />)}
            {asking && <>
              <div className="ml-8 self-end rounded bg-mono-100 px-3 py-2 text-sm whitespace-pre-wrap">{asking}</div>
              <div className="flex items-center gap-2 text-sm text-muted"><Spinner /> Reading the RFP…</div>
            </>}
            <div ref={end} />
          </div>
        )}
      </div>
      {err && <div className="px-4 pb-2"><Alert tone="error">{err}</Alert></div>}
      <form className="flex items-end gap-2 border-t border-border p-3" onSubmit={(e) => { e.preventDefault(); send(q); }}>
        <Textarea rows={2} value={q} placeholder="Ask about this RFP, or ask for a change" onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(q); } }} />
        <Button type="submit" variant="primary" aria-label="Send" disabled={!q.trim() || !!asking}><Send size={16} /></Button>
      </form>
    </aside>
  );
}

/** Light Markdown: paragraphs, "- " / "1." lists, **bold**, and [D3]-style references as small markers. */
function Text({ text }: { text: string }) {
  const inline = (s: string): ReactNode[] => s.split(/(\*\*[^*]+\*\*|\[[DRSP]\d+\])/g).map((p, i) =>
    p.startsWith("**") ? <b key={i}>{p.slice(2, -2)}</b>
      : /^\[[DRSP]\d+\]$/.test(p) ? <sup key={i} className="ml-0.5 text-xs font-semibold text-info">{p.slice(1, -1)}</sup>
      : <Fragment key={i}>{p}</Fragment>);
  const blocks = text.split(/\n{2,}/);
  return <div className="flex flex-col gap-2">{blocks.map((b, i) => {
    const lines = b.split("\n");
    if (lines.every((l) => /^\s*([-*]|\d+\.)\s/.test(l)))
      return <ul key={i} className="list-disc pl-5">{lines.map((l, j) => <li key={j}>{inline(l.replace(/^\s*([-*]|\d+\.)\s/, ""))}</li>)}</ul>;
    return <p key={i} className="whitespace-pre-wrap">{inline(b)}</p>;
  })}</div>;
}

const KIND: Record<string, string> = { rfp: "RFP", requirement: "Requirement", knowledge: "Motadata docs", past: "Past bid" };

function Answer({ m, act }: { m: any; act: (mid: number, i: number, what: "prepare" | "apply" | "discard") => void }) {
  return (
    <div className="flex flex-col gap-2 text-sm">
      {m.not_found && <Badge tone="warning">Not found in this RFP</Badge>}
      <Text text={m.content} />
      {(m.actions || []).map((a: any) => <ActionCard key={a.index} a={a} onAct={(w) => act(m.id, a.index, w)} />)}
      {(m.citations || []).length > 0 && (
        <details className="text-xs">
          <summary className="cursor-pointer text-muted">Sources ({m.citations.length})</summary>
          <ul className="mt-1 flex flex-col gap-1">
            {m.citations.map((c: any) => (
              <li key={c.id}><span className="font-semibold text-info">{c.id}</span> {KIND[c.kind] || c.kind}: <b>{c.label || c.title}</b>
                {(c.ref || c.page) && <span className="text-muted"> · {c.ref || c.page}</span>}
                {c.url && <> · <a className="underline" href={c.url} target="_blank" rel="noreferrer">link</a></>}
                {c.text && <div className="text-muted">{c.text.length > 220 ? `${c.text.slice(0, 220)}…` : c.text}</div>}</li>))}
          </ul>
        </details>)}
    </div>
  );
}

function ActionCard({ a, onAct }: { a: any; onAct: (w: "prepare" | "apply" | "discard") => void }) {
  const { can } = useSession();
  const edit = can("rfp.edit");
  const [busy, setBusy] = useState(false);
  const run = async (w: "prepare" | "apply" | "discard") => { setBusy(true); try { await onAct(w); } finally { setBusy(false); } };
  const rows = a.kind === "params" ? a.preview || [] : a.changes || [];
  return (
    <div className="flex flex-col gap-2 rounded border border-accent p-3">
      <div className="flex flex-wrap items-center gap-2"><Sparkles size={14} /><b>Proposed change</b><Badge tone="info">{a.label}</Badge></div>
      <div>{a.summary}{a.requirement_numbers?.length > 0 && <span className="text-muted"> ({a.requirement_numbers.join(", ")})</span>}</div>
      {a.state === "preparing" && <div className="flex items-center gap-2 text-muted"><Spinner /> Preparing the change on the step…</div>}
      {a.state === "invalid" && <Alert tone="warning">Cannot be applied: {a.error}</Alert>}
      {a.state === "failed" && <Alert tone="error">Preparing failed: {a.error}</Alert>}
      {a.outdated && <Alert tone="warning">The step changed after this was prepared. Prepare it again.</Alert>}
      {(a.state === "ready" || (a.kind === "params" && a.state === "proposed")) && (
        <Table head={["Where", "Before", "After"]} empty="No changes.">
          {rows.map((c: any, i: number) => (
            <tr key={i}><td className="text-xs font-semibold">{c.where || c.label}</td>
              <td className="text-xs text-muted line-through decoration-mono-300">{String(c.before ?? "")}</td>
              <td className="text-xs">{String(c.after ?? "")}</td></tr>))}
        </Table>)}
      {a.state === "applied" && <Alert tone="success">Applied as a new version of {a.label}. Review and approve the step again on the Bid workflow tab.</Alert>}
      {a.state === "discarded" && <p className="text-muted">Discarded.</p>}
      {a.state === "closed" && <p className="text-muted">Handled on the {a.label} step.</p>}
      {edit && <div className="flex flex-wrap gap-2">
        {a.kind === "revise" && ["proposed", "failed", "closed"].includes(a.state) &&
          <Button disabled={busy} onClick={() => run("prepare")}><Sparkles size={14} /> {a.state === "proposed" ? "Prepare change" : "Prepare again"}</Button>}
        {a.kind === "revise" && a.outdated && <Button disabled={busy} onClick={() => run("prepare")}>Prepare again</Button>}
        {((a.state === "ready" && !a.outdated) || (a.kind === "params" && a.state === "proposed")) &&
          <Button variant="primary" disabled={busy || !rows.length} onClick={() => run("apply")}><Check size={14} /> Apply</Button>}
        {["ready", "proposed"].includes(a.state) && <Button variant="ghost" disabled={busy} onClick={() => run("discard")}>Discard</Button>}
      </div>}
      {!edit && a.state === "proposed" && <p className="text-xs text-muted">Someone with edit rights can prepare and apply this.</p>}
    </div>
  );
}
