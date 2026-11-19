"use client";
/** Shadcn-style primitives restyled with the brand tokens. No component hardcodes a colour, size or spacing value. */
import { AlertTriangle, CheckCircle2, Info, Loader2, X, XCircle } from "lucide-react";
import { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes, useEffect, useState } from "react";

export function cx(...c: (string | false | null | undefined)[]) {
  return c.filter(Boolean).join(" ");
}

/**
 * Buttons share one recognisable shape (a pill) so they never look like fields, which are square-cornered.
 * primary   – the one main action on a screen: Motadata accent fill, black text (5.86:1), turns black on hover
 * secondary – other actions: black outline, fills black on hover
 * ghost     – low-emphasis actions in lists and toolbars: light grey pill, darker on hover
 * danger    – destructive actions: error-colour outline (never the accent)
 */
export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
const BUTTON_BASE = "inline-flex h-8 items-center justify-center gap-2 whitespace-nowrap rounded-full border px-4 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-40";
const BUTTON_STYLES: Record<ButtonVariant, string> = {
  primary: "border-accent bg-accent text-black hover:border-black hover:bg-black hover:text-white disabled:hover:border-accent disabled:hover:bg-accent disabled:hover:text-black",
  secondary: "border-black bg-white text-black hover:bg-black hover:text-white disabled:hover:bg-white disabled:hover:text-black",
  ghost: "border-mono-100 bg-mono-100 px-3 text-black hover:border-mono-300 hover:bg-mono-300 disabled:hover:border-mono-100 disabled:hover:bg-mono-100",
  danger: "border-error bg-white text-error hover:bg-error hover:text-white disabled:hover:bg-white disabled:hover:text-error",
};

/** Button styling for links and file-picker labels that act as buttons. */
export function buttonClass(variant: ButtonVariant = "secondary", extra?: string) {
  return cx(BUTTON_BASE, BUTTON_STYLES[variant], "cursor-pointer", extra);
}

export function Button({ variant = "secondary", loading, className, children, ...p }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; loading?: boolean }) {
  return (
    <button {...p} disabled={p.disabled || loading}
      className={cx(BUTTON_BASE, BUTTON_STYLES[variant], className)}>
      {loading && <Loader2 size={16} className="animate-spin" />}
      {children}
    </button>
  );
}

export function Field({ label, hint, children, className }: { label: string; hint?: string; children: ReactNode; className?: string }) {
  return (
    <label className={cx("flex flex-col gap-1", className)}>
      <span className="text-sm text-mono-700">{label}</span>
      {children}
      {hint && <span className="text-sm text-muted">{hint}</span>}
    </label>
  );
}

const inputCls = "rounded border border-border bg-white px-3 py-1 text-sm placeholder:text-mono-500 focus:border-black focus:outline-none";
/** Fields fill their container unless the caller gives them a width (w-40, w-56 …). */
const fieldCls = (extra?: string) => cx(inputCls, /(^|\s)w-/.test(extra || "") ? "" : "w-full", extra);
export function Input(p: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...p} className={fieldCls(p.className)} />;
}
export function Textarea(p: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea rows={4} {...p} className={fieldCls(p.className)} />;
}
export function Select({ options, ...p }: SelectHTMLAttributes<HTMLSelectElement> & { options: (string | { value: string | number; label: string })[] }) {
  return (
    <select {...p} className={fieldCls(p.className)}>
      {options.map((o) => typeof o === "string"
        ? <option key={o} value={o}>{o}</option>
        : <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}

export function Card({ title, actions, children, className }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cx("rounded border border-border bg-white", className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-4 border-b border-lightborder px-4 py-2">
          <h2 className="text-sm font-semibold">{title}</h2>
          <div className="flex items-center gap-2">{actions}</div>
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
      <div>
        <h1 className="text-h4">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
      </div>
      <div className="flex flex-wrap items-center gap-2">{actions}</div>
    </div>
  );
}

type Tone = "success" | "warning" | "error" | "info" | "neutral" | "accent";
const toneCls: Record<Tone, string> = {
  success: "text-success border-success", warning: "text-warning border-warning", error: "text-error border-error",
  info: "text-info border-info", neutral: "text-mono-700 border-border", accent: "text-black border-accent bg-white",
};
const toneIcon: Record<Tone, ReactNode> = {
  success: <CheckCircle2 size={14} />, warning: <AlertTriangle size={14} />, error: <XCircle size={14} />,
  info: <Info size={14} />, neutral: null, accent: null,
};
/** Every status shows an icon and a text label as well as colour. */
export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className={cx("inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 text-sm", toneCls[tone])}>
      {toneIcon[tone]}
      {children}
    </span>
  );
}

const STATUS_TONES: Record<string, Tone> = {
  Completed: "success", Approved: "success", Ready: "success", Compliant: "success", Supported: "success", Reviewed: "success",
  Sent: "success", Submitted: "success", Won: "success",
  "Partially Compliant": "warning", "Partially Supported": "warning", "Needs Product Validation": "warning", "Not Verified": "warning",
  "Awaiting Review": "warning", "Pending Approval": "warning", Pending: "warning", Provisional: "warning", Draft: "neutral",
  "Supported Through Integration/Configuration": "success", "Planned, Officially Confirmed": "info",
  Failed: "error", Rejected: "error", "Non-Compliant": "error", "Not Supported": "error", Cancelled: "neutral", Disabled: "neutral",
  Queued: "info", Processing: "info", Uploaded: "info", Lost: "neutral",
};
export function StatusBadge({ status }: { status?: string | null }) {
  if (!status) return null;
  return <Badge tone={STATUS_TONES[status] || "neutral"}>{status}</Badge>;
}

export function Table({ head, children, empty }: { head: ReactNode[]; children: ReactNode; empty?: string }) {
  const hasRows = Array.isArray(children) ? children.flat().filter(Boolean).length > 0 : !!children;
  return (
    <div className="overflow-x-auto rounded border border-border">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-border bg-offwhite text-left text-mono-700">
            {head.map((h, i) => <th key={i} className="whitespace-nowrap px-3 py-2 text-sm font-semibold text-mono-600">{h}</th>)}
          </tr>
        </thead>
        <tbody className="[&>tr]:border-t [&>tr]:border-lightborder [&>tr:hover]:bg-offwhite [&_td]:px-3 [&_td]:py-2 [&_td]:align-top">
          {hasRows ? children : (
            <tr><td colSpan={head.length} className="py-6 text-center text-muted">{empty || "Nothing here yet."}</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

export function Tabs({ tabs, active, onChange }: { tabs: { key: string; label: string }[]; active: string; onChange: (k: string) => void }) {
  return (
    <div className="no-scrollbar mb-6 flex gap-1 overflow-x-auto border-b border-border" role="tablist">
      {tabs.map((t) => (
        <button key={t.key} role="tab" aria-selected={active === t.key} onClick={() => onChange(t.key)}
          className={cx("-mb-px whitespace-nowrap border-b-2 px-4 py-2 text-sm font-semibold",
            active === t.key ? "border-accent text-black" : "border-transparent text-muted hover:text-black")}>
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function Modal({ open, title, onClose, children, wide }: { open: boolean; title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    if (open) window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="modal-overlay fixed inset-0 z-50 flex items-start justify-center overflow-y-auto p-4" onClick={onClose}>
      <div role="dialog" aria-modal className={cx("mt-12 w-full rounded border border-border bg-white", wide ? "max-w-content" : "max-w-prose")}
        onClick={(e) => e.stopPropagation()}>
        <header className="flex items-center justify-between border-b border-lightborder px-4 py-3">
          <h2 className="text-h6">{title}</h2>
          <button aria-label="Close" onClick={onClose} className="rounded p-1 hover:bg-offwhite"><X size={20} /></button>
        </header>
        <div className="p-4">{children}</div>
      </div>
    </div>
  );
}

export function Alert({ tone = "info", children }: { tone?: "info" | "warning" | "error" | "success"; children: ReactNode }) {
  return (
    <div className={cx("flex items-start gap-2 rounded border bg-white px-3 py-2 text-sm", toneCls[tone])}>
      <span className="mt-1">{toneIcon[tone]}</span>
      <div className="text-black">{children}</div>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="rounded border border-dashed border-border p-8 text-center text-sm text-muted">{children}</div>;
}

export function Progress({ value }: { value: number }) {
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-mono-100" role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={100}>
      <div className="h-full bg-black transition-all" style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  );
}

/** Compact segmented control for sub-pages within a section. */
export function Segmented({ items, active, onChange }: { items: { key: string; label: string; count?: number }[]; active: string; onChange: (k: string) => void }) {
  return (
    <div role="tablist" className="inline-flex rounded bg-mono-100 p-1">
      {items.map((i) => (
        <button key={i.key} role="tab" aria-selected={active === i.key} onClick={() => onChange(i.key)}
          className={cx("rounded-sm px-3 py-1 text-sm transition-colors",
            active === i.key ? "bg-white font-semibold text-black shadow-sm" : "text-mono-600 hover:text-black")}>
          {i.label}{i.count !== undefined && <span className="ml-2 text-muted">{i.count}</span>}
        </button>
      ))}
    </div>
  );
}

/** Slide-over panel from the right, for editing one item without leaving the list. */
export function Drawer({ open, title, subtitle, onClose, children, footer }: { open: boolean; title: string; subtitle?: string; onClose: () => void; children: ReactNode; footer?: ReactNode }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    if (open) window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="modal-overlay fixed inset-0 z-50 flex justify-end" onClick={onClose}>
      <aside role="dialog" aria-modal aria-label={title} className="flex h-full w-full max-w-lg flex-col border-l border-border bg-white" onClick={(e) => e.stopPropagation()}>
        <header className="flex items-start justify-between gap-4 border-b border-lightborder px-6 py-4">
          <div><h2 className="text-h6">{title}</h2>{subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}</div>
          <button aria-label="Close" onClick={onClose} className="rounded p-1 hover:bg-offwhite"><X size={20} /></button>
        </header>
        <div className="flex-1 overflow-y-auto px-6 py-4">{children}</div>
        {footer && <footer className="flex justify-end gap-2 border-t border-lightborder px-6 py-4">{footer}</footer>}
      </aside>
    </div>
  );
}

/** Checkbox that can also show a partly-selected state (for "select all" over a group). */
export function Checkbox({ checked, indeterminate, onChange, label, disabled }: { checked: boolean; indeterminate?: boolean; onChange: (v: boolean) => void; label: string; disabled?: boolean }) {
  return (
    <input type="checkbox" aria-label={label} checked={checked} disabled={disabled}
      ref={(el) => { if (el) el.indeterminate = !!indeterminate && !checked; }}
      onChange={(e) => onChange(e.target.checked)}
      className="h-4 w-4 shrink-0 cursor-pointer accent-black disabled:cursor-not-allowed" />
  );
}

/** On/off switch for boolean settings. */
export function Toggle({ checked, onChange, label, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: string; disabled?: boolean }) {
  return (
    <button type="button" role="switch" aria-checked={checked} aria-label={label} disabled={disabled} onClick={() => onChange(!checked)}
      className={cx("relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors disabled:opacity-50",
        checked ? "bg-black" : "bg-mono-300")}>
      <span className={cx("inline-block h-4 w-4 rounded-full bg-white transition-transform", checked ? "translate-x-4" : "translate-x-px")} />
    </button>
  );
}

/** A labelled settings row: title and help text on the left, the control on the right. */
export function SettingRow({ title, help, children }: { title: string; help?: ReactNode; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-2 border-b border-lightborder py-3 last:border-b-0 md:flex-row md:items-center md:justify-between md:gap-8">
      <div className="min-w-0 md:max-w-prose">
        <div className="text-sm">{title}</div>
        {help && <div className="text-sm text-muted">{help}</div>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}

export function NumberInput({ value, onChange, unit, min, max, step }: { value: number | string; onChange: (v: number) => void; unit?: string; min?: number; max?: number; step?: number }) {
  return (
    <div className="flex items-center overflow-hidden rounded border border-border focus-within:border-black">
      <input type="number" value={value} min={min} max={max} step={step ?? 1}
        onChange={(e) => onChange(e.target.value === "" ? 0 : Number(e.target.value))}
        className="w-20 bg-white px-2 py-1 text-right text-sm focus:outline-none" />
      {unit && <span className="border-l border-border bg-offwhite px-2 py-1 text-sm text-muted">{unit}</span>}
    </div>
  );
}

/** Editable list of short values, such as domain names. */
export function TagInput({ values, onChange, placeholder, validate }: { values: string[]; onChange: (v: string[]) => void; placeholder?: string; validate?: (v: string) => string | null }) {
  const [draft, setDraft] = useState("");
  const [err, setErr] = useState("");
  const add = () => {
    const v = draft.trim().toLowerCase();
    if (!v) return;
    const problem = validate?.(v);
    if (problem) { setErr(problem); return; }
    if (!values.includes(v)) onChange([...values, v]);
    setDraft(""); setErr("");
  };
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-2">
        {values.map((v) => (
          <span key={v} className="inline-flex items-center gap-1 rounded-full border border-border bg-offwhite py-1 pl-3 pr-1 text-sm">
            {v}
            <button type="button" aria-label={`Remove ${v}`} className="rounded-full p-1 hover:bg-mono-200" onClick={() => onChange(values.filter((x) => x !== v))}><X size={12} /></button>
          </span>
        ))}
        {values.length === 0 && <span className="text-sm text-muted">None</span>}
      </div>
      <div className="flex gap-2">
        <Input value={draft} placeholder={placeholder} onChange={(e) => { setDraft(e.target.value); setErr(""); }}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }} />
        <Button type="button" onClick={add}>Add</Button>
      </div>
      {err && <span className="text-sm text-error">{err}</span>}
    </div>
  );
}

/** Footer for a settings form: shows unsaved state and save/discard actions. */
export function SaveBar({ dirty, saving, onSave, onReset, savedAt }: { dirty: boolean; saving?: boolean; onSave: () => void; onReset: () => void; savedAt?: string }) {
  return (
    <div className="mt-2 flex items-center justify-end gap-3 border-t border-lightborder pt-4">
      <span className="mr-auto text-sm text-muted">{dirty ? "Unsaved changes" : savedAt ? `Saved ${savedAt}` : ""}</span>
      <Button variant="ghost" onClick={onReset} disabled={!dirty || saving}>Discard</Button>
      <Button variant="primary" onClick={onSave} disabled={!dirty} loading={saving}>Save changes</Button>
    </div>
  );
}

export function Spinner() {
  return <Loader2 size={20} className="animate-spin text-muted" />;
}
