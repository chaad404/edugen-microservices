# 05 Reliability and security

## What happens when a part fails

| Failure | Behaviour | Where |
|---|---|---|
| Generator stopped | Jobs wait in the durable queue `generator.jobs`; the experiment shows them as dispatched and continues when a Generator starts | RabbitMQ |
| LLM host answers 429 | Retried in the Generator only: 429 waits out most of a rate-limit window (or `Retry-After`), other transient errors use exponential backoff with full jitter, at most 4 attempts | `generator/resilience.py`, `llm.py` |
| LLM host keeps failing | Circuit breaker per model: after 5 technical failures it fails fast for 30 s, then lets one trial call through | `generator/resilience.py` |
| Bad API key, no credit, retired model (401, 402, 403, 404, 410) | No retry; the job fails at once with `provider_rejected` | `generator/providers/base.py` |
| Model answers with unusable JSON | Retried as a new attempt; the tokens of every attempt are counted in the cost | `generator/llm.py` |
| Evaluator stopped | Generated questions are stored; the job waits in `generated` and scoring is retried with a growing delay (2, 4, 8 … 60 s); the client shows "waiting for the Evaluator" | `lab/orchestration.py` |
| Evaluator without its embedding model | Readiness fails; the Lab treats it as unavailable and waits. Lexical scores are never stored in place of dense ones | `evaluator/main.py`, `lab/clients.py` |
| Review service stopped when a study is created | The sample is kept as a `draft` with the reason; `POST /studies/{id}/publish` retries with the same idempotency key | `lab/studies.py` |
| Lab stopped during a study | Ratings and answers are stored in the Review service and wait in its outbox or in the Lab's queue | `review/outbox.py` |
| Broker unreachable | Outbox rows stay unsent and are published in order when it is back; consumers reconnect with backoff | `*/outbox.py`, `*/broker.py`, `generator/messaging.py` |
| Gateway receives a burst of logins | 10 attempts per minute per address (burst 5), then 429 | `gateway/nginx.conf` |

A failure is always a bounded, visible state: a job is `failed` with `error_kind`, a study is `draft` with
`publish_error`, a job waits with a reason. No step reports success that did not happen.

## Delivery guarantees

| Mechanism | Guarantee | Implementation |
|---|---|---|
| **Transactional outbox** (Lab, Review) | A state change and the message announcing it are committed together, so neither exists without the other | Same database transaction; a relay thread publishes in order |
| **Publisher confirms + `mandatory`** | A message is marked sent only after the broker accepted it into a queue. If no queue is bound yet, it stays in the outbox | `basic_publish(..., mandatory=True)` on a confirm channel |
| **Acknowledge after the effect** | The Generator publishes the result before it acknowledges the job, and the Lab acknowledges after its commit | At-least-once delivery |
| **Inbox** (Lab) | A redelivered message is recognised by its ID, so its effect is not repeated | `inbox` table, primary key = `message_id` |
| **Idempotent state transitions** | A job accepts one result: a repeated job (at-least-once) cannot overwrite it | `queued` / `dispatched` only |
| **Revision numbers** | A late, older rating cannot overwrite a newer one | `revision` in `review.rating.submitted` |
| **Dead-letter queues** | A message that cannot be parsed goes to `generator.jobs.dead` or `lab.dead` instead of looping | Queue argument `x-dead-letter-exchange` |
| **Idempotency keys** (HTTP) | Retrying `POST /experiments` with the same key returns the first answer; the same key with another body is a 409; a primary key guards parallel first requests | `idempotency_keys` table |

Delivery is at-least-once, never exactly-once. Every consumer is therefore idempotent.

## Authentication and authorization

| Token | Issued by | Accepted by | Claims checked |
|---|---|---|---|
| Operator token (8 h) | Lab, `POST /auth/login` | Lab; Review for `/internal/*` and progress | Algorithm HS256 only, `iss edugen-lab`, `aud edugen`, `exp`, `iat`, `sub`, `role operator` |
| Stream ticket (5 min) | Lab | Lab SSE endpoint, for one channel | As above with `aud edugen-lab-stream` and the `channel` claim |
| Participant token (12 h) | Review, `POST /v1/sessions` | Review | `iss edugen-review`, `aud edugen-review`, `role expert` or `student`, `sid` study |

- **Record-level authorization** is done by the service that owns the data, never by the gateway. An expert can
  open only the questions of their own study; a student only their own quiz steps; an expert token is
  refused on student routes and the reverse.
- The gateway hides `/api/review/internal/*`, and the Generator and Evaluator have no public route at all.
- Passwords and secrets come from environment variables (`.env`, never committed). The development defaults
  in `docker-compose.yml` are logged as warnings at start-up.
- Operator tokens are signed with a key shared by the Lab and the Review service (HS256). This is acceptable for
  one trust domain; see ADR 7 for the trade-off.

## Blindness and privacy

- **Blind by data ownership.** The Review service receives only `item_ref`, topic label, question, options and
  key. It has no model, strategy, provider or score in its schema, so it cannot reveal them.
- **Blind by contract.** The study contract forbids unknown fields (`extra = "forbid"`). A request that tried to
  send a model name with an item would be rejected with 422. A test checks this.
- **Students are anonymous.** A random participant ID, no name, no IP address in the data, and consent to a
  participation notice before the first question (thesis NFR.2.3 and NFR.6.2).
- **Experts use a pseudonym** of their choice, which lets them resume their review.
- **The thesis's private inputs stay private:** no topic source texts, prompts or course PDFs are in the
  repository or the images.

## Cost control for paid models

- Models without a configured key are shown as unavailable and are refused; there is no silent fallback to the
  simulator.
- `POST /experiments/estimate` and the client show the cost before a run: the expected cost, from the output
  each model wrote per question in earlier runs, and a true maximum, as if every call used all its attempts
  and the full `max_tokens`.
- An experiment with a paid model is refused (422 `paid-models-not-confirmed`) unless `confirm_paid` is set.
- Every job stores its tokens and cost, including the tokens of failed attempts.
