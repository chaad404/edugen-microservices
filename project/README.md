# EduGen: comparing language models on exam-question generation

EduGen is a microservice platform built on my BSc thesis, *LLM Comparative Framework for Automated Technical
Question Generation*. It generates multiple-choice exam questions with several language models and generation
strategies. It scores every question with the thesis's deterministic **Three Pillars** framework (semantic
alignment, readability, distractor plausibility and diversity). It then lets experts and students evaluate the
questions **blind**, so the automatic scores can be compared with human judgement.

- **Problem:** writing good multiple-choice questions is slow. Language models write them fast, but their
  quality varies by model and by prompting strategy, and automatic metrics alone do not prove that a question
  is correct or useful.
- **Audience:** instructors and researchers who compare models (the Lab), expert reviewers (blind rating) and
  students (an anonymous practice quiz).
- **Current status:** all four services and the web client are implemented. 160 automated tests pass,
  including cross-service contract tests. The whole system runs with `docker compose up --build`, and the
  end-to-end smoke test (`scripts/smoke_test.py`) passes through the gateway. Next: the live-model run and a
  pilot review study.

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
| 07 (Oct 19–23) | Concept, architecture and implementation of the four services and the client | Services in `services/`, React client in `client/`, 147 passing tests, Evaluator reproduces the thesis metrics |
| 08 (Oct 26–30) | Container deployment and documentation | `docker compose up --build` runs the whole system; documents in `docs/` with Mermaid diagrams |
| 09 (Nov 2–6) | Live-model run and pilot study | One small experiment with the thesis models (cost estimate shown before start); a pilot review study opened |
| 10 (Nov 9–13) | Pilot with reviewers and students | Ratings and quiz answers collected; agreement and correlations shown in the Lab |
| 11 (Nov 16–20) | Fixes from the pilot, defense preparation | Board items closed; demo script rehearsed |
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
