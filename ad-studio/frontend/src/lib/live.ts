import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { toast } from "sonner";
import type { Campaign, Video } from "./api";

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
      } else if (msg.type === "due") {
        const d = msg.data as { id: number; hook: string; platform: string };
        toast(`Yayın zamanı: #${d.id}`, { description: `${d.platform} · ${d.hook}` });
      } else if (msg.type === "queue") softRefetch();
    };
    return () => { es.close(); window.clearTimeout(refetchTimer); };
  }, [qc]);
}
