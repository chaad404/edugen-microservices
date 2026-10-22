# 06 Architecture decision records

Each record states the situation, the alternatives, the decision, its consequences and a checkable condition
for reviewing it.

## ADR 1: Four services instead of a modular monolith

**Situation.** The course requires three to four microservices and a client. Independent of that requirement, the
split has to be justified: a distributed system pays for every boundary with network calls, partial failure
and operations.

**Alternatives.**
1. Modular monolith: one deployment unit with Lab, generation, evaluation and review modules.
2. Service-based: two coarse services (research and review) sharing one database.
3. Four services along the boundaries below.

**Decision.** Four services, because each boundary separates something that differs in one of the quality aspects:

| Boundary | Aspect | Reason |
|---|---|---|
| Generator | Failure handling, scaling, cost | External calls that take minutes, cost money and fail with HTTP 429. Isolated, they cannot block the Lab; scaled by adding workers |
| Evaluator | Scaling, deployability | CPU-bound and stateless with a 90 MB model; used by two callers; changes only when the framework changes |
| Review | Data management, availability, security | Different users and sensitive data; must keep working during a study while experiments are changed or restarted; blindness by not owning model data |
| Lab | Data ownership | The single owner of experiments and of the item → model mapping |

**Consequences.** Network calls and eventual consistency: human results reach the Lab after a delay, and scores
lag generation. The system needs a broker, an outbox, an inbox and idempotent consumers. Operations need one
compose file and per-service health checks. The modulith would have been simpler; its weak point is that a
stuck or failing LLM call and a running student study would share one process and one release.

**Review when.** The Generator and Lab always change and release together for three milestones in a row, or one
team maintains all services and the broker causes more incidents than the LLM hosts. Then merge Lab and
Generator.

## ADR 2: A message queue for generation

**Situation.** A generation job takes from a second (simulator) to several minutes (verify → repair with a slow
host), and hosts reject bursts with HTTP 429. In the thesis, batches had to be resumed by hand after rate limits.

**Alternatives.** A synchronous HTTP call from the Lab; HTTP with `202 Accepted` and polling of the Generator;
a durable work queue.

**Decision.** RabbitMQ work queue `generator.jobs` with competing consumers, prefetch 1, persistent messages,
publisher confirms and a dead-letter queue. Results return as events. Retries of LLM calls happen in exactly
one layer, the Generator, so they do not multiply.

**Consequences.** Jobs survive restarts and wait while no Generator runs; more Generators share the work. In
exchange there is a pending state to show to the user, at-least-once delivery (duplicates must be ignored) and
one more component to operate.

**Review when.** Jobs need priorities or a deadline that a plain queue cannot express, or more than 10 Generator
instances are needed.

## ADR 3: The Evaluator is called synchronously

**Situation.** Scoring takes about a second and is deterministic. The Lab cannot mark a job finished without
it, and the verify → repair strategy needs the flags before the next step.

**Alternatives.** A synchronous call; an evaluation queue with result events.

**Decision.** Synchronous `POST /v1/evaluations` with a time limit. The Lab stores the generated questions first
and scores them in a background loop that retries while the Evaluator is unavailable.

**Consequences.** Simple request–response with an immediate answer, and no extra queue. An Evaluator outage
delays scoring but loses nothing.

**Review when.** Scoring a batch takes longer than 10 seconds, or the Evaluator becomes a shared service for
other systems.

## ADR 4: Server-Sent Events for live progress

**Alternatives.** Polling, long polling, SSE, WebSocket.

**Decision.** SSE. Progress flows only from the server to the browser, and SSE adds automatic reconnection with
`Last-Event-ID`. Events are stored, so a reconnecting client receives what it missed. Commands still use normal
HTTP requests. A polling endpoint over the same events exists as a fallback.

**Consequences.** One open connection per watching browser, a gateway without buffering, and a ticket in the URL
because `EventSource` cannot send headers. Tickets live 5 minutes and are valid for one channel.

**Review when.** Operators need to send frequent commands over the same channel (two-way); then WebSocket.

## ADR 5: Blindness by data ownership

**Situation.** The thesis requires that neither experts nor students can see which model wrote a question
(UI.2.1, TR.1.3).

**Alternatives.** Send everything to the Review service and hide fields in its API; send only what a reviewer
may see.

**Decision.** The Lab sends only `item_ref`, topic label, question, options and key. The mapping back to model and
strategy exists only in the Lab, and the Review contract rejects any extra field.

**Consequences.** A programming error in the Review API cannot reveal the model, because the data is not there.
Analytics that combine human results with models run in the Lab, which therefore needs the review events.

**Review when.** Reviewers must see generation details on purpose (for example an unblinded second round).

## ADR 6: One database server, one database per service

**Alternatives.** A shared schema; one database server per service; one server with separate databases and roles.

**Decision.** One PostgreSQL server with the databases `lab` and `review`, each owned by its own role, and
`CONNECT` revoked from everyone else. The Generator and Evaluator are stateless.

**Consequences.** Data ownership is enforced by the database permissions, with one server to operate. The server
is a shared operational dependency, not a shared data model.

**Review when.** The two services need different database versions, backups or capacity.

## ADR 7: Signed tokens with a shared key

**Decision.** HS256 JWTs. The Review service verifies the Lab's operator tokens with the same key.
Participant tokens use a separate key known only to the Review service.

**Consequences.** Simple key management for one trust domain. A service that can verify an operator token can
also create one. Asymmetric keys (RS256 with a published public key) would remove that.

**Review when.** A service outside this deployment needs to verify tokens, or the services are operated by
different teams.

## ADR 8: An offline simulator next to the real models

**Situation.** Demos and tests must run without API keys, cost or network, but the thesis rule forbids passing off
synthetic output as a model's.

**Decision.** A simulator provider answers the same prompts in the same JSON format with synthetic cloze
questions built from the topic text. It is a separate registry entry, always labelled `simulated`, and never used
as a fallback for a real model.

**Consequences.** The whole pipeline (queue, retries, verify → repair, scoring, SSE) can be shown offline. Its
questions are obviously synthetic, so model comparisons come from the imported thesis results or from live runs.

**Review when.** A free, local model (for example through Ollama) is fast enough on the demo machine.
