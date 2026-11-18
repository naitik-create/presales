"use client";
import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { api } from "./api";

export type Me = {
  id: number; username: string; full_name: string; email: string; must_change_password: boolean;
  is_scoring_participant: boolean; roles: string[]; permissions: string[]; nav: { key: string; label: string; href: string }[];
};

type Ctx = { me: Me | null; loading: boolean; reload: () => Promise<void>; can: (...codes: string[]) => boolean; area: (a: string) => boolean };
const SessionCtx = createContext<Ctx>({ me: null, loading: true, reload: async () => {}, can: () => false, area: () => false });

export function SessionProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const reload = useCallback(async () => {
    try {
      setMe(await api.get<Me>("/auth/me"));
    } catch {
      setMe(null);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { reload(); }, [reload]);
  const can = (...codes: string[]) => !!me && codes.some((c) => me.permissions.includes(c));
  const area = (a: string) => !!me && me.permissions.some((p) => p.startsWith(a + "."));
  return <SessionCtx.Provider value={{ me, loading, reload, can, area }}>{children}</SessionCtx.Provider>;
}

export const useSession = () => useContext(SessionCtx);
