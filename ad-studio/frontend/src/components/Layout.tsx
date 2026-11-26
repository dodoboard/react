import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import {
  BadgeDollarSign, Bot, CalendarDays, Clapperboard, Command, Cpu, Film, LayoutDashboard, ListVideo, Menu, Moon, Package,
  Settings, Sparkles, Sun, X,
} from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { cn, gb } from "@/lib/utils";
import { Dot } from "./ui";

const NAV = [
  { to: "/", label: "Genel Bakış", icon: LayoutDashboard },
  { to: "/studio", label: "Stüdyo", icon: Sparkles, accent: true },
  { to: "/products", label: "Ürünler", icon: Package },
  { to: "/campaigns", label: "Kampanyalar", icon: Clapperboard },
  { to: "/queue", label: "Üretim Kuyruğu", icon: ListVideo },
  { to: "/library", label: "Kütüphane", icon: Film },
  { to: "/calendar", label: "Yayın Takvimi", icon: CalendarDays },
  { to: "/autopilot", label: "Otopilot", icon: Bot },
  { to: "/revenue", label: "Gelir & ROI", icon: BadgeDollarSign },
  { to: "/settings", label: "Ayarlar", icon: Settings },
];

function useTheme() {
  const [dark, setDark] = useState(() => {
    try { return localStorage.getItem("theme") !== "light"; } catch { return true; }
  });
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    try { localStorage.setItem("theme", dark ? "dark" : "light"); } catch { /* private mode */ }
  }, [dark]);
  return [dark, setDark] as const;
}

function Brand() {
  return (
    <div className="flex items-center gap-2.5 px-2">
      <div className="grid h-9 w-9 place-items-center rounded-xl grad-bg shadow-glow">
        <svg viewBox="0 0 24 24" className="h-4 w-4 fill-white"><path d="M8 5.5v13l10.5-6.5z" /></svg>
      </div>
      <div className="leading-tight">
        <div className="font-display text-[15px] font-extrabold tracking-tight">AdForge</div>
        <div className="text-[10px] font-semibold uppercase tracking-[.18em] text-muted">Local Studio</div>
      </div>
    </div>
  );
}

function SideNav({ onNav }: { onNav?: () => void }) {
  const { data: h } = useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: 10_000 });
  const vramUsed = h?.comfy.vram_total ? 100 - (100 * (h.comfy.vram_free ?? 0)) / h.comfy.vram_total : 0;
  return (
    <div className="flex h-full flex-col gap-6 p-4">
      <Brand />
      <nav className="flex flex-1 flex-col gap-0.5">
        {NAV.map(({ to, label, icon: Icon, accent }) => (
          <NavLink key={to} to={to} end={to === "/"} onClick={onNav}
            className={({ isActive }) => cn(
              "group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition",
              isActive ? "text-fg" : "text-muted hover:bg-elev/60 hover:text-fg",
            )}>
            {({ isActive }) => (
              <>
                {isActive && <motion.span layoutId="nav-active" className="absolute inset-0 rounded-xl border border-brand/30 bg-gradient-to-r from-brand/15 to-brand-2/5" transition={{ type: "spring", stiffness: 400, damping: 34 }} />}
                <Icon className={cn("relative h-[18px] w-[18px]", accent && !isActive && "text-brand", isActive && "text-brand")} />
                <span className="relative">{label}</span>
                {accent && <span className="relative ml-auto rounded-md grad-bg px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-white">Üret</span>}
              </>
            )}
          </NavLink>
        ))}
      </nav>
      <div className="card space-y-3 p-3.5">
        <div className="flex items-center gap-2 text-xs font-semibold"><Cpu className="h-3.5 w-3.5 text-brand" /> {h?.comfy.gpu || "GPU"}</div>
        {h?.comfy.vram_total ? (
          <div>
            <div className="mb-1 flex justify-between text-[11px] text-muted"><span>VRAM</span><span>{gb(h.comfy.vram_total - (h.comfy.vram_free ?? 0))} / {gb(h.comfy.vram_total)} GB</span></div>
            <div className="h-1.5 overflow-hidden rounded-full bg-elev"><div className="h-full rounded-full grad-bg transition-all" style={{ width: `${vramUsed}%` }} /></div>
          </div>
        ) : null}
        <div className="grid grid-cols-3 gap-1.5 text-[11px]">
          {([["Ollama", h?.ollama.ok], ["ComfyUI", h?.comfy.ok], ["Ses", h?.tts.ok]] as const).map(([n, ok]) => (
            <div key={n} className="flex items-center gap-1.5 rounded-lg bg-elev/60 px-2 py-1.5 text-muted"><Dot ok={h ? !!ok : undefined} pulse />{n}</div>
          ))}
        </div>
        {h?.dry_run && <div className="rounded-lg bg-amber-500/10 px-2 py-1.5 text-center text-[11px] font-medium text-amber-500">DEMO modu (dry-run)</div>}
      </div>
    </div>
  );
}

function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [i, setI] = useState(0);
  const items = NAV.filter((n) => n.label.toLowerCase().includes(q.toLowerCase()));
  useEffect(() => { if (open) { setQ(""); setI(0); } }, [open]);
  const go = (to: string) => { nav(to); onClose(); };
  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-[60] flex items-start justify-center bg-black/50 p-4 pt-[15vh] backdrop-blur-sm" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
          <motion.div initial={{ scale: 0.96, y: -8 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.97 }} className="card w-full max-w-lg overflow-hidden bg-panel" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center gap-3 border-b border-line px-4">
              <Command className="h-4 w-4 text-muted" />
              <input autoFocus value={q} onChange={(e) => { setQ(e.target.value); setI(0); }}
                onKeyDown={(e) => {
                  if (e.key === "ArrowDown") { e.preventDefault(); setI((x) => Math.min(x + 1, items.length - 1)); }
                  if (e.key === "ArrowUp") { e.preventDefault(); setI((x) => Math.max(x - 1, 0)); }
                  if (e.key === "Enter" && items[i]) go(items[i].to);
                }}
                placeholder="Sayfaya git…" className="h-14 flex-1 bg-transparent text-sm outline-none placeholder:text-muted" />
              <kbd className="rounded-md border border-line px-1.5 py-0.5 text-[10px] text-muted">ESC</kbd>
            </div>
            <div className="max-h-80 overflow-y-auto p-2">
              {items.map((n, idx) => (
                <button key={n.to} onMouseEnter={() => setI(idx)} onClick={() => go(n.to)}
                  className={cn("flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm", idx === i ? "bg-brand/15 text-fg" : "text-muted")}>
                  <n.icon className="h-4 w-4" /> {n.label}
                </button>
              ))}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export default function Layout({ children }: { children: ReactNode }) {
  const [dark, setDark] = useTheme();
  const [mobile, setMobile] = useState(false);
  const [palette, setPalette] = useState(false);
  const loc = useLocation();
  const { data: h } = useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: 10_000 });

  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setPalette((p) => !p); }
      if (e.key === "Escape") setPalette(false);
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, []);

  const active = h?.queue.current.length ?? 0;
  return (
    <div className="flex min-h-full">
      <aside className="sticky top-0 hidden h-screen w-[264px] shrink-0 border-r border-line/60 bg-panel/40 backdrop-blur-xl lg:block"><SideNav /></aside>
      <AnimatePresence>
        {mobile && (
          <motion.div className="fixed inset-0 z-40 lg:hidden" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <div className="absolute inset-0 bg-black/60" onClick={() => setMobile(false)} />
            <motion.aside initial={{ x: -280 }} animate={{ x: 0 }} exit={{ x: -280 }} transition={{ type: "spring", damping: 30, stiffness: 300 }} className="absolute inset-y-0 left-0 w-[272px] border-r border-line bg-panel">
              <button className="absolute right-3 top-5 rounded-lg p-1.5 text-muted" onClick={() => setMobile(false)}><X className="h-4 w-4" /></button>
              <SideNav onNav={() => setMobile(false)} />
            </motion.aside>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-line/60 bg-bg/70 px-4 backdrop-blur-xl sm:px-8">
          <button className="rounded-lg p-2 text-muted hover:bg-elev lg:hidden" onClick={() => setMobile(true)}><Menu className="h-5 w-5" /></button>
          <button onClick={() => setPalette(true)} className="flex h-10 w-full max-w-sm items-center gap-3 rounded-xl border border-line bg-elev/50 px-3 text-sm text-muted transition hover:border-brand/40">
            <Command className="h-4 w-4" /><span className="flex-1 text-left">Ara veya git…</span>
            <kbd className="hidden rounded-md border border-line px-1.5 text-[10px] sm:block">Ctrl K</kbd>
          </button>
          <div className="ml-auto flex items-center gap-2">
            {active > 0 && (
              <NavLink to="/queue" className="hidden items-center gap-2 rounded-xl border border-brand/30 bg-brand/10 px-3 py-2 text-xs font-semibold text-brand sm:flex">
                <span className="relative flex h-2 w-2"><span className="absolute h-full w-full animate-ping rounded-full bg-brand opacity-60" /><span className="relative h-2 w-2 rounded-full bg-brand" /></span>
                {active} video işleniyor
              </NavLink>
            )}
            <span className="hidden rounded-lg border border-line px-2 py-1.5 text-[11px] font-mono text-muted md:block">{h?.encoder === "h264_nvenc" ? "NVENC" : h?.encoder ?? "…"}</span>
            <button onClick={() => setDark(!dark)} className="grid h-10 w-10 place-items-center rounded-xl border border-line bg-elev/50 text-muted transition hover:text-fg">
              {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
          </div>
        </header>
        <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-8 sm:px-8">
          <motion.div key={loc.pathname} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}>
            {children}
          </motion.div>
        </main>
      </div>
      <CommandPalette open={palette} onClose={() => setPalette(false)} />
    </div>
  );
}
