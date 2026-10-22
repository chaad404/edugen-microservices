import type { ReactNode } from "react";

import { ApiError } from "../api/http";
import type { Band } from "../api/types";

export function Card({ title, actions, children }: { title?: ReactNode; actions?: ReactNode; children: ReactNode }) {
  return (
    <section className="card">
      {(title || actions) && (
        <header className="card-header">
          {title && <h2>{title}</h2>}
          {actions && <div className="card-actions">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

export function Badge({ tone = "neutral", children, title }: { tone?: string; children: ReactNode; title?: string }) {
  return <span className={`badge badge-${tone}`} title={title}>{children}</span>;
}

const BAND_TONE: Record<Band, string> = {
  Best: "best", Better: "better", "Good enough": "ok", Weak: "weak",
  "Too close": "warn", "Too simple": "warn", "Too dense": "warn",
};

export function BandBadge({ band }: { band: Band | null | undefined }) {
  if (!band) return <span className="muted">n/a</span>;
  return <Badge tone={BAND_TONE[band]}>{band}</Badge>;
}

const STATUS_TONE: Record<string, string> = {
  queued: "neutral", dispatched: "info", generated: "info", succeeded: "best", failed: "weak",
  running: "info", completed: "best", completed_with_failures: "warn", draft: "warn", open: "best",
};

export function StatusBadge({ status }: { status: string }) {
  return <Badge tone={STATUS_TONE[status] ?? "neutral"}>{status.replaceAll("_", " ")}</Badge>;
}

export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  const text = error instanceof ApiError ? error.message : String(error);
  return <div className="error" role="alert">{text}</div>;
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return <p className="muted">{label}</p>;
}

export function ProgressBar({ value, total }: { value: number; total: number }) {
  const pct = total ? Math.round((100 * value) / total) : 0;
  return (
    <div className="progress" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
      <div className="progress-fill" style={{ width: `${pct}%` }} />
      <span className="progress-label">{value} / {total}</span>
    </div>
  );
}

export function Likert({ name, label, hint, value, onChange, low, high }: {
  name: string; label: string; hint?: string; value: number | null; onChange: (v: number) => void; low: string; high: string;
}) {
  return (
    <fieldset className="likert">
      <legend>{label}{hint && <span className="muted"> · {hint}</span>}</legend>
      <div className="likert-scale">
        <span className="muted small">{low}</span>
        {[1, 2, 3, 4, 5].map((n) => (
          <label key={n} className={value === n ? "likert-option selected" : "likert-option"}>
            <input type="radio" name={name} value={n} checked={value === n} onChange={() => onChange(n)} />
            {n}
          </label>
        ))}
        <span className="muted small">{high}</span>
      </div>
    </fieldset>
  );
}

export const fmt = {
  num: (v: number | null | undefined, digits = 3) => (v === null || v === undefined ? "–" : v.toFixed(digits)),
  pct: (v: number | null | undefined) => (v === null || v === undefined ? "–" : `${Math.round(v * 100)}%`),
  usd: (v: number | null | undefined) => (v === null || v === undefined ? "–" : `$${v.toFixed(v < 0.01 && v > 0 ? 5 : 4)}`),
  date: (v: string | null | undefined) => (v ? new Date(v).toLocaleString() : "–"),
};
