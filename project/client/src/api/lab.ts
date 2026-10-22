import { request } from "./http";
import type {
  Estimate, Experiment, ItemPage, LabEvent, ModelInfo, Strategy, Study, StudyAnalytics, Summary, Topic,
} from "./types";

const BASE = "/api/lab";
const TOKEN_KEY = "edugen.operator.token";

export const operatorToken = {
  get: () => sessionStorage.getItem(TOKEN_KEY),
  set: (token: string) => sessionStorage.setItem(TOKEN_KEY, token),
  clear: () => sessionStorage.removeItem(TOKEN_KEY),
};

const lab = <T>(path: string, options: Parameters<typeof request>[1] = {}) =>
  request<T>(`${BASE}${path}`, { token: operatorToken.get(), ...options });

export interface ExperimentRequest {
  name: string;
  topic_ids: string[];
  models: string[];
  strategies: string[];
  questions_per_job: number;
  confirm_paid: boolean;
  description?: string;
}

export const labApi = {
  login: (username: string, password: string) =>
    request<{ access_token: string }>(`${BASE}/auth/login`, { method: "POST", body: { username, password } }),
  streamTicket: (channel: string) =>
    lab<{ ticket: string }>("/auth/stream-tickets", { method: "POST", body: { channel } }),
  models: () => lab<ModelInfo[]>("/models"),
  strategies: () => lab<Strategy[]>("/strategies"),
  topics: () => lab<Topic[]>("/topics"),
  experiments: () => lab<Experiment[]>("/experiments"),
  experiment: (id: string) => lab<Experiment>(`/experiments/${id}`),
  estimate: (body: ExperimentRequest) => lab<Estimate>("/experiments/estimate", { method: "POST", body }),
  // The idempotency key makes a retried submission safe: the same key never starts a second experiment
  startExperiment: (body: ExperimentRequest, idempotencyKey: string) =>
    lab<Experiment>("/experiments", { method: "POST", body, headers: { "Idempotency-Key": idempotencyKey } }),
  items: (id: string, filters: Record<string, string> = {}) => {
    const query = new URLSearchParams({ limit: "500", ...filters });
    return lab<ItemPage>(`/experiments/${id}/items?${query}`);
  },
  summary: (id: string) => lab<Summary>(`/experiments/${id}/summary`),
  events: (channel: string, after = 0) =>
    lab<{ events: LabEvent[]; last_id: number }>(`/events?channel=${encodeURIComponent(channel)}&after=${after}`),
  studies: () => lab<Study[]>("/studies"),
  study: (id: string) => lab<Study>(`/studies/${id}`),
  createStudy: (body: { title: string; kind: string; experiment_ids: string[]; per_cell: number; student_items: number; seed: number }) =>
    lab<Study>("/studies", { method: "POST", body }),
  republish: (id: string) => lab<Study>(`/studies/${id}/publish`, { method: "POST" }),
  analytics: (id: string) => lab<StudyAnalytics>(`/studies/${id}/analytics`),
};

export const streamUrl = (channel: string, ticket: string, after: number) =>
  `${BASE}/events/stream?channel=${encodeURIComponent(channel)}&ticket=${encodeURIComponent(ticket)}&after=${after}`;
