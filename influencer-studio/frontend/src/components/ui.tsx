import { useEffect, type ReactNode } from "react";

export function Chip(props: {
  active: boolean;
  disabled?: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      className={`chip${props.active ? " chip--active" : ""}`}
      disabled={props.disabled && !props.active}
      aria-pressed={props.active}
      onClick={props.onClick}
    >
      {props.children}
    </button>
  );
}

export function Segmented<T extends string | number>(props: {
  value: T;
  options: { value: T; label: ReactNode }[];
  onChange: (v: T) => void;
  label?: string;
  size?: "sm" | "md";
}) {
  return (
    <div className={`segmented segmented--${props.size ?? "md"}`} role="radiogroup" aria-label={props.label}>
      {props.options.map((o) => (
        <button
          key={String(o.value)}
          type="button"
          role="radio"
          aria-checked={o.value === props.value}
          className={o.value === props.value ? "is-active" : ""}
          onClick={() => props.onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Modal(props: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  const { onClose } = props;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && props.onClose()}>
      <div className={`modal${props.wide ? " modal--wide" : ""}`} role="dialog" aria-modal="true" aria-label={props.title}>
        <header className="modal__header">
          <h2>{props.title}</h2>
          <button type="button" className="icon-btn" aria-label="Close" onClick={props.onClose}>
            ✕
          </button>
        </header>
        {props.children}
      </div>
    </div>
  );
}

export function ProgressBar({ value }: { value: number }) {
  return (
    <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(value * 100)}>
      <div className="progress__fill" style={{ width: `${Math.max(3, value * 100)}%` }} />
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <strong>{title}</strong>
      {children && <div className="muted">{children}</div>}
    </div>
  );
}

export function ErrorNote({ message }: { message: string | null }) {
  return message ? (
    <p className="error-note" role="alert">
      {message}
    </p>
  ) : null;
}
