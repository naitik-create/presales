"use client";
import { DependencyList, useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";

/** Load JSON from the API; `reload` refetches. */
export function useApi<T = any>(path: string | null, deps: DependencyList = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(!!path);
  const reload = useCallback(async () => {
    if (!path) return;
    setLoading(true);
    try {
      setData(await api.get<T>(path));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, ...deps]);
  useEffect(() => { reload(); }, [reload]);
  return { data, setData, error, loading, reload };
}

/** Poll a job until it finishes, then call onDone. */
export function useJobPoll(jobId: number | null | undefined, onDone: () => void, interval = 3000) {
  const [job, setJob] = useState<any>(null);
  const done = useRef(onDone);
  done.current = onDone;
  useEffect(() => {
    if (!jobId) return;
    let stop = false;
    const tick = async () => {
      try {
        const j = await api.get(`/admin/jobs/${jobId}`);
        if (stop) return;
        setJob(j);
        if (["Completed", "Failed", "Cancelled"].includes(j.status)) {
          done.current();
          return;
        }
      } catch {
        /* keep polling */
      }
      if (!stop) setTimeout(tick, interval);
    };
    tick();
    return () => { stop = true; };
  }, [jobId, interval]);
  return job;
}

export function useDebounced<T>(value: T, ms = 500) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}
