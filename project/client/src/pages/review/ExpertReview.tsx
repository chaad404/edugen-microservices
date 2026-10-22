import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { ApiError } from "../../api/http";
import { codeRole, reviewApi, sessionStore } from "../../api/review";
import type { Rating, ReviewItem, SessionInfo } from "../../api/types";
import { Card, ErrorBox, Likert, Loading, ProgressBar } from "../../components/ui";

const EMPTY: Partial<Rating> = { key_correct: undefined, unusable: false };

export default function ExpertReview() {
  const [params] = useSearchParams();
  const [code, setCode] = useState(params.get("code") ?? "");
  const [token, setToken] = useState<string | null>(() => (code ? sessionStore.get(code) : null));
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [instructions, setInstructions] = useState("");
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    if (!token) return;
    reviewApi.me(token).then(setSession).catch((e) => {
      if (e instanceof ApiError && e.status === 401) {
        sessionStore.clear(code);
        setToken(null);
      } else setError(e);
    });
  }, [token, code]);

  if (!token) return <Join code={code} setCode={setCode} onJoined={(t, text) => { setToken(t); setInstructions(text); }} />;
  if (!session) return error ? <ErrorBox error={error} /> : <Loading />;
  return <Reviewer token={token} session={session} instructions={instructions} />;
}

function Join({ code, setCode, onJoined }: { code: string; setCode: (c: string) => void; onJoined: (token: string, instructions: string) => void }) {
  const [name, setName] = useState("");
  const [error, setError] = useState<unknown>(null);
  const studentCode = codeRole(code) === "student";
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      const result = await reviewApi.join(code, { rater_name: name });
      if (result.role !== "expert") throw new Error("This is a student code. Open the student quiz instead.");
      sessionStore.set(code, result.token);
      onJoined(result.token, result.instructions);
    } catch (e) {
      setError(e);
    }
  };
  return (
    <div className="narrow">
      <Card title="Expert review">
        <form className="form" onSubmit={submit}>
          <label>Study code<input value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="EXP-…" /></label>
          <label>Your pseudonym<input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Rater 1" /></label>
          <p className="muted small">Use the same pseudonym to continue later. The model behind each question is hidden.</p>
          {studentCode && (
            <div className="error" role="alert">This is a student quiz code. <Link to={`/quiz?code=${code}`}>Open the student quiz</Link></div>
          )}
          <ErrorBox error={error} />
          <button className="primary" disabled={!code || studentCode || name.trim().length < 2}>Start</button>
        </form>
      </Card>
    </div>
  );
}

function Reviewer({ token, session, instructions }: { token: string; session: SessionInfo; instructions: string }) {
  const [item, setItem] = useState<ReviewItem | null>(null);
  const [position, setPosition] = useState({ at: 0, total: session.total, rated: session.done });
  const [rating, setRating] = useState<Partial<Rating>>(EMPTY);
  const [list, setList] = useState<Array<{ position: number; item_ref: string; rated: boolean }>>([]);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [saving, setSaving] = useState(false);

  const loadList = useCallback(() => reviewApi.expertItems(token).then((r) => setList(r.items)).catch(setError), [token]);

  const loadNext = useCallback(async () => {
    const step = await reviewApi.expertNext(token);
    setDone(step.done);
    setPosition({ at: step.position ?? step.total, total: step.total, rated: step.rated });
    setItem(step.item ?? null);
    setRating(EMPTY);
  }, [token]);

  useEffect(() => { loadNext().catch(setError); loadList(); }, [loadNext, loadList]);

  const open = async (ref: string) => {
    const detail = await reviewApi.expertItem(token, ref);
    setDone(false);
    setItem(detail.item);
    setPosition((p) => ({ ...p, at: detail.position }));
    setRating(detail.rating ?? EMPTY);
  };

  const complete = (["relevance", "clarity", "difficulty", "distractors"] as const).every((k) => rating[k]) && rating.key_correct;

  const save = async () => {
    if (!item || !complete) return;
    setSaving(true);
    setError(null);
    try {
      await reviewApi.saveRating(token, item.item_ref, rating as Rating);
      await loadNext();
      loadList();
    } catch (e) {
      setError(e);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="review-layout">
      <aside className="navigator">
        <h3>Questions</h3>
        <ol>
          {list.map((entry) => (
            <li key={entry.item_ref}>
              <button className={item?.item_ref === entry.item_ref ? "nav-item current" : "nav-item"} onClick={() => open(entry.item_ref).catch(setError)}>
                {entry.position} {entry.rated ? "✓" : ""}
              </button>
            </li>
          ))}
        </ol>
      </aside>
      <div className="stack">
        <Card title={session.study_title}>
          {instructions && <p className="muted">{instructions}</p>}
          <ProgressBar value={position.rated} total={position.total} />
        </Card>
        <ErrorBox error={error} />
        {done || !item ? (
          <Card title="All questions rated"><p>Thank you! You can still open any question on the left to revise your rating.</p></Card>
        ) : (
          <Card title={`Question ${position.at} of ${position.total}`}>
            <p className="muted small">{item.topic_label} · {item.domain}</p>
            <p className="question">{item.question}</p>
            <ol className="options">
              {(["A", "B", "C", "D"] as const).map((label) => (
                <li key={label} className={label === item.answer ? "key" : undefined}>
                  <strong>{label}.</strong> {item.options[label]} {label === item.answer && <em className="muted">(marked as correct)</em>}
                </li>
              ))}
            </ol>
            <Likert name="relevance" label="Content accuracy and relevance" value={rating.relevance ?? null} onChange={(v) => setRating({ ...rating, relevance: v })} low="poor" high="excellent" />
            <Likert name="clarity" label="Clarity of question and options" value={rating.clarity ?? null} onChange={(v) => setRating({ ...rating, clarity: v })} low="unclear" high="very clear" />
            <Likert name="difficulty" label="Difficulty for a final-year student" value={rating.difficulty ?? null} onChange={(v) => setRating({ ...rating, difficulty: v })} low="very easy" high="very hard" />
            <Likert name="distractors" label="Plausibility of the wrong options" value={rating.distractors ?? null} onChange={(v) => setRating({ ...rating, distractors: v })} low="obviously wrong" high="tempting" />
            <fieldset className="likert">
              <legend>Is the marked answer actually correct?</legend>
              {(["yes", "no", "unsure"] as const).map((v) => (
                <label key={v} className={rating.key_correct === v ? "likert-option selected" : "likert-option"}>
                  <input type="radio" name="key_correct" checked={rating.key_correct === v} onChange={() => setRating({ ...rating, key_correct: v })} />{v}
                </label>
              ))}
            </fieldset>
            <label className="check">
              <input type="checkbox" checked={!!rating.unusable} onChange={(e) => setRating({ ...rating, unusable: e.target.checked })} />
              <span>Unusable: the question has a factual error</span>
            </label>
            {rating.unusable && <textarea placeholder="What is wrong?" value={rating.unusable_reason ?? ""} onChange={(e) => setRating({ ...rating, unusable_reason: e.target.value })} />}
            <textarea placeholder="Optional comment" value={rating.comment ?? ""} onChange={(e) => setRating({ ...rating, comment: e.target.value })} />
            <button className="primary" disabled={!complete || saving} onClick={save}>{saving ? "Saving…" : "Save and next"}</button>
          </Card>
        )}
      </div>
    </div>
  );
}
