"use client";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { Alert, Button, Field, Input } from "@/components/ui";
import { api } from "@/lib/api";
import { useBranding } from "@/lib/branding";
import { useSession } from "@/lib/session";

export default function LoginPage() {
  const router = useRouter();
  const { reload } = useSession();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const brand = useBranding();

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.post("/auth/login", { username, password });
      await reload();
      router.replace("/");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen">
      <div className="hidden flex-1 flex-col justify-end bg-black p-16 text-white lg:flex">
        <h1 className="text-h1">Presales Intelligence</h1>
        <p className="mt-4 max-w-prose text-lg text-mono-300">
          RFP responses, demo scripts and product answers, grounded in approved Motadata material.
        </p>
      </div>
      <div className="flex flex-1 items-center justify-center p-8">
        <form onSubmit={submit} className="flex w-full max-w-sm flex-col gap-4">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={brand.logo} alt="Motadata" className="mb-8 h-12 w-auto min-w-[120px] self-start object-contain" />
          <h2 className="text-h2">Sign in</h2>
          {error && <Alert tone="error">{error}</Alert>}
          <Field label="Username"><Input autoFocus autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required /></Field>
          <Field label="Password"><Input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></Field>
          <Button variant="primary" type="submit" loading={busy} className="justify-center">Sign in</Button>
          <p className="text-sm text-muted">Accounts are created by the system administrator.</p>
        </form>
      </div>
    </div>
  );
}
