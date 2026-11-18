"use client";
import { Plus } from "lucide-react";
import { useState } from "react";
import { CustomerForm } from "@/components/CustomerForm";
import { Button, Input, Modal, PageHeader, Spinner, Table } from "@/components/ui";
import { fmtDate } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useSession } from "@/lib/session";

export default function CustomersPage() {
  const { can } = useSession();
  const [q, setQ] = useState("");
  const { data, loading, reload } = useApi<any[]>(`/customers${q ? `?q=${encodeURIComponent(q)}` : ""}`, [q]);
  const [edit, setEdit] = useState<any | null>(null);

  return (
    <>
      <PageHeader title="Customer contexts" subtitle="Customer details entered once and reused by RFP workspaces and demo scripts."
        actions={can("customers.create") && <Button variant="primary" onClick={() => setEdit({})}><Plus size={16} /> New customer</Button>} />
      <div className="mb-4 max-w-prose"><Input placeholder="Filter by name" value={q} onChange={(e) => setQ(e.target.value)} /></div>
      {loading ? <Spinner /> : (
        <Table head={["Customer", "Industry", "Buyer", "Region", "Competitors", "Updated"]}>
          {(data || []).map((c) => (
            <tr key={c.id} className="cursor-pointer" onClick={() => can("customers.edit") && setEdit(c)}>
              <td className="font-semibold">{c.name}</td><td>{c.industry}</td><td>{c.buyer_type}</td><td>{c.region}</td>
              <td>{c.competitors.join(", ")}</td><td>{fmtDate(c.updated_at)}</td>
            </tr>
          ))}
        </Table>
      )}
      <Modal open={!!edit} title={edit?.id ? "Edit customer" : "New customer"} onClose={() => setEdit(null)}>
        {edit && <CustomerForm initial={edit.id ? edit : undefined} onSaved={() => { setEdit(null); reload(); }} />}
      </Modal>
    </>
  );
}
