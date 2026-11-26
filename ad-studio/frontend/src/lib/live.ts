import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { toast } from "sonner";
import type { Campaign, Episode, Video } from "./api";

/** One SSE connection; patches react-query caches in place so lists update without refetch storms. */
export function useLiveEvents() {
  const qc = useQueryClient();
  useEffect(() => {
    const es = new EventSource("/api/events");
    let refetchTimer: number | undefined;
    const notified = new Set<string>();
    let missing = false;
    const softRefetch = () => {
      window.clearTimeout(refetchTimer);
      refetchTimer = window.setTimeout(() => {
        qc.invalidateQueries({ queryKey: ["campaigns"] });
        qc.invalidateQueries({ queryKey: ["summary"] });
        qc.invalidateQueries({ queryKey: ["health"] });
        if (missing) { missing = false; qc.invalidateQueries({ queryKey: ["videos"] }); }
      }, 800);
    };
    es.onmessage = (e) => {
      const msg = JSON.parse(e.data) as { type: string; data: unknown };
      if (msg.type === "video") {
        const v = msg.data as Video;
        qc.setQueriesData<Video[]>({ queryKey: ["videos"] }, (old) => {
          if (!old) return old;
          const i = old.findIndex((x) => x.id === v.id);
          if (i === -1) { missing = true; return old; }
          const next = old.slice();
          next[i] = { ...old[i], ...v };
          return next;
        });
        qc.setQueryData<Campaign>(["campaign", v.campaign_id], (old) =>
          old?.videos ? { ...old, videos: old.videos.map((x) => (x.id === v.id ? { ...x, ...v } : x)) } : old);
        qc.setQueryData<Video>(["video", v.id], (old) => (old ? { ...old, ...v } : old));
        const key = `${v.id}:${v.status}`;
        if ((v.status === "done" || v.status === "failed") && !notified.has(key)) {
          notified.add(key);
          if (v.status === "done") toast.success(`Video #${v.id} hazır`, { description: v.hook });
          else toast.error(`Video #${v.id} başarısız`, { description: v.error.slice(0, 140) });
        } else if (v.status === "queued") {
          notified.delete(`${v.id}:done`);
          notified.delete(`${v.id}:failed`);
        }
        softRefetch();
      } else if (msg.type === "episode") {
        const e = msg.data as Episode;
        qc.setQueriesData<Episode[]>({ queryKey: ["episodes"] }, (old) => {
          if (!old) return old;
          const i = old.findIndex((x) => x.id === e.id);
          if (i === -1) { qc.invalidateQueries({ queryKey: ["episodes"] }); return old; }
          const next = old.slice();
          next[i] = { ...old[i], ...e };
          return next;
        });
        qc.setQueryData<Episode>(["episode", e.id], (old) => (old ? { ...old, ...e } : old));
        const key = `ep${e.id}:${e.status}`;
        if (["ready", "needs_review", "failed"].includes(e.status) && !notified.has(key)) {
          notified.add(key);
          if (e.status === "ready") toast.success(`Bölüm hazır: ${e.title}`);
          else if (e.status === "needs_review") toast.warning(`İncelemede: ${e.title}`, { description: e.error.slice(0, 140) });
          else toast.error(`Bölüm başarısız: ${e.title}`, { description: e.error.slice(0, 140) });
        }
        window.clearTimeout(refetchTimer);
        refetchTimer = window.setTimeout(() => { qc.invalidateQueries({ queryKey: ["channels"] }); qc.invalidateQueries({ queryKey: ["upcoming"] }); }, 1000);
      } else if (msg.type === "published") {
        const d = msg.data as { channel: string; yt_id: string };
        toast.success(`YouTube'a yüklendi · ${d.channel}`, { description: d.yt_id });
      } else if (msg.type === "due") {
        const d = msg.data as { id: number; hook: string; platform: string };
        toast(`Yayın zamanı: #${d.id}`, { description: `${d.platform} · ${d.hook}` });
      } else if (msg.type === "queue") softRefetch();
    };
    return () => { es.close(); window.clearTimeout(refetchTimer); };
  }, [qc]);
}
