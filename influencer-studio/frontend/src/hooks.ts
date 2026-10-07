import { createContext, useContext, useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { Health, ImageMeta, Job, Schema } from "./types";

export interface StudioContextValue {
  schema: Schema;
  health: Health | null;
  refreshHealth: () => void;
}

export const StudioContext = createContext<StudioContextValue | null>(null);

export function useStudio(): StudioContextValue {
  const ctx = useContext(StudioContext);
  if (!ctx) throw new Error("useStudio outside StudioContext");
  return ctx;
}

/** Polls a job until it finishes; `onDone` fires once with the final state. */
export function useJob<T = ImageMeta>(jobId: string | null, onDone?: (job: Job<T>) => void): Job<T> | null {
  const [job, setJob] = useState<Job<T> | null>(null);
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    let timer: number | undefined;
    const tick = async () => {
      try {
        const next = await api.job<T>(jobId);
        if (cancelled) return;
        setJob(next);
        if (next.status === "done" || next.status === "error") {
          onDoneRef.current?.(next);
          return;
        }
      } catch {
        /* backend restarting: keep polling */
      }
      timer = window.setTimeout(tick, 700);
    };
    tick();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [jobId]);

  return jobId !== null && job?.id === jobId ? job : null;
}

export function useHashRoute(): [string[], (path: string) => void] {
  const parse = () => window.location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  const [segments, setSegments] = useState(parse);
  useEffect(() => {
    const onChange = () => setSegments(parse());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return [segments, (path: string) => (window.location.hash = path)];
}

export function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(value), ms);
    return () => window.clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

/** localStorage-backed state for per-browser conveniences (drafts). Falls back to memory. */
export function usePersistentState<T>(key: string, initial: () => T): [T, (v: T | ((p: T) => T)) => void] {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = window.localStorage.getItem(key);
      return raw ? (JSON.parse(raw) as T) : initial();
    } catch {
      return initial();
    }
  });
  useEffect(() => {
    try {
      window.localStorage.setItem(key, JSON.stringify(value));
    } catch {
      /* storage unavailable */
    }
  }, [key, value]);
  return [value, setValue];
}
