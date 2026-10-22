import { Link, Navigate, Route, Routes } from "react-router-dom";

import Home from "./pages/Home";
import CatalogPage from "./pages/lab/CatalogPage";
import ExperimentPage from "./pages/lab/ExperimentPage";
import ExperimentsPage from "./pages/lab/ExperimentsPage";
import LabLayout from "./pages/lab/LabLayout";
import Login from "./pages/lab/Login";
import StudiesPage from "./pages/lab/StudiesPage";
import StudyPage from "./pages/lab/StudyPage";
import StudentQuiz from "./pages/quiz/StudentQuiz";
import ExpertReview from "./pages/review/ExpertReview";

export default function App() {
  return (
    <div className="app">
      <header className="topbar">
        <Link to="/" className="brand">EduGen</Link>
        <span className="tagline">Comparing language models on exam-question generation</span>
      </header>
      <main className="content">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/lab/login" element={<Login />} />
          <Route path="/lab" element={<LabLayout />}>
            <Route index element={<ExperimentsPage />} />
            <Route path="experiments/:id" element={<ExperimentPage />} />
            <Route path="studies" element={<StudiesPage />} />
            <Route path="studies/:id" element={<StudyPage />} />
            <Route path="catalog" element={<CatalogPage />} />
          </Route>
          <Route path="/review" element={<ExpertReview />} />
          <Route path="/quiz" element={<StudentQuiz />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
