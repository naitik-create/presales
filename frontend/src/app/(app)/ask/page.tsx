"use client";
import { ArrowUp, BookOpen, Check, ChevronLeft, Copy, FileText, Globe, MessageSquarePlus, Sparkles, ThumbsDown, ThumbsUp, Trash2 } from "lucide-react";
import { KeyboardEvent, ReactNode, useEffect, useRef, useState } from "react";
import { Alert, Badge, Button, cx, Segmented, StatusBadge, Table } from "@/components/ui";
import { api, fmtDate } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useSession } from "@/lib/session";

const SUGGESTIONS = [
  "Does ObserveOps support high availability with automatic failover?",
  "Which databases can ServiceOps use, and which versions?",
  "What ports must be open between the collector and the main server?",
  "How is ServiceOps licensed?",
];
const PRODUCTS = [{ key: "", label: "Both" }, { key: "ObserveOps", label: "ObserveOps" }, { key: "ServiceOps", label: "ServiceOps" }];

export default function AskPage() {
  const { can } = useSession();
  const [view, setView] = useState<"chat" | "gaps">("chat");
  if (view === "gaps") return <Gaps onBack={() => setView("chat")} />;
  return <Chat canGaps={can("ask.view_gaps")} onGaps={() => setView("gaps")} />;
}

function Chat({ canGaps, onGaps }: { canGaps: boolean; onGaps: () => void }) {
  const convs = useApi<any[]>("/ask/conversations");
  const [cid, setCid] = useState<number | null>(null);
  const [messages, setMessages] = useState<any[]>([]);
  const [q, setQ] = useState("");
  const [product, setProduct] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const end = useRef<HTMLDivElement>(null);
  const box = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!cid) { setMessages([]); return; }
    api.get(`/ask/conversations/${cid}`).then((c) => setMessages(c.messages));
  }, [cid]);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, busy]);
  useEffect(() => {  // grow the composer with its content, up to a limit
    const el = box.current;
    if (el) { el.style.height = "auto"; el.style.height = `${Math.min(el.scrollHeight, 160)}px`; }
  }, [q]);

  async function ask(text?: string) {
    const question = (text ?? q).trim();
    if (!question || busy) return;
    setQ(""); setBusy(true); setError("");
    setMessages((m) => [...m, { id: "tmp", role: "user", content: question }]);
    try {
      const r = await api.post("/ask", { question, conversation_id: cid, product: product || null });
      if (!cid) { setCid(r.conversation_id); convs.reload(); }
      setMessages((m) => [...m.filter((x) => x.id !== "tmp"), { id: `u${Date.now()}`, role: "user", content: question }, r.message]);
    } catch (err) {
      setError((err as Error).message);
      setMessages((m) => m.filter((x) => x.id !== "tmp"));
      setQ(question);
    } finally { setBusy(false); box.current?.focus(); }
  }
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(); }
  };
  const empty = messages.length === 0 && !busy;

  const composer = (
    <div className="w-full rounded-lg border border-border bg-white shadow-sm focus-within:border-black">
      <textarea ref={box} rows={1} value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={onKey}
        placeholder="Ask about capabilities, architecture, prerequisites, integrations, licensing or sizing…"
        className="block w-full resize-none rounded-lg bg-transparent px-4 pt-3 text-sm placeholder:text-mono-500 focus:outline-none" />
      <div className="flex items-center justify-between gap-2 px-3 pb-3 pt-2">
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted">Product</span>
          <Segmented items={PRODUCTS} active={product} onChange={setProduct} />
        </div>
        <button type="button" aria-label="Send" onClick={() => ask()} disabled={!q.trim() || busy}
          className="flex h-8 w-8 items-center justify-center rounded-full bg-accent text-black transition-colors hover:bg-black hover:text-white disabled:cursor-not-allowed disabled:bg-mono-200 disabled:text-mono-500">
          <ArrowUp size={16} />
        </button>
      </div>
    </div>
  );

  return (
    <div className="-mx-8 -my-6 flex h-[calc(100vh-49px)]">
      {/* conversation history */}
      <aside className="hidden w-56 shrink-0 flex-col border-r border-lightborder px-3 py-4 lg:flex">
        <Button variant="secondary" className="w-full" onClick={() => { setCid(null); setError(""); }}><MessageSquarePlus size={14} /> New chat</Button>
        <div className="mb-1 mt-6 px-2 text-sm text-muted">Recent</div>
        <ul className="flex-1 overflow-y-auto">
          {(convs.data || []).map((c) => (
            <li key={c.id} className={cx("group flex items-center rounded", c.id === cid ? "bg-mono-100" : "hover:bg-offwhite")}>
              <button className={cx("min-w-0 flex-1 truncate px-2 py-2 text-left text-sm", c.id === cid && "font-semibold")} title={c.title} onClick={() => { setCid(c.id); setError(""); }}>{c.title}</button>
              <button aria-label="Delete conversation" className="mr-1 hidden rounded p-1 text-muted hover:text-error group-hover:block"
                onClick={() => confirm("Delete this conversation?") && api.del(`/ask/conversations/${c.id}`).then(() => { if (cid === c.id) setCid(null); convs.reload(); })}>
                <Trash2 size={14} />
              </button>
            </li>
          ))}
          {convs.data?.length === 0 && <li className="px-2 text-sm text-muted">No conversations yet</li>}
        </ul>
        {canGaps && <button onClick={onGaps} className="mt-2 flex items-center gap-2 rounded px-2 py-2 text-left text-sm text-mono-700 hover:bg-offwhite"><BookOpen size={14} /> Unanswered questions</button>}
      </aside>

      {/* chat */}
      <section className="flex min-w-0 flex-1 flex-col">
        {empty ? (
          <div className="flex flex-1 flex-col items-center justify-center px-6">
            <div className="flex w-full max-w-prose flex-col items-center gap-6">
              <span className="flex h-12 w-12 items-center justify-center rounded-full bg-accent text-black"><Sparkles size={20} /></span>
              <div className="text-center">
                <h1 className="text-h4">Ask Motadata</h1>
                <p className="mt-1 text-sm text-muted">Answers come only from approved Knowledge Hub documents, with sources you can open.</p>
              </div>
              {composer}
              {error && <Alert tone="error">{error}</Alert>}
              <div className="grid w-full grid-cols-1 gap-2 md:grid-cols-2">
                {SUGGESTIONS.map((s) => (
                  <button key={s} onClick={() => ask(s)} className="rounded-lg border border-lightborder px-4 py-3 text-left text-sm text-mono-700 hover:border-mono-400 hover:text-black">{s}</button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <>
            <div className="flex-1 overflow-y-auto px-6">
              <div className="mx-auto flex max-w-prose flex-col gap-8 py-8">
                {messages.map((m) => m.role === "user"
                  ? <div key={m.id} className="ml-auto max-w-lg whitespace-pre-wrap rounded-lg bg-mono-100 px-4 py-2 text-sm">{m.content}</div>
                  : <Answer key={m.id} m={m} />)}
                {busy && (
                  <div className="flex items-center gap-3 text-sm text-muted">
                    <span className="flex h-8 w-8 items-center justify-center rounded-full bg-accent text-black"><Sparkles size={14} /></span>
                    <span className="flex gap-1"><Dot d={0} /><Dot d={150} /><Dot d={300} /></span> Searching approved documents…
                  </div>
                )}
                <div ref={end} />
              </div>
            </div>
            <div className="px-6 pb-6">
              <div className="mx-auto flex max-w-prose flex-col gap-2">
                {error && <Alert tone="error">{error}</Alert>}
                {composer}
                <p className="text-center text-sm text-muted">Enter to send · Shift + Enter for a new line</p>
              </div>
            </div>
          </>
        )}
      </section>
    </div>
  );
}

function Dot({ d }: { d: number }) {
  return <span className="h-1 w-1 animate-bounce rounded-full bg-mono-500" style={{ animationDelay: `${d}ms` }} />;
}

/** Minimal formatting for answers: paragraphs, "- " lists, **bold** and [S1] citation markers. */
function Rich({ text }: { text: string }) {
  const inline = (s: string, k: string): ReactNode[] =>
    s.split(/(\*\*[^*]+\*\*|\[S\d+\])/g).filter(Boolean).map((part, i) => {
      if (part.startsWith("**")) return <strong key={`${k}${i}`}>{part.slice(2, -2)}</strong>;
      if (/^\[S\d+\]$/.test(part)) return <sup key={`${k}${i}`} className="mx-px rounded bg-mono-100 px-1 text-mono-700">{part.slice(2, -1)}</sup>;
      return <span key={`${k}${i}`}>{part}</span>;
    });
  const blocks = text.split(/\n{2,}/);
  return (
    <div className="flex flex-col gap-3 text-sm leading-relaxed">
      {blocks.map((b, i) => {
        const lines = b.split("\n");
        if (lines.every((l) => /^\s*[-*•]\s+/.test(l))) {
          return <ul key={i} className="flex list-disc flex-col gap-1 pl-5">{lines.map((l, j) => <li key={j}>{inline(l.replace(/^\s*[-*•]\s+/, ""), `${i}-${j}-`)}</li>)}</ul>;
        }
        return <p key={i} className="whitespace-pre-wrap">{inline(b, `${i}-`)}</p>;
      })}
    </div>
  );
}

function Answer({ m }: { m: any }) {
  const [fb, setFb] = useState<boolean | null>(null);
  const [copied, setCopied] = useState(false);
  const meta = m.meta || {};
  const cites: any[] = m.citations || [];
  async function send(helpful: boolean) {
    setFb(helpful);
    const comment = helpful ? "" : (prompt("What was wrong or missing? (optional)") || "");
    await api.post(`/ask/messages/${m.id}/feedback`, { helpful, comment });
  }
  const tags = [meta.product, meta.module].filter(Boolean);
  return (
    <div className="flex gap-3">
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent text-black"><Sparkles size={14} /></span>
      <div className="min-w-0 flex-1">
        {(meta.not_found || tags.length > 0 || (meta.classification && meta.classification !== "Not applicable") || meta.sizing) && (
          <div className="mb-2 flex flex-wrap items-center gap-2">
            {meta.not_found && <Badge tone="warning">Not found in approved documentation</Badge>}
            {meta.classification && meta.classification !== "Not applicable" && !meta.not_found && <StatusBadge status={meta.classification} />}
            {meta.sizing && <Badge tone="info">From the sizing rules</Badge>}
            {tags.map((t: string) => <span key={t} className="text-sm text-muted">{t}</span>)}
          </div>
        )}
        <Rich text={m.content} />
        {(meta.limitations || meta.clarification_needed) && (
          <dl className="mt-3 flex flex-col gap-1 text-sm">
            {meta.limitations && <div><dt className="inline font-semibold">Limitations: </dt><dd className="inline text-mono-700">{meta.limitations}</dd></div>}
            {meta.clarification_needed && <div><dt className="inline font-semibold">To answer fully: </dt><dd className="inline text-mono-700">{meta.clarification_needed}</dd></div>}
          </dl>
        )}
        {meta.conflicts && <div className="mt-3"><Alert tone="warning">Sources disagree: {meta.conflicts}</Alert></div>}

        {cites.length > 0 && (
          <div className="mt-4">
            <div className="mb-2 text-sm text-muted">Sources</div>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {cites.map((c) => (
                <a key={c.id} href={c.url || `/api/knowledge/sources/${c.source_id}/download`} target={c.url ? "_blank" : undefined} rel="noreferrer"
                  className="flex items-start gap-2 rounded-lg border border-lightborder px-3 py-2 hover:border-mono-400">
                  <span className="mt-px flex h-5 w-5 shrink-0 items-center justify-center rounded bg-mono-100 text-sm text-mono-700">{String(c.id).replace(/^S/, "")}</span>
                  <span className="min-w-0">
                    <span className="flex items-center gap-1 text-sm font-semibold"><span className="truncate">{c.title}</span>{c.url ? <Globe size={12} className="shrink-0 text-muted" /> : <FileText size={12} className="shrink-0 text-muted" />}</span>
                    <span className="block truncate text-sm text-muted">{[c.section_path || c.section, c.page, c.product_version && `v${c.product_version}`, c.label].filter(Boolean).join(" · ")}</span>
                  </span>
                </a>
              ))}
            </div>
          </div>
        )}

        {typeof m.id === "number" && (
          <div className="mt-3 flex items-center gap-1 text-muted">
            <IconBtn label={copied ? "Copied" : "Copy answer"} onClick={() => { navigator.clipboard?.writeText(m.content); setCopied(true); setTimeout(() => setCopied(false), 1500); }}>
              {copied ? <Check size={14} /> : <Copy size={14} />}
            </IconBtn>
            {fb === null ? <>
              <IconBtn label="Helpful" onClick={() => send(true)}><ThumbsUp size={14} /></IconBtn>
              <IconBtn label="Not helpful" onClick={() => send(false)}><ThumbsDown size={14} /></IconBtn>
            </> : <span className="ml-1 text-sm">{fb ? "Thanks for the feedback." : "Thanks. It was added to the unanswered questions list."}</span>}
          </div>
        )}
      </div>
    </div>
  );
}

function IconBtn({ label, onClick, children }: { label: string; onClick: () => void; children: ReactNode }) {
  return <button aria-label={label} title={label} onClick={onClick} className="rounded p-2 hover:bg-mono-100 hover:text-black">{children}</button>;
}

function Gaps({ onBack }: { onBack: () => void }) {
  const [resolved, setResolved] = useState("open");
  const { data, reload } = useApi<any[]>(`/ask/gaps?resolved=${resolved === "resolved"}`, [resolved]);
  return (
    <>
      <button onClick={onBack} className="mb-4 flex items-center gap-1 text-sm text-mono-700 hover:text-black"><ChevronLeft size={16} /> Back to Ask Motadata</button>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-h4">Unanswered questions</h1>
          <p className="text-sm text-muted">Questions the documentation could not answer, or answers marked not helpful. Use them to find missing documents.</p>
        </div>
        <Segmented items={[{ key: "open", label: "Open" }, { key: "resolved", label: "Resolved" }]} active={resolved} onChange={setResolved} />
      </div>
      <Table head={["Question", "Reason", "Comment", "When", ""]} empty={resolved === "open" ? "No open questions." : "Nothing resolved yet."}>
        {(data || []).map((g) => (
          <tr key={g.id}>
            <td className="max-w-prose">{g.question}</td>
            <td className="whitespace-nowrap">{g.reason === "not_found" ? <Badge tone="warning">Not found</Badge> : <Badge>Not helpful</Badge>}</td>
            <td className="text-muted">{g.comment}</td>
            <td className="whitespace-nowrap text-muted">{fmtDate(g.at, true)}</td>
            <td className="text-right">{!g.resolved && <Button variant="ghost" onClick={() => api.post(`/ask/gaps/${g.id}/resolve`).then(reload)}>Mark resolved</Button>}</td>
          </tr>
        ))}
      </Table>
    </>
  );
}
