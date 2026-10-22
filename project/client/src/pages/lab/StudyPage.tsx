import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";

import { labApi } from "../../api/lab";
import type { StudyAnalytics } from "../../api/types";
import { Badge, Card, ErrorBox, fmt, Loading, StatusBadge } from "../../components/ui";
import { useEventStream } from "../../hooks/useEventStream";
import { strategyLabel } from "../../labels";
import { useModelLabel } from "./LabLayout";

const HUMAN_LABELS: Record<string, string> = {
  expert_relevance: "Expert relevance", expert_distractors: "Expert distractor quality",
  expert_difficulty: "Expert difficulty", student_p_value: "Student p-value (share correct)",
  student_perceived_difficulty: "Student perceived difficulty",
};

export default function StudyPage() {
  const { id = "" } = useParams();
  const modelLabel = useModelLabel();
  const [data, setData] = useState<StudyAnalytics | null>(null);
  const [error, setError] = useState<unknown>(null);
  const timer = useRef<number | undefined>(undefined);

  const refresh = useCallback(() => labApi.analytics(id).then(setData).catch(setError), [id]);
  useEffect(() => { refresh(); }, [refresh]);

  const status = useEventStream(data?.study.status === "open" ? `study:${id}` : null, () => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(refresh, 600);
  });

  const republish = async () => {
    setError(null);
    try {
      await labApi.republish(id);
      refresh();
    } catch (e) {
      setError(e);
    }
  };

  if (!data) return error ? <ErrorBox error={error} /> : <Loading />;
  const { study, progress } = data;
  const origin = window.location.origin;

  return (
    <div className="stack">
      <Card title={<>{study.title} <StatusBadge status={study.status} /></>}
        actions={study.status === "open" && <Badge tone={status === "live" ? "best" : "warn"}>{status === "live" ? "● live" : status}</Badge>}>
        <ErrorBox error={error} />
        {study.status === "draft" ? (
          <div>
            <p className="error">Not yet handed to the Review service: {study.publish_error}</p>
            <button className="primary" onClick={republish}>Retry</button>
          </div>
        ) : (
          <div className="codes">
            {study.expert_code && <Code label="Expert reviewers" code={study.expert_code} link={`${origin}/review?code=${study.expert_code}`} />}
            {study.student_code && <Code label="Students" code={study.student_code} link={`${origin}/quiz?code=${study.student_code}`} />}
          </div>
        )}
        <p className="muted small">
          {study.items} questions (seed {study.seed}, {study.per_cell} per model × strategy × domain cell) · {progress.raters} raters,
          {" "}{progress.ratings} ratings · {progress.participants} students, {progress.answers} answers
        </p>
      </Card>

      <Card title="Human versus automatic evaluation, per model and strategy">
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Model</th><th>Strategy</th><th>n</th>
                <th>Expert relevance</th><th>Clarity</th><th>Difficulty</th><th>Distractors</th><th>Key correct</th>
                <th>Student p</th><th>Time</th><th>Helpfulness</th>
                <th>P1 align.</th><th>P3a plaus.</th>
              </tr>
            </thead>
            <tbody>
              {data.groups.map((g) => (
                <tr key={`${g.model}-${g.strategy}`}>
                  <td>{modelLabel(g.model)}</td><td>{strategyLabel(g.strategy)}</td><td>{g.items}</td>
                  <td>{fmt.num(g.expert.relevance, 2)}</td><td>{fmt.num(g.expert.clarity, 2)}</td>
                  <td>{fmt.num(g.expert.difficulty, 2)}</td><td>{fmt.num(g.expert.distractors, 2)}</td>
                  <td>{fmt.pct(g.expert.key_correct_rate)}</td>
                  <td>{fmt.num(g.student.p_value, 2)}</td>
                  <td>{g.student.mean_time_ms ? `${(g.student.mean_time_ms / 1000).toFixed(1)} s` : "–"}</td>
                  <td>{fmt.num(g.student.helpfulness, 2)}</td>
                  <td>{fmt.num(g.automatic.alignment)}</td><td>{fmt.num(g.automatic.plausibility)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="grid-2">
        <Card title="Inter-rater agreement (Krippendorff's alpha)">
          <table className="table">
            <thead><tr><th>Dimension</th><th>Level</th><th>Items rated twice</th><th>Alpha</th></tr></thead>
            <tbody>
              {Object.entries(data.agreement).map(([dim, a]) => (
                <tr key={dim}><td>{dim.replace("_", " ")}</td><td>{a.level}</td><td>{a.items_with_2_raters}</td><td>{fmt.num(a.alpha)}</td></tr>
              ))}
            </tbody>
          </table>
        </Card>
        <Card title="Do the pillars agree with people? (Spearman)">
          <table className="table">
            <thead><tr><th>Human judgement</th><th>Automatic metric</th><th>n</th><th>rho</th></tr></thead>
            <tbody>
              {data.correlations.map((c) => (
                <tr key={`${c.human}-${c.metric}`}>
                  <td>{HUMAN_LABELS[c.human] ?? c.human}</td><td>{c.metric}</td><td>{c.n}</td><td>{fmt.num(c.spearman_rho)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted small">{data.note}</p>
        </Card>
      </div>
    </div>
  );
}

function Code({ label, code, link }: { label: string; code: string; link: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => navigator.clipboard?.writeText(link).then(() => setCopied(true));
  return (
    <div className="code-box">
      <div className="muted small">{label}</div>
      <code className="big-code">{code}</code>
      <button className="link" onClick={copy}>{copied ? "Link copied" : "Copy link"}</button>
    </div>
  );
}
