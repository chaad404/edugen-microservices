import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { ApiError } from "../../api/http";
import { codeRole, reviewApi, sessionStore } from "../../api/review";
import type { QuizState } from "../../api/types";
import { Card, ErrorBox, Likert, Loading, ProgressBar } from "../../components/ui";

const NOTICE = "This quiz is part of a BSc thesis on automatically generated exam questions. Your answers, " +
  "the time you take and your ratings are stored anonymously, without your name or any other personal data, and are " +
  "used only for research. You can stop at any time.";

export default function StudentQuiz() {
  const [params] = useSearchParams();
  const [code, setCode] = useState(params.get("code") ?? "");
  const [token, setToken] = useState<string | null>(() => (code ? sessionStore.get(code) : null));

  if (!token) return <Join code={code} setCode={setCode} onJoined={setToken} />;
  return <Quiz token={token} onExpired={() => { sessionStore.clear(code); setToken(null); }} />;
}

function Join({ code, setCode, onJoined }: { code: string; setCode: (c: string) => void; onJoined: (token: string) => void }) {
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const expertCode = codeRole(code) === "expert";
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      const result = await reviewApi.join(code, { consent });
      if (result.role !== "student") throw new Error("This is an expert code. Open the expert review instead.");
      sessionStore.set(code, result.token);
      onJoined(result.token);
    } catch (e) {
      setError(e);
    }
  };
  return (
    <div className="narrow">
      <Card title="Practice quiz">
        <form className="form" onSubmit={submit}>
          <label>Quiz code<input value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="STU-…" /></label>
          <p className="notice">{NOTICE}</p>
          <label className="check">
            <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
            <span>I have read the notice and agree to take part.</span>
          </label>
          {expertCode && (
            <div className="error" role="alert">This is an expert review code. <Link to={`/review?code=${code}`}>Open the expert review</Link></div>
          )}
          <ErrorBox error={error} />
          <button className="primary" disabled={!code || !consent || expertCode}>Start the quiz</button>
        </form>
      </Card>
    </div>
  );
}

function Quiz({ token, onExpired }: { token: string; onExpired: () => void }) {
  const [state, setState] = useState<QuizState | null>(null);
  const [choice, setChoice] = useState<string | null>(null);
  const [scores, setScores] = useState<{ clarity: number | null; helpfulness: number | null; difficulty: number | null }>({ clarity: null, helpfulness: null, difficulty: null });
  const [shownAt, setShownAt] = useState(Date.now());
  const [now, setNow] = useState(Date.now());
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const current = await reviewApi.quizCurrent(token);
      setState(current);
      setChoice(current.chosen ?? null);
      setScores({ clarity: null, helpfulness: null, difficulty: null });
      setShownAt(Date.now());
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) onExpired();
      else setError(e);
    }
  }, [token, onExpired]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const act = async (fn: () => Promise<QuizState>) => {
    setBusy(true);
    setError(null);
    try {
      const next = await fn();
      if (next.state === "completed") setState(next);
      else await load();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  if (!state) return error ? <ErrorBox error={error} /> : <Loading />;

  if (state.state === "completed") {
    return (
      <div className="narrow">
        <Card title="Thank you!">
          <p>You answered <strong>{state.correct} of {state.total}</strong> questions correctly.</p>
          <p>Completion code: <code className="big-code">{state.completion_code}</code></p>
        </Card>
      </div>
    );
  }

  const item = state.item!;
  const seconds = Math.max(0, Math.round((now - shownAt) / 1000));
  return (
    <div className="narrow wide">
      <Card title={`Question ${state.position} of ${state.total}`} actions={state.state === "question" && <span className="muted">{seconds} s</span>}>
        <ProgressBar value={(state.position ?? 1) - 1} total={state.total} />
        <p className="muted small">{item.topic_label}</p>
        <p className="question">{item.question}</p>
        <div className="answers" role="radiogroup">
          {item.options.map((option) => (
            <label key={option.label} className={choice === option.label ? "answer selected" : "answer"}>
              <input type="radio" name="answer" value={option.label} disabled={state.state !== "question"}
                checked={choice === option.label} onChange={() => setChoice(option.label)} />
              <strong>{option.label}.</strong> {option.text}
            </label>
          ))}
        </div>
        <ErrorBox error={error} />
        {state.state === "question" ? (
          <button className="primary" disabled={!choice || busy} onClick={() => act(() => reviewApi.answer(token, item.item_ref, choice!))}>
            Submit answer
          </button>
        ) : (
          <div className="feedback">
            <p className="muted">Your answer is saved and cannot be changed. How was this question?</p>
            <Likert name="clarity" label="Clarity of the question and options" value={scores.clarity} onChange={(v) => setScores({ ...scores, clarity: v })} low="unclear" high="very clear" />
            <Likert name="helpfulness" label="Helpful for exam preparation" value={scores.helpfulness} onChange={(v) => setScores({ ...scores, helpfulness: v })} low="not at all" high="very" />
            <Likert name="difficulty" label="Difficulty" value={scores.difficulty} onChange={(v) => setScores({ ...scores, difficulty: v })} low="very easy" high="very hard" />
            <button className="primary" disabled={busy || !scores.clarity || !scores.helpfulness || !scores.difficulty}
              onClick={() => act(() => reviewApi.feedback(token, item.item_ref, scores as { clarity: number; helpfulness: number; difficulty: number }))}>
              Next question
            </button>
          </div>
        )}
      </Card>
    </div>
  );
}
