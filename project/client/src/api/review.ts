import { request } from "./http";
import type { ExpertStep, JoinResult, QuizState, Rating, ReviewItem, SessionInfo } from "./types";

const BASE = "/api/review/v1";

// A session token per study code, kept on this device so an interrupted review or quiz can be resumed
export const sessionStore = {
  get: (code: string) => localStorage.getItem(`edugen.session.${code.toUpperCase()}`),
  set: (code: string, token: string) => localStorage.setItem(`edugen.session.${code.toUpperCase()}`, token),
  clear: (code: string) => localStorage.removeItem(`edugen.session.${code.toUpperCase()}`),
};

export const reviewApi = {
  join: (code: string, extra: { rater_name?: string; consent?: boolean }) =>
    request<JoinResult>(`${BASE}/sessions`, { method: "POST", body: { code, ...extra } }),
  me: (token: string) => request<SessionInfo>(`${BASE}/sessions/me`, { token }),

  expertNext: (token: string) => request<ExpertStep>(`${BASE}/expert/next`, { token }),
  expertItems: (token: string) =>
    request<{ total: number; rated: number; items: Array<{ position: number; item_ref: string; rated: boolean }> }>(
      `${BASE}/expert/items`, { token }),
  expertItem: (token: string, ref: string) =>
    request<{ position: number; total: number; item: ReviewItem; rating: Rating | null }>(`${BASE}/expert/items/${ref}`, { token }),
  saveRating: (token: string, ref: string, rating: Rating) =>
    request<{ saved: boolean; revision: number; rated: number; total: number }>(
      `${BASE}/expert/ratings/${ref}`, { method: "PUT", body: rating, token }),

  quizCurrent: (token: string) => request<QuizState>(`${BASE}/quiz/current`, { token }),
  answer: (token: string, item_ref: string, choice: string) =>
    request<QuizState>(`${BASE}/quiz/answers`, { method: "POST", body: { item_ref, choice }, token }),
  feedback: (token: string, item_ref: string, scores: { clarity: number; helpfulness: number; difficulty: number }) =>
    request<QuizState>(`${BASE}/quiz/feedback`, { method: "POST", body: { item_ref, ...scores }, token }),
};
