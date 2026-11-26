import { AnimatePresence, motion } from "framer-motion";
import { Loader2, X } from "lucide-react";
import { forwardRef, type ButtonHTMLAttributes, type ReactNode, useEffect } from "react";
import type { VideoStatus } from "@/lib/api";
import { cn, STATUS } from "@/lib/utils";

type Variant = "primary" | "secondary" | "ghost" | "danger";
const variants: Record<Variant, string> = {
  primary: "grad-bg text-white shadow-glow hover:brightness-110",
  secondary: "border border-line bg-elev/70 text-fg hover:bg-elev hover:border-brand/40",
  ghost: "text-muted hover:text-fg hover:bg-elev/70",
  danger: "border border-rose-500/30 bg-rose-500/10 text-rose-400 hover:bg-rose-500/20",
};

export const Button = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant; size?: "sm" | "md" | "lg"; loading?: boolean; icon?: ReactNode;
}>(({ variant = "secondary", size = "md", loading, icon, className, children, disabled, ...rest }, ref) => (
  <button
    ref={ref}
    disabled={disabled || loading}
    className={cn(
      "inline-flex select-none items-center justify-center gap-2 whitespace-nowrap rounded-xl font-medium transition-all active:scale-[.98] disabled:pointer-events-none disabled:opacity-50",
      size === "sm" && "h-8 px-3 text-xs", size === "md" && "h-10 px-4 text-sm", size === "lg" && "h-12 px-6 text-[15px]",
      variants[variant], className,
    )}
    {...rest}
  >
    {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : icon}
    {children}
  </button>
));

export function StatusBadge({ status }: { status: VideoStatus }) {
  const s = STATUS[status];
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-semibold ring-1 ring-inset", s.tone)}>
      {s.active ? <span className="relative flex h-1.5 w-1.5"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-current opacity-60" /><span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-current" /></span>
        : <span className="h-1.5 w-1.5 rounded-full bg-current" />}
      {s.label}
    </span>
  );
}

export function Pill({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cn("inline-flex items-center gap-1 rounded-full border border-line bg-elev/70 px-2 py-0.5 text-[11px] font-medium text-muted", className)}>{children}</span>;
}

export function Progress({ value, className }: { value: number; className?: string }) {
  return (
    <div className={cn("relative h-1.5 w-full overflow-hidden rounded-full bg-elev", className)}>
      <motion.div className="absolute inset-y-0 left-0 rounded-full grad-bg" initial={false} animate={{ width: `${Math.max(2, value)}%` }} transition={{ type: "spring", stiffness: 80, damping: 20 }} />
      {value < 100 && value > 0 && <div className="absolute inset-0 -translate-x-full animate-shimmer bg-gradient-to-r from-transparent via-white/20 to-transparent" />}
    </div>
  );
}

export function Field({ label, hint, children, className }: { label: string; hint?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <label className={cn("block", className)}>
      <span className="label">{label}</span>
      {children}
      {hint && <span className="mt-1.5 block text-xs text-muted">{hint}</span>}
    </label>
  );
}

export function Toggle({ checked, onChange, label, desc }: { checked: boolean; onChange: (v: boolean) => void; label: string; desc?: string }) {
  return (
    <button type="button" onClick={() => onChange(!checked)} className="flex w-full items-center justify-between gap-4 rounded-xl border border-line bg-elev/40 p-3.5 text-left transition hover:border-brand/40">
      <span>
        <span className="block text-sm font-medium">{label}</span>
        {desc && <span className="mt-0.5 block text-xs text-muted">{desc}</span>}
      </span>
      <span className={cn("relative h-6 w-11 shrink-0 rounded-full transition", checked ? "grad-bg" : "bg-line")}>
        <motion.span layout className={cn("absolute top-0.5 h-5 w-5 rounded-full bg-white shadow", checked ? "right-0.5" : "left-0.5")} />
      </span>
    </button>
  );
}

export function Segmented<T extends string>({ value, onChange, options }: { value: T; onChange: (v: T) => void; options: { id: T; label: ReactNode }[] }) {
  return (
    <div className="inline-flex rounded-xl border border-line bg-elev/60 p-1">
      {options.map((o) => (
        <button key={o.id} type="button" onClick={() => onChange(o.id)}
          className={cn("relative rounded-lg px-3 py-1.5 text-xs font-medium transition", value === o.id ? "text-white" : "text-muted hover:text-fg")}>
          {value === o.id && <motion.span layoutId={`seg-${options.map((x) => x.id).join()}`} className="absolute inset-0 rounded-lg grad-bg" transition={{ type: "spring", stiffness: 400, damping: 32 }} />}
          <span className="relative">{o.label}</span>
        </button>
      ))}
    </div>
  );
}

export function Modal({ open, onClose, title, children, wide, footer }: {
  open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; wide?: boolean; footer?: ReactNode;
}) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    if (open) window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);
  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-50 flex items-end justify-center p-0 sm:items-center sm:p-6" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
          <motion.div
            initial={{ y: 24, scale: 0.98, opacity: 0 }} animate={{ y: 0, scale: 1, opacity: 1 }} exit={{ y: 16, opacity: 0 }}
            transition={{ type: "spring", stiffness: 380, damping: 32 }}
            className={cn("card relative flex max-h-[92vh] w-full flex-col overflow-hidden bg-panel", wide ? "sm:max-w-5xl" : "sm:max-w-xl")}
          >
            <div className="flex items-center justify-between border-b border-line px-6 py-4">
              <h3 className="font-display text-lg font-bold">{title}</h3>
              <button onClick={onClose} className="rounded-lg p-1.5 text-muted transition hover:bg-elev hover:text-fg"><X className="h-4 w-4" /></button>
            </div>
            <div className="flex-1 overflow-y-auto px-6 py-5">{children}</div>
            {footer && <div className="flex justify-end gap-2 border-t border-line bg-elev/30 px-6 py-4">{footer}</div>}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export function PageHeader({ title, desc, actions, eyebrow }: { title: string; desc?: string; actions?: ReactNode; eyebrow?: string }) {
  return (
    <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        {eyebrow && <div className="mb-2 text-xs font-semibold uppercase tracking-[.2em] text-brand">{eyebrow}</div>}
        <h1 className="font-display text-3xl font-extrabold tracking-tight">{title}</h1>
        {desc && <p className="mt-1.5 max-w-2xl text-sm text-muted">{desc}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function Empty({ icon, title, desc, action }: { icon: ReactNode; title: string; desc: string; action?: ReactNode }) {
  return (
    <div className="card flex flex-col items-center justify-center px-6 py-16 text-center">
      <div className="mb-4 grid h-14 w-14 place-items-center rounded-2xl grad-bg text-white shadow-glow">{icon}</div>
      <h3 className="font-display text-lg font-bold">{title}</h3>
      <p className="mt-1 max-w-sm text-sm text-muted">{desc}</p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("relative overflow-hidden rounded-xl bg-elev", className)}><div className="absolute inset-0 -translate-x-full animate-shimmer bg-gradient-to-r from-transparent via-white/5 to-transparent" /></div>;
}

export function PhoneFrame({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("relative mx-auto aspect-[9/19.5] w-full max-w-[300px] rounded-[2.6rem] border border-white/10 bg-black p-2.5 shadow-[0_30px_80px_-20px_rgba(139,92,246,.45)]", className)}>
      <div className="absolute left-1/2 top-3.5 z-10 h-5 w-24 -translate-x-1/2 rounded-full bg-black" />
      <div className="relative h-full w-full overflow-hidden rounded-[2.1rem] bg-zinc-900">{children}</div>
    </div>
  );
}

export function Dot({ ok, pulse }: { ok: boolean | undefined; pulse?: boolean }) {
  return (
    <span className="relative flex h-2 w-2">
      {ok && pulse && <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-50" />}
      <span className={cn("relative inline-flex h-2 w-2 rounded-full", ok === undefined ? "bg-zinc-500" : ok ? "bg-emerald-400" : "bg-rose-500")} />
    </span>
  );
}
