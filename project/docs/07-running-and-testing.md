# 07 Running, demo and testing

## Start

Requirements: Docker Desktop (or Docker Engine with Compose v2), about 3 GB of free memory, ports 8080 and 15672.

```bash
cd project
docker compose up --build
```

The first build downloads the base images and the embedding model (about 90 MB). Then open:

| Address | What |
|---|---|
| http://localhost:8080 | The client: Lab, expert review, student quiz |
| http://localhost:8080/api/lab/docs | OpenAPI page of the Lab (`/api/review/docs` for the Review service) |
| http://localhost:15672 | RabbitMQ console (user `edugen`, password `edugen-dev-password`) |

Operator sign-in: `operator` / `edugen-demo`. Copy `.env.example` to `.env` to change passwords. To use the live
thesis models, add `OPENROUTER_API_KEY`, `MISTRAL_API_KEY` and `COHERE_API_KEY`; runs with them cost money and
must be confirmed.

Stop with `docker compose down`; add `-v` to delete the databases as well.

For a study with other people, open the Lab at an address they can reach (for example `http://<this machine's
LAN IP>:8080`): the study page builds the expert and student links from the address in the browser, so links copied
from `localhost` only work on this machine. Outside `localhost` and HTTPS the browser has no clipboard API, so copy
the visible link instead of using *Copy link*.

## Demo script (about 10 minutes)

1. **Lab → Experiments.** The imported thesis sample is already there. Open it: the comparison shows that each
   pillar has a different leader and that the keys are biased towards A and B (key-position chart).
2. **New experiment:** topic *TCP congestion control*, model *Offline simulator*, all three strategies,
   5 questions. The answer is `202 Accepted`, and the page follows the jobs live over SSE.
3. **Failure handling:** `docker compose stop evaluator` while the experiment runs. Jobs stay *generated* and
   show "waiting for the Evaluator". `docker compose start evaluator`: they are scored and the experiment finishes.
4. **Scaling:** `docker compose up -d --scale generator=3`, start another experiment, and watch three consumers on
   the queue `generator.jobs` in the RabbitMQ console.
5. **Review studies → New study** from the thesis sample, one question per cell. Open the expert link in a private
   window, enter a pseudonym and rate a few questions: no model is visible. Open the student link, accept the
   notice and answer: the options are shuffled and an answer cannot be changed.
6. **Study page:** the ratings and answers arrive live; agreement and correlations appear when enough data exists.

## Tests

The tests run offline with SQLite and stand-ins for the embedding model and the broker.

```bash
cd project
python -m venv .venv
.venv/Scripts/python -m pip install -r services/lab/requirements.txt -r services/review/requirements.txt \
    -r services/generator/requirements.txt -r services/evaluator/requirements.txt pytest
cd services/evaluator && ../../.venv/Scripts/python -m pytest && cd ../..   # likewise generator, lab, review
.venv/Scripts/python -m pytest tests                                         # cross-service contracts
```

On Linux and macOS the interpreter is `.venv/bin/python`.

| Suite | Tests | Covers |
|---|---|---|
| Evaluator | 45 | Metrics on known values, band edges, every flag, batch checks, the problem-detail errors, dense model missing |
| Generator | 50 | Providers against mocked HTTP (routing, Mistral's own API, 429, non-retryable codes), backoff, circuit breaker, rate limiter, simulator, all strategies, job failures, consumer acknowledgement and dead-lettering |
| Lab | 31 | Login and token checks, 202 + outbox, paid-model guard, idempotency keys, inbox, evaluation retry, SSE resume, comparison, thesis import, stratified sampling, blindness of the study payload, review events, Krippendorff's alpha (reference example 0.743), Spearman |
| Review | 21 | Study contract (extra fields rejected), idempotent creation, expert order and revisions, linear quiz, answer lock, the key revealed only after the answer is stored, option shuffling, record-level authorization |
| Cross-service | 3 | The four real services connected through their APIs and message handlers: an experiment with all strategies, a blind study and its way back to the Lab, outbox safety |

## Thesis data

`services/lab/seed/thesis_sample.json` is a public sample of the October 2026 comparison: 3 topics × 4 models ×
3 conditions, 3 questions per call, with the scores recorded by the thesis. It was produced by
`scripts/export_thesis_sample.py` from the thesis database, opened read-only. Topic texts, prompts and raw
outputs are never exported.

For a local comparison of all topics (not committed):

```bash
python scripts/export_thesis_sample.py <thesis app.db> data/local/thesis_full.json --full
# then set THESIS_SAMPLE_FILE=/path/to/thesis_full.json for the Lab on an empty database
```

`scripts/verify_against_thesis.py` scores thesis questions with the Evaluator code and compares the result with
the stored thesis scores. On 60 questions the largest difference was 0.00005, which is the rounding of the output.
