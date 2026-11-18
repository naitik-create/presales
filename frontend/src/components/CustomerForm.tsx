"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { Alert, Button, Field, Input, Select, Textarea } from "./ui";

export const INDUSTRIES = ["BFSI", "Healthcare", "Pharma", "Education", "Government/PSU", "Manufacturing", "Retail", "IT/ITES", "Telecom"];
export const REGIONS = ["India", "Middle East", "SEA", "Philippines", "Other"];
export const COMPETITORS = ["SolarWinds", "ManageEngine", "PRTG", "Everest IMS", "NinjaOne", "Ivanti", "Kaseya", "Lansweeper",
  "ServiceNow", "BMC Helix", "OpenText SMAX", "Datadog", "Dynatrace", "New Relic", "AppDynamics", "Splunk", "HaloITSM",
  "Freshservice", "Jira Service Management", "LogicMonitor", "Zabbix", "Nagios", "Elastic", "Grafana"];

export function CustomerForm({ initial, onSaved }: { initial?: any; onSaved: (c: any) => void }) {
  const [c, setC] = useState<any>(initial || { name: "", industry: "BFSI", buyer_type: "Private", region: "India", business_overview: "",
    existing_tools: "", infrastructure: "", competitors: [], pain_points: "", notes: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [other, setOther] = useState("");
  const set = (k: string, v: any) => setC((x: any) => ({ ...x, [k]: v }));

  async function save() {
    setBusy(true);
    setError("");
    try {
      const body = { ...c, parsed_sizes: null };
      const saved = c.id ? await api.put(`/customers/${c.id}`, body) : await api.post("/customers", body);
      onSaved(saved);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {error && <Alert tone="error">{error}</Alert>}
      <div className="grid grid-cols-2 gap-4">
        <Field label="Customer name"><Input value={c.name} onChange={(e) => set("name", e.target.value)} /></Field>
        <Field label="Industry"><Select value={c.industry} onChange={(e) => set("industry", e.target.value)} options={INDUSTRIES} /></Field>
        <Field label="Buyer type"><Select value={c.buyer_type} onChange={(e) => set("buyer_type", e.target.value)} options={[{ value: "Private", label: "Private" }, { value: "Public", label: "Government / PSU / public" }]} /></Field>
        <Field label="Region"><Select value={c.region} onChange={(e) => set("region", e.target.value)} options={REGIONS} /></Field>
      </div>
      <Field label="Business overview"><Textarea rows={2} value={c.business_overview} onChange={(e) => set("business_overview", e.target.value)} /></Field>
      <Field label="Existing monitoring and ITSM tools"><Input value={c.existing_tools} onChange={(e) => set("existing_tools", e.target.value)} /></Field>
      <Field label="Infrastructure" hint="Sizes are read from this text, for example '1,200 network devices, 400 servers, 30 branches'.">
        <Textarea rows={3} value={c.infrastructure} onChange={(e) => set("infrastructure", e.target.value)} />
      </Field>
      <Field label="Competitors">
        <div className="flex flex-wrap gap-2">
          {[...COMPETITORS, ...c.competitors.filter((x: string) => !COMPETITORS.includes(x))].map((n) => (
            <label key={n} className="flex items-center gap-1 text-sm">
              <input type="checkbox" checked={c.competitors.includes(n)}
                onChange={(e) => set("competitors", e.target.checked ? [...c.competitors, n] : c.competitors.filter((x: string) => x !== n))} />
              {n}
            </label>
          ))}
        </div>
        <Input className="mt-2" placeholder="Add another competitor and press Enter" value={other} onChange={(e) => setOther(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && other.trim()) {
              e.preventDefault();
              if (!c.competitors.includes(other.trim())) set("competitors", [...c.competitors, other.trim()]);
              setOther("");
            }
          }} />
      </Field>
      <Field label="Pain points"><Textarea rows={2} value={c.pain_points} onChange={(e) => set("pain_points", e.target.value)} /></Field>
      <Field label="Notes"><Textarea rows={2} value={c.notes} onChange={(e) => set("notes", e.target.value)} /></Field>
      <div><Button variant="primary" onClick={save} loading={busy} disabled={!c.name}>Save customer</Button></div>
    </div>
  );
}
