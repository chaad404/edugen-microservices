import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ApiError } from "../../api/http";
import { labApi, type ExperimentRequest } from "../../api/lab";
import type { Estimate, Experiment, ModelInfo, Strategy, Topic } from "../../api/types";
import { Badge, Card, ErrorBox, fmt, Loading, StatusBadge } from "../../components/ui";
import { DOMAIN_LABELS } from "../../labels";

export default function ExperimentsPage() {
  const [experiments, setExperiments] = useState<Experiment[] | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    labApi.experiments().then(setExperiments).catch(setError);
  }, []);

  return (
    <div className="stack">
      <NewExperiment />
      <Card title="Experiments">
        <ErrorBox error={error} />
        {!experiments ? <Loading /> : (
          <div className="table-scroll"><table className="table">
            <thead>
              <tr><th>Name</th><th>Origin</th><th>Status</th><th>Jobs</th><th>Cost</th><th>Created</th></tr>
            </thead>
            <tbody>
              {experiments.map((e) => (
                <tr key={e.id}>
                  <td><Link to={`/lab/experiments/${e.id}`}>{e.name}</Link></td>
                  <td>{e.origin === "thesis_import" ? <Badge tone="info">thesis results</Badge> : <Badge>live</Badge>}</td>
                  <td><StatusBadge status={e.status} /></td>
                  <td>{(e.job_counts.succeeded ?? 0) + (e.job_counts.failed ?? 0)} / {e.jobs_total}</td>
                  <td>{fmt.usd(e.cost_usd)}</td>
                  <td>{fmt.date(e.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
        )}
      </Card>
    </div>
  );
}

function toggle(list: string[], value: string): string[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

function NewExperiment() {
  const navigate = useNavigate();
  const [topics, setTopics] = useState<Topic[]>([]);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [form, setForm] = useState<ExperimentRequest>({
    name: "", topic_ids: [], models: ["simulator"], strategies: ["baseline", "prompt_v2", "verify_repair"],
    questions_per_job: 5, confirm_paid: false,
  });
  const [estimate, setEstimate] = useState<Estimate | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  // One key per submission: a retried click after a timeout cannot start the experiment twice
  const idempotencyKey = useRef(crypto.randomUUID());

  useEffect(() => {
    Promise.all([labApi.topics(), labApi.models(), labApi.strategies()])
      .then(([t, m, s]) => { setTopics(t); setModels(m); setStrategies(s); })
      .catch(setError);
  }, []);

  const runnable = useMemo(() => topics.filter((t) => t.has_source_text), [topics]);
  const paid = form.models.some((alias) => models.find((m) => m.alias === alias)?.paid);
  const ready = form.name.trim() && form.topic_ids.length && form.models.length && form.strategies.length;

  useEffect(() => {
    setEstimate(null);
    if (!ready) return;
    const timer = window.setTimeout(() => labApi.estimate(form).then(setEstimate).catch(() => setEstimate(null)), 300);
    return () => window.clearTimeout(timer);
  }, [form, ready]);

  const update = (patch: Partial<ExperimentRequest>) => {
    idempotencyKey.current = crypto.randomUUID(); // a changed form is a new request
    setForm((f) => ({ ...f, ...patch }));
  };

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const experiment = await labApi.startExperiment(form, idempotencyKey.current);
      navigate(`/lab/experiments/${experiment.id}`);
    } catch (e) {
      setError(e);
      if (e instanceof ApiError && e.status !== 0) idempotencyKey.current = crypto.randomUUID();
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="New experiment">
      <div className="form grid-2">
        <label>Name<input value={form.name} onChange={(e) => update({ name: e.target.value })} placeholder="e.g. Demo: three strategies on TCP" /></label>
        <label>Questions per job
          <input type="number" min={1} max={10} value={form.questions_per_job}
            onChange={(e) => update({ questions_per_job: Number(e.target.value) })} />
        </label>
      </div>

      <h3>Topics</h3>
      <div className="checks">
        {runnable.map((t) => (
          <label key={t.topic_id} className="check">
            <input type="checkbox" checked={form.topic_ids.includes(t.topic_id)}
              onChange={() => update({ topic_ids: toggle(form.topic_ids, t.topic_id) })} />
            <span><strong>{t.title}</strong> <span className="muted">{DOMAIN_LABELS[t.domain] ?? t.domain} · {t.topic_id}</span></span>
          </label>
        ))}
      </div>
      <p className="muted small">Thesis topics are listed for their recorded results only; their source texts are not part of this project.</p>

      <h3>Models</h3>
      <div className="checks">
        {models.map((m) => (
          <label key={m.alias} className={m.available ? "check" : "check disabled"} title={m.notes ?? undefined}>
            <input type="checkbox" disabled={!m.available} checked={form.models.includes(m.alias)}
              onChange={() => update({ models: toggle(form.models, m.alias), confirm_paid: false })} />
            <span>
              <strong>{m.label}</strong> {m.params && <span className="muted">{m.params}</span>}{" "}
              {m.paid ? <Badge tone="warn">paid API</Badge> : <Badge tone="best">free</Badge>}{" "}
              {!m.available && <Badge tone="weak">needs {m.requires}</Badge>}
            </span>
          </label>
        ))}
      </div>

      <h3>Strategies</h3>
      <div className="checks">
        {strategies.map((s) => (
          <label key={s.key} className="check">
            <input type="checkbox" checked={form.strategies.includes(s.key)}
              onChange={() => update({ strategies: toggle(form.strategies, s.key) })} />
            <span><strong>{s.key}</strong> <span className="muted">{s.description}</span></span>
          </label>
        ))}
      </div>

      {estimate && (
        <p className="estimate">
          {estimate.jobs} jobs · API cost expected about <strong>{fmt.usd(estimate.estimated_cost_usd)}</strong>
          <span className="muted" title="If every call needed all its attempts and wrote the full max_tokens">
            {" "}· at most {estimate.max_cost_usd === null ? "unbounded" : fmt.usd(estimate.max_cost_usd)}
          </span>
        </p>
      )}
      {paid && (
        <label className="check confirm">
          <input type="checkbox" checked={form.confirm_paid} onChange={(e) => setForm((f) => ({ ...f, confirm_paid: e.target.checked }))} />
          <span>I understand that this run calls paid APIs.</span>
        </label>
      )}
      <ErrorBox error={error} />
      <button className="primary" disabled={!ready || busy || (paid && !form.confirm_paid)} onClick={submit}>
        {busy ? "Starting…" : "Start experiment"}
      </button>
    </Card>
  );
}
