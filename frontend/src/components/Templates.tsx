"use client";
import { Upload } from "lucide-react";
import { useState } from "react";
import { Alert, Button, Field, Input, Modal, Select, Table } from "@/components/ui";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useSession } from "@/lib/session";

export function Templates({ module }: { module: "rfp" | "demo" }) {
  const { can } = useSession();
  const { data, reload } = useApi<any[]>(`/rfp/templates?module=${module}`);
  const [open, setOpen] = useState<any | null>(null);
  const [error, setError] = useState("");
  const manage = can(module === "rfp" ? "rfp.manage_templates" : "demo.manage_templates");
  async function upload(form: FormData) {
    try { form.set("module", module); await api.upload("/rfp/templates", form); setOpen(null); reload(); } catch (e) { setError((e as Error).message); }
  }
  return (
    <>
      <div className="mb-4 flex items-center justify-between">
        <p className="text-sm text-muted">Templates use named placeholders written as {"{{executive_summary}}"}; branding, headers and styles are kept. Samples are style and structure references only.</p>
        {manage && <Button variant="primary" onClick={() => setOpen({})}><Upload size={16} /> Upload</Button>}
      </div>
      <Table head={["Name", "Kind", "Placeholders", "Version", ""]} empty="No templates yet.">
        {(data || []).map((t) => (
          <tr key={t.id}>
            <td className="font-semibold">{t.name}</td><td>{t.kind}</td>
            <td>{t.placeholders.map((p: any) => p.name).join(", ")}</td><td>{t.version}</td>
            <td>{manage && t.kind === "template" && <Button variant="ghost" onClick={() => setOpen(t)}>New version</Button>}</td>
          </tr>
        ))}
      </Table>
      <Modal open={!!open} title={open?.id ? `New version of ${open.name}` : "Upload template or sample"} onClose={() => setOpen(null)}>
        <form className="flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); upload(new FormData(e.currentTarget)); }}>
          {error && <Alert tone="error">{error}</Alert>}
          {open?.id && <input type="hidden" name="template_id" value={open.id} />}
          <Field label="Name"><Input name="name" defaultValue={open?.name || ""} required /></Field>
          {!open?.id && <Field label="Kind"><Select name="kind" options={[{ value: "template", label: "Template (with placeholders)" }, { value: "sample", label: "Sample document (style reference)" }]} /></Field>}
          <Field label="File (.docx)"><input type="file" name="file" required accept=".docx,.doc,.pdf" /></Field>
          <div><Button variant="primary" type="submit">Upload</Button></div>
        </form>
      </Modal>
    </>
  );
}
