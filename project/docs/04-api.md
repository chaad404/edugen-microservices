# 04 API

Through the gateway, the Lab is under `/api/lab` and the Review service under `/api/review`; the gateway strips the
prefix. Each service also serves its OpenAPI description: `http://localhost:8080/api/lab/docs` and
`/api/review/docs`. The Generator and Evaluator are reachable only inside the Docker network.

Errors are RFC 9457 problem details (`application/problem+json`) with a stable `type`, for example
`urn:edugen:problem:paid-models-not-confirmed`. Clients react to the type, not to the human-readable title.

## Lab (operator)

All routes except login need `Authorization: Bearer <operator token>`.

| Method and path | Purpose | Success | Typical errors |
|---|---|---|---|
| `POST /auth/login` | Operator sign-in | 200 token (8 h) | 401, 429 at the gateway |
| `POST /auth/stream-tickets` | Ticket for one SSE channel (5 min) | 200 | 422 bad channel |
| `GET /models`, `GET /strategies` | Model registry with price and availability; strategies | 200 | 503 catalog unavailable |
| `GET /framework` | Pillars and cut points as published by the Evaluator | 200 | 503 |
| `GET /topics`, `GET /topics/{id}`, `POST /topics` | Topics; custom topics need a source text of at least 200 characters | 200 / 201 + `Location` | 404, 409 exists |
| `POST /experiments/estimate` | Jobs and estimated API cost of a planned run | 200 | 422 |
| `POST /experiments` | Start a run (`Idempotency-Key` header recommended) | **202 Accepted** + `Location` | 409 key reused, 422 unknown / unavailable model, paid model not confirmed, topic without text; 503 |
| `GET /experiments`, `GET /experiments/{id}` | List; status resource with jobs | 200 | 404 |
| `GET /experiments/{id}/items` | Questions with metrics, bands, flags; filters `model`, `strategy`, `topic_id`, paging | 200 | 404 |
| `GET /experiments/{id}/summary` | Comparison per model × strategy | 200 | 404 |
| `POST /studies` | Stratified blind sample, handed to the Review service | 201 + codes (or `draft` with `publish_error`) | 422 no items, study too large |
| `GET /studies`, `GET /studies/{id}` | Studies | 200 | 404 |
| `POST /studies/{id}/publish` | Retry handing a draft study to the Review service | 200 | 503 still unavailable |
| `GET /studies/{id}/analytics` | Human vs automatic: per group, agreement, correlations, items | 200 | 404 |
| `GET /events?channel=&after=` | Progress events after a cursor (polling) | 200 | 422 |
| `GET /events/stream?channel=&ticket=` | Server-Sent Events, resumes from `Last-Event-ID` or `after` | 200 `text/event-stream` | 401 / 403 bad ticket |
| `GET /health`, `GET /ready` | Liveness; readiness (database reachable) | 200 | 503 |

Example: starting an experiment.

```http
POST /api/lab/experiments
Authorization: Bearer eyJ…
Idempotency-Key: 3b1f0c5e-…
Content-Type: application/json

{"name": "Demo", "topic_ids": ["NETCOMP-DEMO-1"], "models": ["simulator"],
 "strategies": ["baseline", "prompt_v2", "verify_repair"], "questions_per_job": 5}
```

```http
HTTP/1.1 202 Accepted
Location: /api/lab/experiments/5b0e…

{"id": "5b0e…", "status": "running", "jobs_total": 3, "job_counts": {"queued": 3},
 "links": {"self": "/experiments/5b0e…", "events": "/events/stream?channel=experiment:5b0e…"}, …}
```

## Review

| Method and path | Caller | Purpose | Success | Typical errors |
|---|---|---|---|---|
| `POST /internal/v1/studies` | Lab (operator token, `Idempotency-Key` = study ID) | Create a blinded study; unknown fields are rejected | 201 codes, 200 on a retry | 400 key missing, 409 same ID with other content, 422 |
| `GET /v1/studies/{id}/progress` | Operator | Who rated or answered how much | 200 | 401, 404 |
| `POST /v1/sessions` | Participant | Redeem a code: experts give a pseudonym, students accept the notice | 200 session token (12 h) | 404 unknown code, 422 pseudonym or consent missing, 429 at the gateway |
| `GET /v1/sessions/me` | Participant | Progress and instructions, for resuming after a reload | 200 | 401 |
| `GET /v1/expert/items`, `GET /v1/expert/next`, `GET /v1/expert/items/{ref}` | Expert | The rater's own order; the next unrated question; one question with the rater's rating | 200 | 403 not an expert, 404 not in this study |
| `PUT /v1/expert/ratings/{ref}` | Expert | Create or revise a rating (four 1–5 scales, key correct yes / no / unsure, unusable flag, comment) | 200 with revision | 422 |
| `GET /v1/quiz/current` | Student | Current question with shuffled options; starts its timer. In the feedback step also `result` (correct option, right or wrong) | 200 | 403 |
| `POST /v1/quiz/answers` | Student | Answer the current question | 200 | 409 not the current question, answer locked |
| `POST /v1/quiz/feedback` | Student | Rate the answered question; the last one completes the quiz | 200 (score and completion code at the end) | 409 answer first |

## Generator (internal)

| Method and path | Purpose |
|---|---|
| `GET /v1/models` | Registry: alias, label, host, model ID, size, price per million tokens, `available`, the missing key if not |
| `GET /v1/strategies` | `baseline`, `prompt_v2`, `verify_repair` |
| `GET /health`, `GET /ready` | Liveness; readiness = connected to RabbitMQ |

The work itself arrives as `generation.requested` messages (see [03 Communication](03-communication.md)).

## Evaluator (internal)

| Method and path | Purpose |
|---|---|
| `POST /v1/evaluations` | Up to 100 questions, an optional `source_text` (without it alignment is not measured) and an optional `context` for the evidence check. Returns metrics, bands, flags and quality points per question, plus batch checks: key positions with a chi-square p-value, the share of keys that are the longest option, duplicate stems |
| `GET /v1/framework` | Pillars, cut points, labels, target zone, version `thesis-2026-10` |
| `GET /health`, `GET /ready` | Liveness; readiness = embedding model loaded (dense metrics are never replaced by lexical ones) |
