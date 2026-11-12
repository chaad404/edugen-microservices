# EduGen: comparing language models on exam-question generation

EduGen is a microservice platform built on my BSc thesis work, *A Comparative Framework for Automated Technical
Multiple-Choice Question Generation Using Large Language Models*. It generates multiple-choice exam questions with
several language models and generation strategies. It scores every question with deterministic text metrics, the
**Three Pillars** framework of the thesis prototype (semantic alignment, readability, distractor plausibility and
diversity). It then lets experts and students evaluate the questions **blind**, so the automatic scores can be
compared with human judgement.

- **Problem:** writing good multiple-choice questions is slow. Language models write them fast, but their
  quality varies by model and by prompting strategy, and automatic metrics alone do not prove that a question
  is correct or useful.
- **Audience:** instructors and researchers who compare models (the Lab), expert reviewers (blind rating) and
  students (an anonymous practice quiz).
- **Current status:** all four services and the web client are implemented. 168 automated tests pass,
  including cross-service contract tests. The whole system runs with `docker compose up --build`, also from a
  fresh clone, and the end-to-end smoke test (`scripts/smoke_test.py`) passes through the gateway. A fresh
  deployment already shows real-model results without any API key: the recorded live run of 23 October 2026
  (four models, 150 questions) and a sample of the thesis prototype's results. Next: one clean re-run with the
  fixed sampling settings, and a pilot review study.

| Service | Responsibility |
|---|---|
| **Lab** | Experiments, generated questions and their scores, model comparison, review studies, live progress (SSE) |
| **Generator** | Generation jobs from a RabbitMQ work queue; four thesis models via OpenRouter, Mistral and Cohere, plus an offline simulator |
| **Evaluator** | Stateless scoring: the Three Pillars, their frozen bands and the item-writing checks |
| **Review** | Blind expert review and an anonymous student quiz; never learns which model wrote a question |

Infrastructure, not counted as services: an nginx gateway that serves the React client, PostgreSQL (one database
per data-owning service) and RabbitMQ.

```bash
cd project
docker compose up --build     # then open http://localhost:8080  (operator / edugen-demo)
```

## Timeline

| Week | Goal / Milestone | Verifiable Result |
|---|---|---|
| 07 (Oct 19–23) | Concept, architecture, the four services, the client, container deployment and documentation; first live-model run | Services in `services/`, React client in `client/`, 147 passing tests, Evaluator reproduces the prototype's metrics; `docker compose up --build` runs the whole system; documents in `docs/` with Mermaid diagrams; live run of 23 October: 30 of 36 jobs, 150 questions (`services/lab/seed/recorded/`) |
| 08 (Oct 26–30) | Fixes from the first live run | Mistral called through its own API; fixed sampling settings and the models' own key letters recorded with every job; expected cost and a true maximum shown before a run (160 tests) |
| 09 (Nov 2–6) | Pause: the thesis's main run used the same model accounts | No change in this week (see the commit history) |
| 10 (Nov 9–13) | Results, thesis alignment and tooling for the review study | [Results](docs/08-results.md) of the live run; per-question results on the study page; recorded runs imported at start-up; simulated study (`scripts/simulate_study.py`); 168 tests; start-up verified from a fresh clone |
| 11 (Nov 16–20) | Clean re-run with the fixed settings, pilot review study, defense preparation | Re-run recorded and described in the results; study with ratings and quiz answers in the Lab; board items closed; demo rehearsed |
| 12 (Nov 23) | Submission | Final repository and demo, submitted before Monday 12:00 |

## GitHub Projects board

Task status (Todo → In progress → Done) is tracked on the public project board:
[github.com/users/chaad404/projects/2](https://github.com/users/chaad404/projects/2).

## Additional Documents

- [Documentation index](docs/README.md)
- [Overview and relation to the thesis](docs/01-overview.md)
- [Architecture](docs/02-architecture.md)
- [Communication and data flows](docs/03-communication.md)
- [API reference](docs/04-api.md)
- [Reliability and security](docs/05-reliability-and-security.md)
- [Architecture decision records](docs/06-decisions.md)
- [Running, demo and testing](docs/07-running-and-testing.md)
- [Results](docs/08-results.md)
- [Course concepts in the code](docs/09-course-concepts.md)
