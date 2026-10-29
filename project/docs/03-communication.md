# 03 Communication and data flows

## Synchronous or asynchronous?

| Interaction | Style | Why |
|---|---|---|
| Browser → Lab, Browser → Review | Synchronous REST through the gateway | The user needs an immediate answer |
| Lab → Generator: run a job | **Asynchronous command** on a work queue | Minutes long, paid, rate-limited, fails with HTTP 429; the queue buffers it and the Generator works at the speed the hosts allow |
| Generator → Lab: job result | **Asynchronous event** | The Lab may be busy or restarting; the result waits in its queue |
| Lab → Evaluator, Generator → Evaluator | Synchronous request–response | Deterministic, about a second, and the caller cannot continue without the scores |
| Lab → Generator: model catalog | Synchronous, cached for 30 s | Needed to validate a new experiment; the last known catalog is used while the Generator is down |
| Lab → Review: create a study | Synchronous with an idempotency key | The operator needs the study codes at once; a retry is safe |
| Review → Lab: ratings, answers, feedback | **Asynchronous events** | Participants must not wait for the Lab, and the Lab may be down during a study |
| Lab → Browser: progress | **Server-Sent Events** | Data flows from the server only; the browser reconnects and resumes by itself |

## Message contract

Every message on RabbitMQ has the same envelope:

```json
{
  "message_id": "7f0c…",
  "type": "generation.requested",
  "version": 1,
  "occurred_at": "2026-10-22T14:05:11+00:00",
  "producer": "lab",
  "correlation_id": "<experiment or study ID>",
  "causation_id": "<message_id of the message that caused this one>",
  "payload": { }
}
```

| Type | Kind | Producer → consumer | Payload (main fields) |
|---|---|---|---|
| `generation.requested` | Command | Lab → Generator (queue `generator.jobs`) | `job_id`, `experiment_id`, `model`, `strategy`, `num_questions`, `topic {topic_id, title, domain, source_text}` |
| `generation.completed` | Event | Generator → Lab (queue `lab.generation-results`) | `job_id`, `items[]`, `provider`, requested and returned model ID, `simulated`, `attempts`, `calls`, tokens, `cost_usd`, `latency_seconds`, `strategy_status`, `trace` (with the sampling `settings` sent) |
| `generation.failed` | Event | Generator → Lab | `job_id`, `error_kind`, `error`, `status_code`, `attempts`, tokens spent, `cost_usd`, `provider`, requested model ID, `trace` (the `settings`) |
| `review.rating.submitted` | Event | Review → Lab (queue `lab.review-events`) | `study_id`, `item_ref`, `rater` (pseudonym), four scores, `key_correct`, `unusable`, `comment`, `revision` |
| `review.answer.submitted` | Event | Review → Lab | `study_id`, `item_ref`, `participant` (anonymous ID), `chosen` (original label), `correct`, `time_ms` |
| `review.feedback.submitted` | Event | Review → Lab | `study_id`, `item_ref`, `participant`, `clarity`, `helpfulness`, `difficulty` |

The job message carries the topic text, so the Generator needs no call back to the Lab. Results never contain
internal table rows, only the fields the consumer needs.

### Broker topology

```mermaid
flowchart LR
    cmd{{edugen.commands<br/>direct}}
    evt{{edugen.events<br/>topic}}
    dlx{{edugen.dlx<br/>direct}}
    jobs[[generator.jobs]]
    results[[lab.generation-results]]
    reviews[[lab.review-events]]
    jobsdead[[generator.jobs.dead]]
    labdead[[lab.dead]]

    cmd -- "generation.requested" --> jobs
    evt -- "generation.*" --> results
    evt -- "review.#" --> reviews
    jobs -. "rejected" .-> dlx
    results -. "rejected" .-> dlx
    reviews -. "rejected" .-> dlx
    dlx --> jobsdead
    dlx --> labdead
```

*Messaging view.* `generator.jobs` is a work queue: each job goes to exactly one Generator instance. Events
are routed by type. A message that cannot be parsed goes to a dead-letter queue instead of being retried forever.

## Experiment run

```mermaid
sequenceDiagram
    autonumber
    actor Op as Operator
    participant GW as Gateway
    participant Lab
    participant MQ as RabbitMQ
    participant Gen as Generator
    participant LLM as LLM host / simulator
    participant Ev as Evaluator

    Op->>GW: POST /api/lab/experiments (Idempotency-Key)
    GW->>Lab: POST /experiments
    Lab->>Lab: one transaction: experiment, jobs, outbox messages
    Lab-->>Op: 202 Accepted, Location: /experiments/{id}
    Op->>Lab: POST /auth/stream-tickets, then GET /events/stream (SSE)
    loop outbox relay
        Lab->>MQ: publish generation.requested (confirmed, mandatory)
        Lab->>Lab: job dispatched, event job.dispatched
    end
    MQ->>Gen: deliver job (prefetch 1)
    Gen->>LLM: chat completion (rate limit, breaker, retries)
    opt strategy verify_repair
        Gen->>Ev: POST /v1/evaluations (flags of the candidates)
        Gen->>LLM: repair the flagged options (at most 2 rounds)
    end
    Gen->>MQ: publish generation.completed (confirmed)
    Gen->>MQ: ack the job
    MQ->>Lab: deliver result
    Lab->>Lab: inbox check, store questions, job generated
    Lab-->>Op: SSE job.generated
    Lab->>Ev: POST /v1/evaluations (topic text + questions)
    Ev-->>Lab: metrics, bands, flags
    Lab->>Lab: job succeeded, experiment completed when all jobs finished
    Lab-->>Op: SSE job.succeeded, experiment.completed
```

### Job lifecycle

```mermaid
stateDiagram-v2
    [*] --> queued: experiment accepted (job + outbox message in one transaction)
    queued --> dispatched: outbox relay published the job
    dispatched --> generated: generation.completed received
    dispatched --> failed: generation.failed received
    generated --> generated: Evaluator unavailable, retry with growing delay
    generated --> succeeded: questions scored
    succeeded --> [*]
    failed --> [*]
```

*State view of one job.* A job does not time out while it waits in the queue: a stopped Generator only delays
it. A duplicated result (the job ran twice) is ignored, because only `queued` and `dispatched` jobs accept one.

## Blind review study

```mermaid
sequenceDiagram
    autonumber
    actor Op as Operator
    participant Lab
    participant Rev as Review
    actor Ex as Expert
    actor St as Student
    participant MQ as RabbitMQ

    Op->>Lab: POST /studies (experiments, questions per cell, seed)
    Lab->>Lab: stratified sample, new item_ref per question
    Lab->>Rev: POST /internal/v1/studies (operator token, Idempotency-Key = study ID)
    Note over Lab,Rev: only item_ref, topic label, question, options and key: no model, strategy or score
    Rev-->>Lab: 201 expert code, student code
    Lab-->>Op: 201 study with codes
    Ex->>Rev: POST /v1/sessions (code, pseudonym)
    Ex->>Rev: GET /v1/expert/next, PUT /v1/expert/ratings/{item_ref}
    Rev->>Rev: one transaction: rating + outbox event
    St->>Rev: POST /v1/sessions (code, consent)
    St->>Rev: GET /v1/quiz/current, POST /v1/quiz/answers, POST /v1/quiz/feedback
    Rev->>MQ: review.* events (outbox relay)
    MQ->>Lab: deliver
    Lab->>Lab: inbox check, store, join with model and scores
    Lab-->>Op: SSE study events, analytics updated
```

### Student quiz flow

```mermaid
stateDiagram-v2
    [*] --> question: joined with consent, random subset, options shuffled per student
    question --> feedback: answer submitted (locked, time measured on the server)
    feedback --> question: feedback submitted, next question
    feedback --> completed: feedback on the last question
    completed --> [*]
```

*State view of one quiz step.* Questions come strictly in order. A repeated identical answer is accepted
without a second effect; a different answer is rejected with 409. In the feedback step the student sees whether
the answer was right and which option is correct; the key is never sent before the answer is locked. The
clarity, helpfulness and difficulty ratings are therefore given with the correct answer known.

## Live progress (Server-Sent Events)

The Lab stores every progress event with an increasing ID. `GET /events/stream` sends them as
`id: / event: / data:` frames, a `retry: 3000` hint and a comment line every 15 seconds so that proxies do not
drop the idle connection. The browser's `EventSource` cannot send an `Authorization` header, so the client first
requests a **stream ticket**, a JWT valid for 5 minutes and for one channel only, and passes it in the URL.

After a broken connection the browser reconnects with `Last-Event-ID`, and the server continues after that event.
If the ticket has expired, the client requests a new ticket and reopens the stream with `after=<last ID>`, with
backoff and jitter. A stream closes after 15 minutes, so long-lived connections spread over instances. The
gateway forwards the stream without buffering. The same events can also be polled with `GET /events?after=<ID>`.
