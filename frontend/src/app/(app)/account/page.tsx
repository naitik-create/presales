"use client";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useState } from "react";
import { Alert, Button, Card, Field, Input, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";

function Account() {
  const { me, reload } = useSession();
  const router = useRouter();
  const first = useSearchParams().get("first");
  const [cur, setCur] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [msg, setMsg] = useState<{ tone: "error" | "success"; text: string } | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (pw !== pw2) return setMsg({ tone: "error", text: "The new passwords do not match" });
    try {
      await api.post("/auth/change-password", { current_password: cur, new_password: pw });
      setMsg({ tone: "success", text: "Password changed" });
      await reload();
      if (first) router.replace("/");
    } catch (err) {
      setMsg({ tone: "error", text: (err as Error).message });
    }
  }

  return (
    <>
      <PageHeader title="Account" subtitle={`${me?.full_name} (${me?.username}) · Roles: ${me?.roles.join(", ") || "none"}`} />
      {first && <div className="mb-4"><Alert tone="warning">Set a new password before you continue.</Alert></div>}
      <Card title="Change password" className="max-w-prose">
        <form onSubmit={submit} className="flex flex-col gap-4">
          {msg && <Alert tone={msg.tone}>{msg.text}</Alert>}
          <Field label="Current password"><Input type="password" value={cur} onChange={(e) => setCur(e.target.value)} required /></Field>
          <Field label="New password" hint="At least 10 characters with upper-case, lower-case and a digit.">
            <Input type="password" value={pw} onChange={(e) => setPw(e.target.value)} required />
          </Field>
          <Field label="Confirm new password"><Input type="password" value={pw2} onChange={(e) => setPw2(e.target.value)} required /></Field>
          <div><Button variant="primary" type="submit">Change password</Button></div>
        </form>
      </Card>
    </>
  );
}

export default function AccountPage() {
  return <Suspense><Account /></Suspense>;
}
