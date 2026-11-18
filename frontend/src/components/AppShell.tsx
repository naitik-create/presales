"use client";
import {
  Bell, BookOpen, FileSearch, FileText, LayoutDashboard, LogOut, MessageSquare, MonitorPlay,
  PanelLeftClose, PanelLeftOpen, Search, Settings, Trophy, User,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import { api, fmtDate } from "@/lib/api";
import { useBranding } from "@/lib/branding";
import { useSession } from "@/lib/session";
import { cx, Spinner } from "./ui";

const ICONS: Record<string, ReactNode> = {
  dashboard: <LayoutDashboard size={18} />, rfp: <FileSearch size={18} />,
  demo: <MonitorPlay size={18} />, ask: <MessageSquare size={18} />, scorecard: <Trophy size={18} />,
  knowledge: <BookOpen size={18} />, admin: <Settings size={18} />,
};

export default function AppShell({ children }: { children: ReactNode }) {
  const { me, loading } = useSession();
  const router = useRouter();
  const path = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const brand = useBranding();

  useEffect(() => {
    try { setCollapsed(localStorage.getItem("sidebar") === "collapsed"); } catch { /* storage unavailable */ }
  }, []);
  useEffect(() => {
    if (!loading && !me) router.replace("/login");
    else if (me?.must_change_password && path !== "/account") router.replace("/account?first=1");
  }, [loading, me, path, router]);

  if (loading || !me) {
    return <div className="flex h-screen items-center justify-center"><Spinner /></div>;
  }
  const toggle = () => {
    setCollapsed((c) => {
      try { localStorage.setItem("sidebar", c ? "open" : "collapsed"); } catch { /* ignore */ }
      return !c;
    });
  };
  return (
    <div className="flex min-h-screen">
      <aside className={cx("sticky top-0 flex h-screen flex-col border-r border-border bg-white", collapsed ? "w-sidebar-collapsed" : "w-sidebar")}>
        <div className={cx("flex items-center border-b border-lightborder", collapsed ? "justify-center px-2 py-3" : "px-4 py-3")}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          {collapsed ? <img src={brand.logomark} alt="Motadata" width={32} height={32} className="h-8 w-8 object-contain" />
            : <img src={brand.logo} alt="Motadata" className="h-8 w-auto min-w-[120px] max-w-full object-contain" />}
        </div>
        <nav className="flex-1 overflow-y-auto px-2 py-3">
          {me.nav.map((n) => {
            const active = n.href === "/" ? path === "/" : path.startsWith(n.href);
            return (
              <Link key={n.key} href={n.href} title={n.label}
                className={cx("mb-px flex items-center gap-3 rounded py-2 text-sm", collapsed ? "justify-center px-2" : "px-3",
                  active ? "bg-mono-100 font-semibold text-black" : "text-mono-600 hover:bg-offwhite hover:text-black")}>
                {ICONS[n.key]}
                {!collapsed && <span>{n.label}</span>}
              </Link>
            );
          })}
        </nav>
        <button onClick={toggle} className="flex items-center gap-2 border-t border-lightborder px-4 py-3 text-sm text-muted hover:text-black"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}>
          {collapsed ? <PanelLeftOpen size={18} /> : <><PanelLeftClose size={18} /> Collapse</>}
        </button>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        <main className="mx-auto w-full max-w-content flex-1 px-8 py-6 text-sm">{children}</main>
      </div>
    </div>
  );
}

function TopBar() {
  const { me } = useSession();
  const router = useRouter();
  const [q, setQ] = useState("");
  const [results, setResults] = useState<any[] | null>(null);
  const [notes, setNotes] = useState<any[]>([]);
  const [showNotes, setShowNotes] = useState(false);
  const [showUser, setShowUser] = useState(false);

  useEffect(() => {
    const load = () => api.get("/auth/notifications").then(setNotes).catch(() => {});
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, []);
  useEffect(() => {
    if (q.trim().length < 2) { setResults(null); return; }
    const t = setTimeout(() => api.get(`/search?q=${encodeURIComponent(q)}`).then(setResults).catch(() => setResults([])), 300);
    return () => clearTimeout(t);
  }, [q]);
  const unread = notes.filter((n) => !n.read).length;

  return (
    <header className="sticky top-0 z-40 flex items-center gap-4 border-b border-border bg-white px-8 py-2">
      <div className="relative max-w-prose flex-1">
        <Search size={16} className="absolute left-3 top-2 text-muted" />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search RFPs, demo scripts and knowledge"
          className="w-full rounded border border-lightborder bg-offwhite py-1 pl-8 pr-3 text-sm focus:border-black focus:bg-white focus:outline-none" />
        {results && (
          <div className="absolute left-0 right-0 top-12 max-h-96 overflow-y-auto rounded border border-border bg-white">
            {results.length === 0 && <div className="p-3 text-sm text-muted">No results</div>}
            {results.map((r, i) => (
              <button key={i} className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-offwhite"
                onClick={() => { setQ(""); router.push(r.href); }}>
                <span><span className="text-muted">{r.type}:</span> {r.title}</span>
                {r.status && <span className="text-muted">{r.status}</span>}
              </button>
            ))}
          </div>
        )}
      </div>
      <div className="relative ml-auto">
        <button aria-label="Notifications" className="relative rounded p-2 hover:bg-offwhite"
          onClick={() => { setShowNotes((s) => !s); if (unread) api.post("/auth/notifications/read").then(() => setNotes((n) => n.map((x) => ({ ...x, read: true })))); }}>
          <Bell size={18} />
          {unread > 0 && <span className="absolute right-1 top-1 h-2 w-2 rounded-full bg-accent" aria-label={`${unread} unread`} />}
        </button>
        {showNotes && (
          <div className="absolute right-0 top-12 w-96 max-h-96 overflow-y-auto rounded border border-border bg-white">
            {notes.length === 0 && <div className="p-4 text-sm text-muted">No notifications</div>}
            {notes.map((n) => (
              <Link key={n.id} href={n.link || "/"} onClick={() => setShowNotes(false)} className="block border-b border-lightborder px-4 py-3 hover:bg-offwhite">
                <div className="text-sm font-semibold">{n.title}</div>
                {n.body && <div className="text-sm text-muted">{n.body}</div>}
                <div className="text-sm text-muted">{fmtDate(n.at, true)}</div>
              </Link>
            ))}
          </div>
        )}
      </div>
      <div className="relative">
        <button onClick={() => setShowUser((s) => !s)} className="flex items-center gap-2 rounded px-2 py-1 text-sm hover:bg-offwhite">
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-mono-100 text-sm font-semibold text-mono-700">{(me?.full_name || "?").slice(0, 1).toUpperCase()}</span> {me?.full_name}
        </button>
        {showUser && (
          <div className="absolute right-0 top-12 w-56 rounded border border-border bg-white py-1">
            <Link href="/account" className="block px-4 py-2 text-sm hover:bg-offwhite" onClick={() => setShowUser(false)}>Account and password</Link>
            <Link href="/customers" className="block px-4 py-2 text-sm hover:bg-offwhite" onClick={() => setShowUser(false)}>Customer contexts</Link>
            <button className="flex w-full items-center gap-2 px-4 py-2 text-left text-sm hover:bg-offwhite"
              onClick={async () => { await api.post("/auth/logout"); window.location.href = "/login"; }}>
              <LogOut size={16} /> Sign out
            </button>
          </div>
        )}
      </div>
    </header>
  );
}

export function FileIcon() {
  return <FileText size={16} />;
}
