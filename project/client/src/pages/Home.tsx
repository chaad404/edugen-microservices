import { Link } from "react-router-dom";

export default function Home() {
  return (
    <div className="home">
      <section className="hero">
        <h1>Which language model writes the better exam question?</h1>
        <p>
          EduGen generates multiple-choice questions with several language models, scores them with the deterministic
          Three Pillars framework of my BSc thesis, and lets experts and students evaluate them blind, so the automatic
          scores can be compared with human judgement.
        </p>
      </section>
      <div className="role-grid">
        <Link to="/lab" className="role-card">
          <h2>Lab</h2>
          <p>Run experiments, follow them live, compare models and strategies, and open review studies.</p>
          <span className="role-tag">Operator</span>
        </Link>
        <Link to="/review" className="role-card">
          <h2>Expert review</h2>
          <p>Rate questions on relevance, clarity, difficulty and distractor quality, without seeing the model.</p>
          <span className="role-tag">Code required</span>
        </Link>
        <Link to="/quiz" className="role-card">
          <h2>Student quiz</h2>
          <p>Answer the questions, then tell us how clear, helpful and difficult they were. Anonymous.</p>
          <span className="role-tag">Code required</span>
        </Link>
      </div>
    </div>
  );
}
