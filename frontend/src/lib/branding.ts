"use client";
import { useEffect, useState } from "react";

type Branding = Record<"logo" | "logomark" | "export", { set: boolean; url: string; label: string; use: string }>;

const FALLBACK = { logo: "/brand/logo-light.svg", logomark: "/brand/logomark.svg" };
let cache: Branding | null = null;
const listeners = new Set<(b: Branding) => void>();

export async function refreshBranding() {
  try {
    const r = await fetch("/api/branding");
    if (r.ok) {
      cache = await r.json();
      listeners.forEach((l) => l(cache!));
    }
  } catch {
    /* keep placeholders */
  }
}

/** Logo URLs, versioned so a new upload shows immediately despite browser caching. */
export function useBranding() {
  const [b, setB] = useState<Branding | null>(cache);
  useEffect(() => {
    listeners.add(setB);
    if (!cache) refreshBranding();
    return () => { listeners.delete(setB); };
  }, []);
  return {
    logo: b?.logo.url || FALLBACK.logo,
    logomark: b?.logomark.url || FALLBACK.logomark,
    raw: b,
  };
}
