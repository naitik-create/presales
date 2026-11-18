"use client";
import Link from "next/link";
import { Card, Empty, PageHeader, Progress, Spinner, StatusBadge } from "@/components/ui";
import { fmtDate, money } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useSession } from "@/lib/session";

export default function Dashboard() {
  const { me } = useSession();
  const { data, loading } = useApi<any>("/dashboard");
  if (loading || !data) return <Spinner />;
  const tiles = Object.keys(data).length;
  return (
    <>
      <PageHeader title={`Welcome, ${me?.full_name.split(" ")[0]}`} subtitle="Recent work and items waiting for you." />
      {tiles === 0 && <Empty>You have no modules assigned yet. Ask the administrator to give you a role.</Empty>}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 xl:grid-cols-3">
        {data.pending && (
          <Card title="Pending approvals">
            <ul className="flex flex-col gap-2 text-sm">
              {"rfp_answers" in data.pending && <Row label="RFP answers awaiting approval" value={data.pending.rfp_answers} href="/rfp" />}
              {"knowledge_sources" in data.pending && <Row label="Knowledge sources to approve" value={data.pending.knowledge_sources} href="/knowledge?tab=approval" />}
              {"use_cases" in data.pending && <Row label="Demo use cases to approve" value={data.pending.use_cases} href="/demo?tab=usecases" />}
              {"scoring" in data.pending && <Row label="Scoring transactions" value={data.pending.scoring} href="/scorecard" />}
            </ul>
          </Card>
        )}
        {data.rfp_workspaces && (
          <Card title="RFP workspaces" actions={<Link className="text-sm underline" href="/rfp">All</Link>}>
            <List items={data.rfp_workspaces} href={(x) => `/rfp/${x.id}`} right={(x) => <StatusBadge status={x.status} />} />
            {data.rfp_jobs?.length > 0 && (
              <div className="mt-4 flex flex-col gap-2">
                <div className="text-sm font-semibold">Running jobs</div>
                {data.rfp_jobs.map((j: any) => (
                  <div key={j.id} className="text-sm"><Link href={`/rfp/${j.ref_id}`} className="underline">Job #{j.id}</Link> {j.status}<Progress value={j.progress} /></div>
                ))}
              </div>
            )}
          </Card>
        )}
        {data.demo_scripts && (
          <Card title="Recent demo scripts" actions={<Link className="text-sm underline" href="/demo">All</Link>}>
            <List items={data.demo_scripts} href={(x) => `/demo/${x.id}`} right={(x) => <span className="text-sm text-muted">v{x.version}</span>} />
          </Card>
        )}
        {data.ingestion && (
          <Card title="Knowledge ingestion">
            <ul className="flex flex-col gap-1 text-sm">
              {Object.entries(data.ingestion).map(([k, v]) => <li key={k} className="flex justify-between"><StatusBadge status={k} /> <span>{String(v)}</span></li>)}
            </ul>
          </Card>
        )}
        {data.usage && (
          <Card title={`AI usage ${data.usage.month}`} actions={<Link className="text-sm underline" href="/admin?tab=usage">Details</Link>}>
            <div className="text-h3">{money(data.usage.spent)}</div>
            <div className="text-sm text-muted">{data.usage.calls} calls{data.usage.budget ? ` of a ${money(data.usage.budget)} budget` : ", no budget set"}</div>
            {data.usage.budget && <div className="mt-2"><Progress value={(100 * data.usage.spent) / data.usage.budget} /></div>}
          </Card>
        )}
      </div>
    </>
  );
}

function Row({ label, value, href }: { label: string; value: number; href: string }) {
  return <li><Link href={href} className="flex justify-between hover:underline"><span>{label}</span><span className="font-semibold">{value}</span></Link></li>;
}

function List({ items, href, right }: { items: any[]; href: (x: any) => string; right: (x: any) => React.ReactNode }) {
  if (!items.length) return <p className="text-sm text-muted">None yet.</p>;
  return (
    <ul className="flex flex-col divide-y divide-lightborder">
      {items.map((x) => (
        <li key={x.id} className="flex items-center justify-between gap-2 py-2">
          <Link href={href(x)} className="min-w-0 truncate text-sm font-semibold hover:underline">{x.title}</Link>
          <span className="flex shrink-0 items-center gap-2">{right(x)}<span className="text-sm text-muted">{fmtDate(x.updated_at)}</span></span>
        </li>
      ))}
    </ul>
  );
}
