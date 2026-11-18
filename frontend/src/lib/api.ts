/** Thin fetch wrapper. State-changing requests carry the CSRF header the backend requires. */

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function handle<T>(res: Response): Promise<T> {
  if (res.status === 401 && typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
    window.location.href = "/login";
  }
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const body = await res.json();
      msg = typeof body.detail === "string" ? body.detail : Array.isArray(body.detail)
        ? body.detail.map((d: { msg: string; loc?: string[] }) => `${(d.loc || []).slice(-1)[0] ?? ""}: ${d.msg}`).join("; ")
        : JSON.stringify(body.detail ?? body);
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, msg || `Request failed (${res.status})`);
  }
  const type = res.headers.get("content-type") || "";
  return (type.includes("application/json") ? res.json() : res.text()) as Promise<T>;
}

const H = { "X-Requested-With": "presales" };

export const api = {
  get: <T = any>(path: string) => fetch(`/api${path}`, { credentials: "same-origin" }).then((r) => handle<T>(r)),
  post: <T = any>(path: string, body?: unknown) =>
    fetch(`/api${path}`, {
      method: "POST", credentials: "same-origin", headers: { ...H, "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    }).then((r) => handle<T>(r)),
  put: <T = any>(path: string, body?: unknown) =>
    fetch(`/api${path}`, {
      method: "PUT", credentials: "same-origin", headers: { ...H, "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}),
    }).then((r) => handle<T>(r)),
  patch: <T = any>(path: string, body?: unknown) =>
    fetch(`/api${path}`, {
      method: "PATCH", credentials: "same-origin", headers: { ...H, "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}),
    }).then((r) => handle<T>(r)),
  del: <T = any>(path: string) =>
    fetch(`/api${path}`, { method: "DELETE", credentials: "same-origin", headers: H }).then((r) => handle<T>(r)),
  upload: <T = any>(path: string, form: FormData) =>
    fetch(`/api${path}`, { method: "POST", credentials: "same-origin", headers: H, body: form }).then((r) => handle<T>(r)),
};

/** Download a file from an authenticated endpoint and save it with the server's file name. */
export async function download(path: string) {
  const res = await fetch(`/api${path}`, { credentials: "same-origin" });
  if (!res.ok) await handle(res);
  const blob = await res.blob();
  const cd = res.headers.get("content-disposition") || "";
  const name = /filename="([^"]+)"/.exec(cd)?.[1] || "download";
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export function fmtDate(v?: string | null, withTime = false) {
  if (!v) return "";
  const d = new Date(v);
  return withTime
    ? d.toLocaleString("en-GB", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })
    : d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

export function money(v?: number | null) {
  if (v === null || v === undefined) return "-";
  return `$${v.toFixed(2)}`;
}
