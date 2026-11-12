import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";

import { labApi } from "../../api/lab";
import type { StudyAnalytics, StudyItemResult } from "../../api/types";
import { Badge, Card, ErrorBox, fmt, Loading, StatusBadge } from "../../components/ui";
import { useEventStream } from "../../hooks/useEventStream";
import { strategyLabel } from "../../labels";
import { useModelLabel } from "./LabLayout";

const HUMAN_LABELS: Record<string, string> = {
  expert_relevance: "Expert relevance", expert_distractors: "Expert distractor quality",
  expert_difficulty: "Expert difficulty", student_p_value: "Student p-value (share correct)",
  student_perceived_difficulty: "Student perceived difficulty",
};

const count = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

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
          {study.items} questions (seed {study.seed}, {study.per_cell} per model × strategy × domain cell) · {count(progress.raters, "rater")},
          {" "}{count(progress.ratings, "rating")} · {count(progress.participants, "student")}, {count(progress.answers, "answer")}
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
          <div className="table-scroll"><table className="table">
            <thead><tr><th>Dimension</th><th>Level</th><th>Items rated twice</th><th>Alpha</th></tr></thead>
            <tbody>
              {Object.entries(data.agreement).map(([dim, a]) => (
                <tr key={dim}><td>{dim.replace("_", " ")}</td><td>{a.level}</td><td>{a.items_with_2_raters}</td><td>{fmt.num(a.alpha)}</td></tr>
              ))}
            </tbody>
          </table></div>
        </Card>
        <Card title="Do the pillars agree with people? (Spearman)">
          <div className="table-scroll"><table className="table">
            <thead><tr><th>Human judgement</th><th>Automatic metric</th><th>n</th><th>rho</th></tr></thead>
            <tbody>
              {data.correlations.map((c) => (
                <tr key={`${c.human}-${c.metric}`}>
                  <td>{HUMAN_LABELS[c.human] ?? c.human}</td><td>{c.metric}</td><td>{c.n}</td><td>{fmt.num(c.spearman_rho)}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
          <p className="muted small">{data.note}</p>
        </Card>
      </div>

      <ItemResults items={data.items} modelLabel={modelLabel} />
    </div>
  );
}

const DIFFICULTY_NOTE = { too_hard: "few correct: unclear or wrong key?", too_easy: "almost all correct" } as const;

/** Classic item analysis next to the expert view: which questions worked, and which options nobody chose. */
function ItemResults({ items, modelLabel }: { items: StudyItemResult[]; modelLabel: (alias: string) => string }) {
  const [onlyWithData, setOnlyWithData] = useState(false);
  const numbered = items.map((item, index) => ({ item, number: index + 1 }));  // the number stays when rows are hidden
  const withData = numbered.filter(({ item }) => item.expert.ratings > 0 || item.student.attempts > 0);
  const shown = onlyWithData ? withData : numbered;
  return (
    <Card title="Per question: expert ratings and student answers"
      actions={
        <label className="check inline">
          <input type="checkbox" checked={onlyWithData} onChange={(e) => setOnlyWithData(e.target.checked)} />
          <span>Only questions with data ({withData.length} of {items.length})</span>
        </label>
      }>
      <div className="table-scroll">
        <table className="table">
          <thead>
            <tr>
              <th>#</th><th>Question</th>
              <th title="Number of expert ratings">Ratings</th><th>Relevance</th><th>Clarity</th><th>Difficulty</th><th>Distractors</th>
              <th title="Share of experts who found the marked answer correct (unsure not counted)">Key correct</th>
              <th title="Number of student answers">Answers</th>
              <th title="Share of students who answered correctly">Correct (p)</th>
              <th title="How often each option was chosen, in the original labels; the key is marked">Options chosen</th>
            </tr>
          </thead>
          <tbody>
            {shown.map(({ item, number }) => (
              <tr key={item.item_ref}>
                <td>{number}</td>
                <td className="item-cell">
                  <div>{item.question}</div>
                  <div className="muted small">{modelLabel(item.model)} · {strategyLabel(item.strategy)} · {item.topic_id}</div>
                  {item.expert.unusable > 0 && <Badge tone="weak">unusable × {item.expert.unusable}</Badge>}
                  {item.expert.comments.map((comment, n) => <div key={n} className="muted small comment">“{comment}”</div>)}
                </td>
                <td>{item.expert.ratings || "–"}</td>
                <td>{fmt.num(item.expert.relevance, 1)}</td><td>{fmt.num(item.expert.clarity, 1)}</td>
                <td>{fmt.num(item.expert.difficulty, 1)}</td><td>{fmt.num(item.expert.distractors, 1)}</td>
                <td>{fmt.pct(item.expert.key_correct_rate)}</td>
                <td>{item.student.attempts || "–"}</td>
                <td>
                  {fmt.num(item.student.p_value, 2)}
                  {item.student.difficulty_note && <div><Badge tone="warn">{DIFFICULTY_NOTE[item.student.difficulty_note]}</Badge></div>}
                </td>
                <td>
                  {item.student.attempts > 0 && (
                    <div className="option-counts">
                      {(["A", "B", "C", "D"] as const).map((label) => (
                        <span key={label} className={label === item.answer ? "option-key" : undefined}
                          title={label === item.answer ? "The marked answer" : undefined}>
                          {label} {item.student.option_counts[label] ?? 0}
                        </span>
                      ))}
                    </div>
                  )}
                  {item.student.dead_distractors.length > 0 && (
                    <Badge tone="warn" title="Wrong options that no student chose: they do not work as distractors">
                      unused: {item.student.dead_distractors.join(", ")}
                    </Badge>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!shown.length && <p className="muted">No ratings or answers yet.</p>}
      <p className="muted small">
        Expert columns are means on the 1–5 scales. The operator sees the model here; reviewers and students never do.
      </p>
    </Card>
  );
}

function Code({ label, code, link }: { label: string; code: string; link: string }) {
  const [copied, setCopied] = useState(false);
  // The clipboard API exists only on https and localhost; elsewhere the visible link is copied by hand
  const canCopy = Boolean(navigator.clipboard);
  const copy = () => navigator.clipboard.writeText(link).then(() => setCopied(true));
  return (
    <div className="code-box">
      <div className="muted small">{label}</div>
      <code className="big-code">{code}</code>
      <a className="share-link" href={link} target="_blank" rel="noreferrer">{link}</a>
      {canCopy && <button className="link" onClick={copy}>{copied ? "Link copied" : "Copy link"}</button>}
    </div>
  );
}
