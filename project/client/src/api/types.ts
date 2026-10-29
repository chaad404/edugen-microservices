// Shapes of the Lab and Review API responses used by the client.

export type Band = "Weak" | "Good enough" | "Better" | "Best" | "Too close" | "Too simple" | "Too dense";
export type PillarKey = "P1" | "P2" | "P3a" | "P3b";
export type Options = Record<"A" | "B" | "C" | "D", string>;

export interface ModelInfo {
  alias: string;
  label: string;
  provider: string;
  model_id: string;
  params: string | null;
  paid: boolean;
  available: boolean;
  requires: string | null;
  price_per_m: { input: number; output: number };
  notes: string | null;
}

export interface Strategy {
  key: string;
  description: string;
}

export interface Topic {
  topic_id: string;
  domain: string;
  title: string;
  origin: "demo" | "thesis" | "custom";
  has_source_text: boolean;
  source_length: number;
}

export interface Job {
  id: string;
  topic_id: string;
  domain: string;
  model: string;
  strategy: string;
  status: "queued" | "dispatched" | "generated" | "succeeded" | "failed";
  provider: string | null;
  simulated: boolean;
  attempts: number;
  calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
  latency_seconds: number | null;
  strategy_status: string | null;
  error_kind: string | null;
  error: string | null;
  evaluation_attempts: number;
  items: number;
}

export interface Experiment {
  id: string;
  name: string;
  origin: "live" | "thesis_import";
  status: string;
  description: string | null;
  models: string[];
  strategies: string[];
  questions_per_job: number;
  created_at: string;
  finished_at: string | null;
  job_counts: Record<string, number>;
  jobs_total: number;
  cost_usd: number;
  jobs?: Job[];
}

export interface Estimate {
  jobs: number;
  estimated_cost_usd: number;
  max_cost_usd: number | null;
  per_model: Record<string, number>;
  max_per_model: Record<string, number | null>;
  paid_models: string[];
}

export interface Metrics {
  alignment: number | null;
  alignment_lexical: number | null;
  grade: number | null;
  plausibility: number | null;
  plausibility_lexical: number | null;
  diversity: number | null;
}

export interface Item {
  id: number;
  topic_id: string;
  domain: string;
  model: string;
  strategy: string;
  question: string;
  options: Options;
  answer: string;
  evidence: string | null;
  metrics_source: "evaluator" | "thesis";
  valid: boolean | null;
  metrics: Metrics;
  bands: Record<PillarKey, Band | null> | null;
  flags: string[] | null;
  quality: number | null;
}

export interface ItemPage {
  total: number;
  bands_available: boolean;
  items: Item[];
}

export interface PillarSummary {
  metric: string;
  mean: number | null;
  band_of_mean?: Band | null;
  share_better_or_best?: number | null;
  share_in_zone?: number | null;
  share_too_close?: number | null;
}

export interface SummaryGroup {
  model: string;
  strategy: string;
  questions: number;
  valid: number;
  pillars: Record<PillarKey, PillarSummary>;
  key_positions: Record<string, number>;
  key_position_p: number | null;
  raw_key_positions: Record<string, number> | null;
  raw_key_position_p: number | null;
  raw_keys_known: number;
  key_longest_rate: number | null;
  flags: Record<string, number>;
  flags_checked: number;
  jobs: number;
  failed_jobs: number;
  simulated: boolean;
  cost_usd: number;
  tokens: number;
  mean_latency_seconds: number | null;
}

export interface Summary {
  experiment_id: string;
  name: string;
  framework_version: string | null;
  bands_available: boolean;
  groups: SummaryGroup[];
  leaders: Partial<Record<PillarKey, { model: string; strategy: string; value: number }>>;
  note: string;
}

export interface LabEvent {
  id: number;
  type: string;
  data: Record<string, unknown>;
}

export interface Study {
  id: string;
  title: string;
  kind: "expert" | "student" | "both";
  status: "draft" | "open";
  items: number;
  student_items: number;
  per_cell: number;
  seed: number;
  source_experiments: string[];
  expert_code: string | null;
  student_code: string | null;
  publish_error: string | null;
  created_at: string;
}

export interface StudyAnalytics {
  study: Study;
  progress: { raters: number; ratings: number; participants: number; answers: number; feedback: number };
  groups: Array<{
    model: string;
    strategy: string;
    items: number;
    automatic: Record<string, number | null>;
    expert: Record<string, number | null>;
    student: Record<string, number | null>;
  }>;
  agreement: Record<string, { level: string; raters: number; items_with_2_raters: number; alpha: number | null }>;
  correlations: Array<{ human: string; metric: string; n: number; spearman_rho: number | null }>;
  items: Array<{
    item_ref: string;
    model: string;
    strategy: string;
    domain: string;
    question: string;
    answer: string;
    automatic: Record<string, number | null>;
    expert: Record<string, unknown> & { ratings: number };
    student: { attempts: number; p_value: number | null; dead_distractors: string[]; option_counts: Record<string, number> };
  }>;
  note: string;
}

// Review service

export interface JoinResult {
  token: string;
  role: "expert" | "student";
  study_title: string;
  instructions: string;
}

export interface SessionInfo {
  role: "expert" | "student";
  study_title: string;
  instructions: string;
  rater_name: string | null;
  done: number;
  total: number;
  completed: boolean;
  completion_code: string | null;
}

export interface ReviewItem {
  item_ref: string;
  topic_label: string;
  domain: string;
  question: string;
  options: Options;
  answer: string;
}

export interface Rating {
  relevance: number;
  clarity: number;
  difficulty: number;
  distractors: number;
  key_correct: "yes" | "no" | "unsure";
  unusable: boolean;
  unusable_reason?: string | null;
  comment?: string | null;
  revision?: number;
}

export interface ExpertStep {
  done: boolean;
  position?: number;
  total: number;
  rated: number;
  item?: ReviewItem;
  rating?: Rating | null;
}

export interface QuizState {
  state: "question" | "feedback" | "completed";
  position?: number;
  total: number;
  chosen?: string | null;
  correct?: number;
  completion_code?: string | null;
  item?: { item_ref: string; topic_label: string; domain: string; question: string; options: Array<{ label: string; text: string }> };
  /** Only in the feedback step, after the answer is locked */
  result?: { key: string; correct: boolean };
}
