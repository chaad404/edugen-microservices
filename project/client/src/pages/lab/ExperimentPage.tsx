import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";

import { labApi } from "../../api/lab";
import type { Experiment, Item, LabEvent, Summary } from "../../api/types";
import { Badge, BandBadge, Card, ErrorBox, fmt, Loading, ProgressBar, StatusBadge } from "../../components/ui";
import { useEventStream } from "../../hooks/useEventStream";
import { flagLabel, PILLARS, strategyLabel } from "../../labels";
import { useModelLabel } from "./LabLayout";

export default function ExperimentPage() {
  const { id = "" } = useParams();
  const modelLabel = useModelLabel();
  const [experiment, setExperiment] = useState<Experiment | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [items, setItems] = useState<Item[] | null>(null);
  const [log, setLog] = useState<LabEvent[]>([]);
  const [tab, setTab] = useState<"summary" | "items" | "jobs">("summary");
  const [error, setError] = useState<unknown>(null);
  const refreshTimer = useRef<number | undefined>(undefined);

  const refresh = useCallback(() => {
    labApi.experiment(id).then(setExperiment).catch(setError);
    labApi.summary(id).then(setSummary).catch(() => undefined);
  }, [id]);

  useEffect(() => {
    refresh();
    labApi.events(`experiment:${id}`).then(({ events }) => setLog(events.slice(-50).reverse())).catch(() => undefined);
  }, [id, refresh]);

  useEffect(() => {
    if (tab === "items") labApi.items(id).then((page) => setItems(page.items)).catch(setError);
  }, [id, tab, experiment?.job_counts.succeeded]);

  const live = experiment?.status === "running";
  const status = useEventStream(live ? `experiment:${id}` : null, (event) => {
    setLog((current) => (current.some((e) => e.id === event.id) ? current : [event, ...current].slice(0, 50)));
    window.clearTimeout(refreshTimer.current); // several events in a burst cause one refresh
    refreshTimer.current = window.setTimeout(refresh, 400);
  });

  if (!experiment) return error ? <ErrorBox error={error} /> : <Loading />;
  const done = (experiment.job_counts.succeeded ?? 0) + (experiment.job_counts.failed ?? 0);

  return (
    <div className="stack">
      <Card
        title={<>{experiment.name} <StatusBadge status={experiment.status} /></>}
        actions={live && <Badge tone={status === "live" ? "best" : "warn"}>{status === "live" ? "● live" : status}</Badge>}
      >
        {experiment.description && <p className="muted">{experiment.description}</p>}
        <ProgressBar value={done} total={experiment.jobs_total} />
        <p className="muted small">
          {Object.entries(experiment.job_counts).map(([k, v]) => `${v} ${k}`).join(" · ")} · cost {fmt.usd(experiment.cost_usd)}
          {" · "}started {fmt.date(experiment.created_at)}
        </p>
        {live && <EventLog events={log} modelLabel={modelLabel} />}
      </Card>

      <div className="tabs" role="tablist">
        {(["summary", "items", "jobs"] as const).map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? "tab active" : "tab"} onClick={() => setTab(t)}>
            {{ summary: "Comparison", items: "Questions", jobs: "Jobs" }[t]}
          </button>
        ))}
      </div>

      {tab === "summary" && <SummaryView summary={summary} modelLabel={modelLabel} />}
      {tab === "items" && (items ? <ItemList items={items} modelLabel={modelLabel} /> : <Loading />)}
      {tab === "jobs" && <JobTable experiment={experiment} modelLabel={modelLabel} />}
    </div>
  );
}

const EVENT_TEXT: Record<string, (d: Record<string, unknown>, m: (a: string) => string) => string> = {
  "experiment.created": (d) => `Experiment accepted: ${d.jobs} jobs queued`,
  "job.dispatched": () => "Job handed to the message queue",
  "job.generated": (d, m) => `${m(String(d.model))} / ${strategyLabel(String(d.strategy))}: ${d.items} questions generated`,
  "job.succeeded": (d, m) => `${m(String(d.model))} / ${strategyLabel(String(d.strategy))}: scored (${d.flags} flags)`,
  "job.failed": (d, m) => `${m(String(d.model))} / ${strategyLabel(String(d.strategy))} failed: ${d.error_kind}`,
  "job.evaluation_delayed": () => "Evaluator unreachable: scoring will be retried",
  "experiment.completed": (d) => `Experiment ${String(d.status).replaceAll("_", " ")}`,
};

function EventLog({ events, modelLabel }: { events: LabEvent[]; modelLabel: (a: string) => string }) {
  const shown = events.filter((e) => e.type !== "job.dispatched").slice(0, 8);
  return (
    <ul className="event-log">
      {shown.map((e) => (
        <li key={e.id} className={e.type === "job.failed" ? "event-failed" : undefined}>
          {(EVENT_TEXT[e.type] ?? (() => e.type))(e.data, modelLabel)}
        </li>
      ))}
    </ul>
  );
}

function SummaryView({ summary, modelLabel }: { summary: Summary | null; modelLabel: (a: string) => string }) {
  if (!summary) return <Loading />;
  if (!summary.groups.length) return <Card><p className="muted">No scored questions yet.</p></Card>;
  return (
    <Card title="Comparison: the Three Pillars per model and strategy">
      {!summary.bands_available && <p className="error">The Evaluator is unreachable: bands are not shown.</p>}
      <div className="table-scroll">
        <table className="table compare">
          <thead>
            <tr>
              <th>Model</th><th>Strategy</th><th>n</th>
              {PILLARS.map((p) => <th key={p.key} title={p.hint}>{p.key} {p.name}</th>)}
              <th title="Share of keys at A/B/C/D; chi-square p against 25% each">Key position</th>
              <th>Item flags</th><th>Cost</th>
            </tr>
          </thead>
          <tbody>
            {summary.groups.map((g) => (
              <tr key={`${g.model}-${g.strategy}`}>
                <td><strong>{modelLabel(g.model)}</strong>{g.simulated && <Badge tone="info">simulated</Badge>}</td>
                <td>{strategyLabel(g.strategy)}</td>
                <td>{g.valid}</td>
                {PILLARS.map((p) => {
                  const pillar = g.pillars[p.key];
                  const leader = summary.leaders[p.key];
                  const isLeader = leader && leader.model === g.model && leader.strategy === g.strategy;
                  const share = p.key === "P2" ? pillar.share_in_zone : pillar.share_better_or_best;
                  return (
                    <td key={p.key} className={isLeader ? "leader" : undefined}>
                      <div>{fmt.num(pillar.mean, p.key === "P2" ? 1 : 3)} <BandBadge band={pillar.band_of_mean} /></div>
                      <div className="muted small">
                        {p.key === "P2" ? "in zone" : "Better/Best"} {fmt.pct(share)}
                        {p.key === "P3a" && pillar.share_too_close ? ` · too close ${fmt.pct(pillar.share_too_close)}` : ""}
                      </div>
                    </td>
                  );
                })}
                <td><KeyPositions counts={g.key_positions} p={g.key_position_p} /></td>
                <td className="small">
                  {Object.entries(g.flags).slice(0, 3).map(([flag, n]) => <div key={flag}>{flagLabel(flag)}: {n}</div>)}
                  {g.flags_checked === 0 && <span className="muted">checking…</span>}
                </td>
                <td>{fmt.usd(g.cost_usd)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted small">{summary.note} Framework {summary.framework_version ?? "unavailable"}; the leader of each pillar is highlighted.</p>
    </Card>
  );
}

function KeyPositions({ counts, p }: { counts: Record<string, number>; p: number | null }) {
  const total = Object.values(counts).reduce((a, b) => a + b, 0) || 1;
  return (
    <div className="keypos" title={`chi-square p = ${fmt.num(p, 4)}`}>
      {["A", "B", "C", "D"].map((label) => (
        <div key={label} className="keypos-bar">
          <div className="keypos-fill" style={{ height: `${(100 * (counts[label] ?? 0)) / total}%` }} />
          <span>{label}</span>
        </div>
      ))}
      {p !== null && p < 0.05 && <Badge tone="warn">biased</Badge>}
    </div>
  );
}

function ItemList({ items, modelLabel }: { items: Item[]; modelLabel: (a: string) => string }) {
  const [model, setModel] = useState("");
  const models = [...new Set(items.map((i) => i.model))];
  const shown = items.filter((i) => !model || i.model === model);
  return (
    <Card title={`Questions (${shown.length})`} actions={
      <select value={model} onChange={(e) => setModel(e.target.value)}>
        <option value="">All models</option>
        {models.map((m) => <option key={m} value={m}>{modelLabel(m)}</option>)}
      </select>
    }>
      <div className="items">
        {shown.map((item) => (
          <article key={item.id} className="item">
            <header className="muted small">
              {item.topic_id} · {modelLabel(item.model)} · {strategyLabel(item.strategy)}
              {item.metrics_source === "thesis" && <Badge tone="info">scored by the thesis</Badge>}
            </header>
            <p className="question">{item.question}</p>
            <ol className="options">
              {(["A", "B", "C", "D"] as const).map((label) => (
                <li key={label} className={label === item.answer ? "key" : undefined}>
                  <strong>{label}.</strong> {item.options[label]}
                </li>
              ))}
            </ol>
            <div className="metrics">
              {PILLARS.map((p) => (
                <span key={p.key} title={p.hint}>
                  {p.key} {fmt.num(item.metrics[p.metric], p.key === "P2" ? 1 : 3)} <BandBadge band={item.bands?.[p.key]} />
                </span>
              ))}
            </div>
            {item.flags && item.flags.length > 0 && (
              <div className="flags">{item.flags.map((f) => <Badge key={f} tone="warn">{flagLabel(f)}</Badge>)}</div>
            )}
          </article>
        ))}
      </div>
    </Card>
  );
}

function JobTable({ experiment, modelLabel }: { experiment: Experiment; modelLabel: (a: string) => string }) {
  return (
    <Card title="Jobs: one per topic × model × strategy">
      <div className="table-scroll">
        <table className="table">
          <thead>
            <tr><th>Topic</th><th>Model</th><th>Strategy</th><th>Status</th><th>Calls</th><th>Tokens</th><th>Cost</th><th>Latency</th><th>Notes</th></tr>
          </thead>
          <tbody>
            {(experiment.jobs ?? []).map((j) => (
              <tr key={j.id}>
                <td>{j.topic_id}</td>
                <td>{modelLabel(j.model)}{j.simulated && <Badge tone="info">simulated</Badge>}</td>
                <td>{strategyLabel(j.strategy)}</td>
                <td><StatusBadge status={j.status} /></td>
                <td>{j.calls || "–"}</td>
                <td>{j.prompt_tokens + j.completion_tokens || "–"}</td>
                <td>{fmt.usd(j.cost_usd)}</td>
                <td>{j.latency_seconds ? `${j.latency_seconds.toFixed(1)} s` : "–"}</td>
                <td className="small">
                  {j.error_kind && <span className="error-text">{j.error_kind}: {j.error}</span>}
                  {j.strategy_status && j.strategy_status !== "valid" && <Badge>{j.strategy_status.replaceAll("_", " ")}</Badge>}
                  {j.evaluation_attempts > 0 && j.status === "generated" && <Badge tone="warn">waiting for the Evaluator</Badge>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
