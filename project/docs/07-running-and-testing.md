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

Operator sign-in: `operator` / `edugen-demo`. No configuration is needed for a local demo. To change something,
copy `.env.example` to `.env`:

- **Ports.** `EDUGEN_PORT` and `RABBITMQ_CONSOLE_PORT`, if 8080 or 15672 is taken.
- **Passwords and signing keys.** Set them before the system is reachable by other people.
- **Live models.** `OPENROUTER_API_KEY`, `MISTRAL_API_KEY` and `COHERE_API_KEY`. Runs with them cost money; the Lab
  shows the expected cost and a maximum, and asks for confirmation.

Stop with `docker compose down`; add `-v` to delete the databases as well.

## What a fresh deployment contains

Nothing has to be generated, and no API key is needed, to see real results. At start-up the Lab imports:

| Data | Origin shown in the Lab | Contents |
|---|---|---|
| Live run of 23 October 2026 | `recorded run` | 36 jobs of four real models on the three demo topics: 150 questions with scores and flags, the job traces, and six failed jobs with their errors |
| Clean re-run of 15 November 2026 | `recorded run` | The same 36 jobs with the fixed sampling settings and Mistral through its own API: all succeeded, 180 questions with scores and flags, the job traces with the settings and the key letters as the models wrote them |
| Thesis prototype sample | `prototype sample` | 108 questions of the prototype's October 2026 comparison with the scores it recorded |
| Three demo topics | – | TCP congestion control, REST-style HTTP APIs, linear time-invariant systems; written for this project |

All three data sets are described in [08 Results](08-results.md). New experiments can always use the offline
simulator. Its questions are synthetic and marked as simulated; it exists to show the pipeline, not to compare models.

## Demo script (about 10 minutes)

1. **Lab → Experiments → the live run of 23 October.** *Comparison*: with the baseline prompt the keys sit at
   one letter (key-position chart), and the group that lost jobs is marked. *Jobs*: each job shows its route and
   what the repair loop did; the six failed Mistral jobs show HTTP 429 and the open circuit. Then **the clean
   re-run of 15 November**: every job succeeded and shows its sampling settings, and the key-position chart shows
   the letters the models wrote under every strategy.
2. **New experiment:** topic *TCP congestion control*, model *Offline simulator*, all three strategies,
   5 questions. The answer is `202 Accepted`, and the page follows the jobs live over SSE.
3. **Failure handling:** `docker compose stop evaluator` while the experiment runs. Jobs stay *generated* and
   show "waiting for the Evaluator". `docker compose start evaluator`: they are scored and the experiment finishes.
4. **Scaling:** `docker compose up -d --scale generator=3`, start another experiment, and watch three consumers on
   the queue `generator.jobs` in the RabbitMQ console.
5. **Review studies → New study** from the clean re-run, topic *TCP congestion control*, one question per cell
   (12 questions). Open the expert link in a private window, enter a pseudonym and rate a few questions: no model is
   visible. Open the student link, accept the notice and answer: the options are shuffled and an answer cannot
   be changed.
6. **Study page with data:** run `python scripts/simulate_study.py` and open the study it prints. Ratings and
   answers arrive live; agreement, correlations and the per-question table fill up. These participants are
   simulated, so the numbers demonstrate the flow and nothing else.

## A review study with people

A short session needs a small study that every participant sees in full.

1. **Create the study.** *Review studies → New study*: choose one experiment and one topic, one question per
   cell. One topic of a complete run gives 12 questions (4 models × 3 strategies). Set *Questions per student* to
   the same number.
2. **Make it reachable.** Open the Lab at an address the participants can reach, for example
   `http://<this machine's LAN IP>:8080`. The study page builds the two links from the address in the browser, so
   links copied from `localhost` work only on this machine. A phone hotspot is the simplest shared network;
   campus networks often block traffic between devices. Outside `localhost` and HTTPS the browser has no
   clipboard access, so copy the visible link.
3. **Hand out the links.** Reviewers get the expert link and choose a pseudonym; with the same pseudonym they
   can continue later. Students get the quiz link, read the notice and agree. Both work on a phone.
4. **Plan the time.** Allow about 15 minutes for rating 12 questions and about 10 for a quiz of 12. These are
   estimates; no session with people has been timed yet.
5. **What is needed for the numbers.** Agreement needs at least two reviewers on the same questions. A
   correlation needs at least five questions with both values. A question is judged too hard or too easy from
   three answers on. A wrong option counts as unused only from 20 answers on: with a few answers, options stay
   unchosen by chance.
6. **Read the results** on the study page. Only the operator sees which model wrote a question.

The gateway allows 10 new sessions per minute from one address, with a burst of 10. A larger group behind one
shared address joins over a minute or two.

## Scripts

The first three need only the Python standard library and a running deployment.

| Script | Purpose |
|---|---|
| `scripts/smoke_test.py [base URL]` | End-to-end check through the gateway: login, an experiment followed over SSE, a blind study, the way of ratings and answers back to the Lab |
| `scripts/simulate_study.py [base URL]` | A study with simulated raters and students (see the demo script). `--topic` limits it to a topic, `--experiment` chooses the source |
| `scripts/export_run.py <experiment id> <file>` | Writes a finished experiment as a recorded-run file |
| `scripts/export_thesis_sample.py`, `scripts/verify_against_thesis.py` | Read the prototype's database, which is not public: the sample export, and the check that the Evaluator reproduces the prototype's scores |

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
| Generator | 57 | Registry (fixed settings, measured output per question), providers against mocked HTTP (routing, Mistral's own API, the settings in each API's names, 429, non-retryable codes), backoff, circuit breaker, rate limiter, simulator, all strategies and the key letters they record, the cause of a failed verify-repair job, job failures, consumer acknowledgement and dead-lettering |
| Lab | 41 | Login and token checks, 202 + outbox, recorded settings and job trace, key positions as the model wrote them, paid-model guard, expected cost and its true maximum, idempotency keys, inbox, evaluation retry, SSE resume, comparison and its leaders, prototype sample import, recorded-run import, stratified sampling with a topic filter, blindness of the study payload, review events, item analysis, Krippendorff's alpha (reference example 0.743), Spearman |
| Review | 21 | Study contract (extra fields rejected), idempotent creation, expert order and revisions, linear quiz, answer lock, the key revealed only after the answer is stored, option shuffling, record-level authorization |
| Cross-service | 5 | The four real services connected through their APIs and message handlers: an experiment with all strategies, a blind study and its way back to the Lab, a run exported from one Lab and imported into another, outbox safety, the Lab's cost bound against the Generator's call limits |

## Recorded runs

Results of a live run exist only in the database of the machine that made it. To let every deployment show them,
a finished experiment can be shipped as a file:

```bash
python scripts/export_run.py <experiment id> services/lab/seed/recorded/<name>.json --name "Title to show"
docker compose up -d --build lab        # the Lab imports every file in seed/recorded/ once
```

The file holds the jobs with their traces, the questions and the scores they got, as the operator API returns
them. It never holds a topic text, and the script refuses to write anything that looks like a credential. An
imported run has the origin `recorded` and its original date; it is not recomputed and never shown as a run of
the importing deployment. Publish a run only if its topics may be published, as the demo topics may.

## Prototype data

`services/lab/seed/thesis_sample.json` is a public sample of the prototype's October 2026 comparison: 3 topics ×
4 models × 3 conditions, 3 questions per call, with the scores the prototype recorded. It was produced by
`scripts/export_thesis_sample.py` from the prototype's database, opened read-only. Topic texts, prompts with
topic text and raw outputs are never exported.

For a local comparison of all topics (not committed):

```bash
python scripts/export_thesis_sample.py <prototype app.db> data/local/thesis_full.json --full
# then set THESIS_SAMPLE_FILE=/path/to/thesis_full.json for the Lab on an empty database
```

`scripts/verify_against_thesis.py` scores prototype questions with the Evaluator code and compares the result
with the stored scores. On 60 questions the largest difference was 0.00005, which is the rounding of the output.
