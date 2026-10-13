const GATEWAY_URL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' 
  ? 'http://localhost:8000' 
  : '';

let CURRENT_RUN_DATA = null;
let ACTIVE_EXAM_ID = null;
let TOPICS_MAP = {};

// Initialize Lucide icons
document.addEventListener("DOMContentLoaded", async () => {
  if (window.lucide) {
    lucide.createIcons();
  }
  await loadTopics();
  setupTopicSelector();
  checkGatewayHealth();
});

// Switch view tabs
function switchTab(tab) {
  const tabs = ['instructor', 'student', 'analytics'];
  tabs.forEach(t => {
    document.getElementById(`view-${t}`).classList.add('hidden');
    const btn = document.getElementById(`tab-${t}`);
    btn.className = "px-4 py-2 text-sm font-medium rounded-lg transition-all flex items-center space-x-2 text-slate-400 hover:text-white";
  });

  document.getElementById(`view-${tab}`).classList.remove('hidden');
  const activeBtn = document.getElementById(`tab-${tab}`);
  activeBtn.className = "px-4 py-2 text-sm font-medium rounded-lg transition-all flex items-center space-x-2 bg-sky-600 text-white shadow";

  if (tab === 'student' && ACTIVE_EXAM_ID) {
    loadStudentExam(ACTIVE_EXAM_ID);
  } else if (tab === 'analytics' && ACTIVE_EXAM_ID) {
    loadAnalytics(ACTIVE_EXAM_ID);
  }

  if (window.lucide) lucide.createIcons();
}

async function checkGatewayHealth() {
  try {
    const res = await fetch(`${GATEWAY_URL}/health`);
    if (res.ok) {
      document.getElementById("gateway-status").innerText = "Gateway Online (:8000)";
    }
  } catch (err) {
    document.getElementById("gateway-status").innerText = "Gateway Offline";
  }
}

// Load curriculum topics from Gateway
async function loadTopics() {
  try {
    const res = await fetch(`${GATEWAY_URL}/api/topics`);
    if (res.ok) {
      const topics = await res.json();
      const sel = document.getElementById("select-topic");
      sel.innerHTML = "";
      topics.forEach(t => {
        TOPICS_MAP[t.topic_id] = t;
        const opt = document.createElement("option");
        opt.value = t.topic_id;
        opt.innerText = `${t.domain}: ${t.title}`;
        sel.appendChild(opt);
      });
      if (topics.length > 0) {
        document.getElementById("input-source-text").value = topics[0].source_text;
      }
    }
  } catch (err) {
    console.warn("Using offline topic fallback:", err);
  }
}

function setupTopicSelector() {
  const sel = document.getElementById("select-topic");
  sel.addEventListener("change", (e) => {
    const t = TOPICS_MAP[e.target.value];
    if (t) {
      document.getElementById("input-source-text").value = t.source_text;
    }
  });
}

// Trigger Batch Run via API Gateway with Server-Sent Events (SSE)
async function triggerRun() {
  const topicId = document.getElementById("select-topic").value;
  const strategy = document.getElementById("select-strategy").value;
  const modelName = document.getElementById("select-model").value;
  const count = parseInt(document.getElementById("input-count").value) || 3;
  const sourceText = document.getElementById("input-source-text").value;

  const topicObj = TOPICS_MAP[topicId] || { domain: "SYSTEM", title: "Technical Subject" };

  const payload = {
    topic_id: topicId,
    domain: topicObj.domain,
    title: topicObj.title,
    source_text: sourceText,
    model_name: modelName,
    strategy: strategy,
    count: count
  };

  // UI state updates
  const btn = document.getElementById("btn-generate");
  btn.disabled = true;
  btn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i><span>Synthesizing Items...</span>`;
  if (window.lucide) lucide.createIcons();

  const progressCard = document.getElementById("progress-card");
  progressCard.classList.remove("hidden");
  document.getElementById("pipeline-status-text").innerText = "Pipeline: Dispatched to Service 2 (Generator)...";
  document.getElementById("pipeline-progress-bar").style.width = "30%";

  try {
    const res = await fetch(`${GATEWAY_URL}/api/runs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    const runId = data.run_id;

    // Connect to Server-Sent Events (SSE) Stream
    const eventSource = new EventSource(`${GATEWAY_URL}/api/runs/${runId}/stream`);

    eventSource.addEventListener("status_update", (e) => {
      const info = JSON.parse(e.data);
      if (info.status === "EVALUATING") {
        document.getElementById("pipeline-status-text").innerText = "Pipeline: Evaluating Three Pillars via Service 3 (Evaluator)...";
        document.getElementById("pipeline-progress-bar").style.width = "75%";
        document.getElementById("pipeline-step-badge").innerText = "Stage 2 of 2";
      }
    });

    eventSource.addEventListener("batch_completed", (e) => {
      const runResult = JSON.parse(e.data);
      CURRENT_RUN_DATA = runResult;
      eventSource.close();

      document.getElementById("pipeline-progress-bar").style.width = "100%";
      document.getElementById("pipeline-status-text").innerText = "Pipeline Completed: Items Evaluated & Stored!";
      document.getElementById("pipeline-step-badge").innerText = "Completed";

      renderRunResults(runResult);

      btn.disabled = false;
      btn.innerHTML = `<i data-lucide="play" class="w-4 h-4"></i><span>Trigger Generation & Evaluation</span>`;
      if (window.lucide) lucide.createIcons();
    });

    eventSource.addEventListener("error", (e) => {
      eventSource.close();
      btn.disabled = false;
      btn.innerHTML = `<i data-lucide="alert-triangle" class="w-4 h-4"></i><span>Failed — Retry</span>`;
    });
  } catch (err) {
    btn.disabled = false;
    btn.innerHTML = `<i data-lucide="play" class="w-4 h-4"></i><span>Trigger Generation & Evaluation</span>`;
    alert("Connection error: Ensure Gateway is running on port 8000.");
  }
}

// Render questions and metric badges
function renderRunResults(run) {
  document.getElementById("summary-cards").classList.remove("hidden");
  document.getElementById("btn-publish-exam").classList.remove("hidden");

  const summary = run.metrics_summary || {};
  document.getElementById("metric-align").innerText = summary.mean_semantic_alignment !== undefined ? summary.mean_semantic_alignment : "--";
  document.getElementById("metric-grade").innerText = summary.mean_linguistic_complexity !== undefined ? `Grade ${summary.mean_linguistic_complexity}` : "--";
  document.getElementById("metric-plaus").innerText = summary.mean_distractor_plausibility !== undefined ? summary.mean_distractor_plausibility : "--";

  const feed = document.getElementById("questions-feed");
  feed.innerHTML = "";

  run.questions.forEach((q, idx) => {
    const metrics = q.metrics || {};
    const card = document.createElement("div");
    card.className = "bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-4 hover:border-sky-300 transition";

    const badgeColor = metrics.semantic_alignment >= 0.35 ? "bg-emerald-50 text-emerald-700 border-emerald-200" : "bg-amber-50 text-amber-700 border-amber-200";

    card.innerHTML = `
      <div class="flex flex-wrap justify-between items-start gap-2 border-b border-slate-100 pb-3">
        <span class="text-xs font-bold text-slate-400 uppercase tracking-wider">Item #${idx + 1} &bull; ${q.strategy_used || 'Strategy'}</span>
        <div class="flex flex-wrap gap-2 text-xs">
          <span class="px-2.5 py-1 rounded-md border font-medium ${badgeColor}">Alignment: ${metrics.semantic_alignment || 0.0}</span>
          <span class="px-2.5 py-1 rounded-md border border-slate-200 bg-slate-50 text-slate-700 font-medium">Grade ${metrics.linguistic_complexity || 0}</span>
          <span class="px-2.5 py-1 rounded-md border border-indigo-200 bg-indigo-50 text-indigo-700 font-medium">Plausibility: ${metrics.distractor_plausibility || 0.0}</span>
          ${metrics.quality_gate_passed ? '<span class="px-2.5 py-1 rounded-md bg-emerald-100 text-emerald-800 font-bold">✓ Approved</span>' : '<span class="px-2.5 py-1 rounded-md bg-rose-100 text-rose-800 font-bold">Flagged</span>'}
        </div>
      </div>
      <p class="text-sm font-semibold text-slate-900">${q.question_stem}</p>
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
        <div class="p-2.5 rounded-xl border ${q.correct_option === 'A' ? 'border-emerald-500 bg-emerald-50/50 font-bold text-emerald-900' : 'border-slate-200 text-slate-700'}">A) ${q.option_a}</div>
        <div class="p-2.5 rounded-xl border ${q.correct_option === 'B' ? 'border-emerald-500 bg-emerald-50/50 font-bold text-emerald-900' : 'border-slate-200 text-slate-700'}">B) ${q.option_b}</div>
        <div class="p-2.5 rounded-xl border ${q.correct_option === 'C' ? 'border-emerald-500 bg-emerald-50/50 font-bold text-emerald-900' : 'border-slate-200 text-slate-700'}">C) ${q.option_c}</div>
        <div class="p-2.5 rounded-xl border ${q.correct_option === 'D' ? 'border-emerald-500 bg-emerald-50/50 font-bold text-emerald-900' : 'border-slate-200 text-slate-700'}">D) ${q.option_d}</div>
      </div>
      ${q.explanation ? `<p class="text-[11px] text-slate-500 italic bg-slate-50 p-2.5 rounded-xl border border-slate-100"><strong class="text-slate-700">Rationale:</strong> ${q.explanation}</p>` : ''}
    `;
    feed.appendChild(card);
  });

  if (window.lucide) lucide.createIcons();
}

// Publish Exam to Service 4 (Quiz)
async function publishExamFromFeed() {
  if (!CURRENT_RUN_DATA || !CURRENT_RUN_DATA.questions.length) return;

  const btn = document.getElementById("btn-publish-exam");
  btn.disabled = true;
  btn.innerText = "Publishing to Quiz Bank...";

  const payload = {
    title: `${CURRENT_RUN_DATA.title || 'Technical Assessment'} Exam`,
    domain: CURRENT_RUN_DATA.domain || "SYSTEM",
    duration_minutes: 20,
    passing_percentage: 60.0,
    questions: CURRENT_RUN_DATA.questions.map(q => ({
      question_stem: q.question_stem,
      option_a: q.option_a,
      option_b: q.option_b,
      option_c: q.option_c,
      option_d: q.option_d,
      correct_option: q.correct_option,
      explanation: q.explanation
    }))
  };

  try {
    const res = await fetch(`${GATEWAY_URL}/api/exams/publish`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    ACTIVE_EXAM_ID = data.exam_id;
    btn.innerHTML = `<span>Published! (ID: ${ACTIVE_EXAM_ID.substring(0,8)}...)</span>`;
    setTimeout(() => {
      switchTab("student");
    }, 800);
  } catch (err) {
    btn.disabled = false;
    btn.innerText = "Publish Failed";
  }
}

// Load exam for Student taking
async function loadStudentExam(examId) {
  const container = document.getElementById("student-questions-container");
  container.innerHTML = `<div class="p-8 text-center text-slate-400">Loading active exam...</div>`;

  try {
    const res = await fetch(`${GATEWAY_URL}/api/exams/${examId}/take`);
    const exam = await res.json();

    document.getElementById("student-exam-title").innerText = exam.title;
    container.innerHTML = "";

    exam.questions.forEach((q, idx) => {
      const qDiv = document.createElement("div");
      qDiv.className = "bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-4";
      qDiv.innerHTML = `
        <div class="text-xs font-bold text-slate-400">QUESTION ${idx + 1} OF ${exam.total_questions}</div>
        <p class="text-sm font-semibold text-slate-900">${q.question_stem}</p>
        <div class="space-y-2">
          ${q.options.map(opt => `
            <label class="flex items-center space-x-3 p-3 rounded-xl border border-slate-200 hover:bg-slate-50 cursor-pointer transition text-xs">
              <input type="radio" name="question_${q.id}" value="${opt.key}" class="w-4 h-4 text-sky-600 focus:ring-sky-500 border-slate-300">
              <span class="font-medium text-slate-800"><strong class="mr-1">${opt.key})</strong> ${opt.text}</span>
            </label>
          `).join('')}
        </div>
      `;
      container.appendChild(qDiv);
    });
  } catch (err) {
    container.innerHTML = `<div class="p-8 text-center text-rose-500">Failed to load exam.</div>`;
  }
}

// Submit Student Quiz
async function submitStudentQuiz() {
  if (!ACTIVE_EXAM_ID) return;

  const answers = {};
  const inputs = document.querySelectorAll('#student-questions-container input[type="radio"]:checked');
  inputs.forEach(input => {
    const qId = input.name.replace("question_", "");
    answers[qId] = input.value;
  });

  const payload = {
    student_name: "Rakhi Mst Rokaya Akter (ZA0P52)",
    answers: answers
  };

  try {
    const res = await fetch(`${GATEWAY_URL}/api/exams/${ACTIVE_EXAM_ID}/submit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const result = await res.json();

    // Render results
    const card = document.getElementById("student-result-card");
    card.classList.remove("hidden");
    const badge = document.getElementById("student-pass-badge");

    if (result.passed) {
      badge.className = "px-3 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800";
      badge.innerText = `PASSED (${result.score_percentage}%)`;
    } else {
      badge.className = "px-3 py-1 rounded-full text-xs font-bold bg-rose-100 text-rose-800";
      badge.innerText = `FAILED (${result.score_percentage}%)`;
    }

    const reviewList = document.getElementById("student-review-list");
    reviewList.innerHTML = "";

    result.review.forEach((r, idx) => {
      const item = document.createElement("div");
      item.className = `p-4 rounded-xl border text-xs space-y-1.5 ${r.is_correct ? 'border-emerald-200 bg-emerald-50/40' : 'border-rose-200 bg-rose-50/40'}`;
      item.innerHTML = `
        <div class="font-bold text-slate-900">${idx + 1}. ${r.question_stem}</div>
        <div class="flex gap-4">
          <span>Your Answer: <strong class="${r.is_correct ? 'text-emerald-700' : 'text-rose-700'}">${r.selected_option}</strong></span>
          <span>Correct Key: <strong class="text-emerald-700">${r.correct_option}</strong></span>
        </div>
        ${r.explanation ? `<div class="text-[11px] text-slate-500 italic mt-1">${r.explanation}</div>` : ''}
      `;
      reviewList.appendChild(item);
    });

    window.scrollTo({ top: card.offsetTop - 80, behavior: 'smooth' });
  } catch (err) {
    alert("Error submitting exam: " + err);
  }
}

// Load Psychometrics Analytics
async function loadAnalytics(examId) {
  const container = document.getElementById("analytics-items-container");
  container.innerHTML = `<div class="col-span-2 text-center py-12 text-slate-400">Loading psychometrics from Service 4...</div>`;

  try {
    const res = await fetch(`${GATEWAY_URL}/api/exams/${examId}/analytics`);
    const data = await res.json();
    container.innerHTML = "";

    data.items.forEach((item, idx) => {
      const div = document.createElement("div");
      div.className = "bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-4";
      
      const counts = item.option_selection_counts || {};
      const total = item.total_attempts || 1;

      div.innerHTML = `
        <div class="flex justify-between items-center border-b border-slate-100 pb-3">
          <span class="text-xs font-bold text-slate-400 uppercase">Item #${idx + 1} Analytics</span>
          <span class="px-2.5 py-1 rounded-md text-xs font-bold bg-sky-50 text-sky-700 border border-sky-200">Difficulty Index: p = ${item.difficulty_index_p}</span>
        </div>
        <p class="text-xs font-semibold text-slate-800 line-clamp-2">${item.question_stem}</p>
        
        <div class="space-y-2 pt-2">
          <div class="text-[11px] font-semibold text-slate-500">Distractor Choice Distribution (Total: ${item.total_attempts} attempts):</div>
          ${['A', 'B', 'C', 'D'].map(opt => {
            const count = counts[opt] || 0;
            const pct = Math.round((count / Math.max(1, item.total_attempts)) * 100);
            return `
              <div class="space-y-1">
                <div class="flex justify-between text-[11px] text-slate-600">
                  <span>Option ${opt}</span>
                  <span>${count} times (${pct}%)</span>
                </div>
                <div class="w-full bg-slate-100 rounded-full h-1.5 overflow-hidden">
                  <div class="bg-indigo-600 h-1.5 rounded-full" style="width: ${pct}%"></div>
                </div>
              </div>
            `;
          }).join('')}
        </div>

        <div class="pt-2 border-t border-slate-100 flex justify-between items-center text-[11px]">
          <span class="text-slate-500">Status: <strong class="text-slate-800">${item.pedagogical_status}</strong></span>
          ${item.dead_distractors.length > 0 ? `<span class="text-rose-600 font-medium">Dead Distractors: ${item.dead_distractors.join(', ')}</span>` : '<span class="text-emerald-600 font-medium">All foils active</span>'}
        </div>
      `;
      container.appendChild(div);
    });
  } catch (err) {
    container.innerHTML = `<div class="col-span-2 text-center py-12 text-slate-400">No active exam analytics available yet. Take an exam first!</div>`;
  }
}
