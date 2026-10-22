import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { labApi } from "../../api/lab";
import type { Experiment, Study } from "../../api/types";
import { Card, ErrorBox, fmt, Loading, StatusBadge } from "../../components/ui";

export default function StudiesPage() {
  const navigate = useNavigate();
  const [studies, setStudies] = useState<Study[] | null>(null);
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [form, setForm] = useState({ title: "", kind: "both", experiment_ids: [] as string[], per_cell: 1, student_items: 10, seed: 2026 });
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    labApi.studies().then(setStudies).catch(setError);
    labApi.experiments().then((list) => setExperiments(list.filter((e) => e.status !== "running"))).catch(setError);
  }, []);

  const create = async () => {
    setBusy(true);
    setError(null);
    try {
      const study = await labApi.createStudy(form);
      navigate(`/lab/studies/${study.id}`);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="stack">
      <Card title="New blind review study">
        <p className="muted">
          A stratified sample (the same number of questions from every model × strategy × domain cell) is copied to
          the Review service without the model, strategy or scores. Experts and students only see the question.
        </p>
        <div className="form grid-2">
          <label>Title<input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="e.g. Pilot expert review" /></label>
          <label>Who evaluates
            <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
              <option value="both">Experts and students</option>
              <option value="expert">Experts only (UC-200)</option>
              <option value="student">Students only (UC-300)</option>
            </select>
          </label>
          <label>Questions per cell<input type="number" min={1} max={20} value={form.per_cell} onChange={(e) => setForm({ ...form, per_cell: Number(e.target.value) })} /></label>
          <label>Questions per student<input type="number" min={1} max={40} value={form.student_items} onChange={(e) => setForm({ ...form, student_items: Number(e.target.value) })} /></label>
          <label>Sampling seed<input type="number" value={form.seed} onChange={(e) => setForm({ ...form, seed: Number(e.target.value) })} /></label>
        </div>
        <h3>From experiments</h3>
        <div className="checks">
          {experiments.map((e) => (
            <label key={e.id} className="check">
              <input type="checkbox" checked={form.experiment_ids.includes(e.id)}
                onChange={() => setForm({ ...form, experiment_ids: form.experiment_ids.includes(e.id) ? form.experiment_ids.filter((x) => x !== e.id) : [...form.experiment_ids, e.id] })} />
              <span><strong>{e.name}</strong> <span className="muted">{e.jobs_total} jobs</span></span>
            </label>
          ))}
        </div>
        <ErrorBox error={error} />
        <button className="primary" disabled={busy || !form.title || !form.experiment_ids.length} onClick={create}>
          {busy ? "Creating…" : "Create study"}
        </button>
      </Card>

      <Card title="Studies">
        {!studies ? <Loading /> : !studies.length ? <p className="muted">No studies yet.</p> : (
          <table className="table">
            <thead><tr><th>Title</th><th>Status</th><th>Questions</th><th>Expert code</th><th>Student code</th><th>Created</th></tr></thead>
            <tbody>
              {studies.map((s) => (
                <tr key={s.id}>
                  <td><Link to={`/lab/studies/${s.id}`}>{s.title}</Link></td>
                  <td><StatusBadge status={s.status} /></td>
                  <td>{s.items}</td>
                  <td><code>{s.expert_code ?? "–"}</code></td>
                  <td><code>{s.student_code ?? "–"}</code></td>
                  <td>{fmt.date(s.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
