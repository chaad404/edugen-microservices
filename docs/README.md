# EduGen Project Documentation

This directory contains the formal architectural specifications, functional and technical requirements, and Mermaid diagrams for **EduGen** (Programming 5 course project under Prof. Gergely Laborci).

## Documentation Index

1. **[System Specifications & Requirements (Markdown)](PROPOSAL_SPECIFICATION.md)**
   - Complete paired Functional Requirements (FR) and Technical Specifications (TR).
   - Domain-Driven Design microservices architecture.
   - Formal Mermaid flowchart and sequence diagram.
   - Docker Compose multi-container deployment parameters.
2. **[Official Word Document Proposal (`.docx`)](EduGen_Programming5_Project_Proposal_ZA0P52.docx)**
   - Formatted course project proposal document.
3. **[High-Resolution Sequence Diagram (`.png`)](sequence_diagram.png)**
   - End-to-end execution flow illustrating generation, evaluation, and student assessment.

## High-Level Architecture (Mermaid)

```mermaid
flowchart TD
    Client["Client Web Application (React SPA)<br/>• Instructor Studio<br/>• Student Exam Room<br/>• Psychometrics Dashboard"]
    Gateway["Service 1: API Gateway & Orchestrator<br/>• Public REST & Reverse Proxy<br/>• JWT Role Security<br/>• Real-Time SSE Streaming"]
    Generator["Service 2: AIG Generation Engine<br/>• Multi-Strategy Synthesis<br/>• Live API & Offline Mock Replay<br/>• Pydantic Schema Validation"]
    Evaluator["Service 3: Deterministic Evaluator<br/>• Pillar 1: Semantic Alignment<br/>• Pillar 2: Linguistic Complexity<br/>• Pillar 3: Distractor Plausibility"]
    Quiz["Service 4: Quiz & Psychometrics<br/>• Question Pool Persistence<br/>• Timed Exam Delivery & Shuffle<br/>• Auto-Grading & Difficulty Index (p)"]

    Client -->|HTTP REST / SSE| Gateway
    Gateway -->|POST /generate/batch| Generator
    Gateway -->|POST /evaluate/batch| Evaluator
    Gateway -->|POST /exams /take /submit| Quiz
```

## System Execution Flow (Mermaid Sequence Diagram)

```mermaid
sequenceDiagram
    autonumber
    actor Instructor as Instructor / Student
    participant Client as Client Web SPA
    participant Gateway as Service 1: API Gateway
    participant Generator as Service 2: AIG Engine
    participant Evaluator as Service 3: Evaluator (Pillars)
    participant Quiz as Service 4: Quiz & Psychometrics

    %% PHASE 1: GENERATION & EVALUATION
    rect rgb(245, 247, 250)
        Note over Instructor, Evaluator: Phase 1: Batch Generation, Three Pillars Evaluation & Real-Time Streaming
        Instructor->>Client: Click "Generate" (Topic, Model, Strategy, Count)
        Client->>Gateway: POST /api/runs (JWT Bearer Token)
        Gateway->>Gateway: Validate JWT & Persist Run (state=INIT)
        Gateway-->>Client: 202 Accepted {run_id: UUID, stream_url}
        Client->>Gateway: GET /api/runs/{run_id}/stream (EventSource SSE)
        Gateway->>Generator: POST /generate/batch {topic_id, strategy, count}
        Generator->>Generator: Render Template -> LLM API / Local Mock Replay
        Generator->>Generator: Validate Pydantic Schema (MCQItemSchema)
        Generator-->>Gateway: 200 OK {questions: [MCQ...], latency, tokens}
        Gateway--)Client: SSE event: status_update (GENERATING -> EVALUATING)
        Gateway->>Evaluator: POST /evaluate/batch {questions, source_text}
        Evaluator->>Evaluator: Compute P1 (Alignment), P2 (Grade Level), P3 (Plausibility)
        Evaluator-->>Gateway: 200 OK {metrics_matrix: [Scores...]}
        Gateway->>Gateway: Persist MCQs & Metrics in SQLite WAL (state=COMPLETED)
        Gateway--)Client: SSE event: batch_completed {questions, metric_badges}
        Client->>Instructor: Render Question Review Cards with Metric Badges
    end

    %% PHASE 2: ASSESSMENT & PSYCHOMETRICS
    rect rgb(240, 244, 248)
        Note over Instructor, Quiz: Phase 2: Exam Publishing, Student Assessment & Live Psychometrics
        Instructor->>Client: Click "Publish Exam" (Select Approved MCQs)
        Client->>Gateway: POST /api/exams/publish {run_id, selected_question_ids}
        Gateway->>Quiz: POST /exams {title, duration_min, questions}
        Quiz-->>Gateway: 201 Created {exam_id, access_code}
        Gateway-->>Client: 200 OK {exam_id, access_code}
        
        Note over Client, Quiz: Student Assessment Session
        Client->>Quiz: GET /api/exams/{id}/take
        Quiz-->>Client: 200 OK {questions: [Stem, Shuffled Foils]} (Keys Hidden)
        Instructor->>Client: Student selects options and clicks "Submit"
        Client->>Quiz: POST /api/exams/{id}/submit {student_answers: {...}}
        Quiz->>Quiz: Auto-grade vs ground truth & Update Item Difficulty Index (p)
        Quiz->>Quiz: Track Distractor Selection Frequencies (Foils efficiency)
        Quiz-->>Client: 200 OK {score, grade, pass_fail, explanations}
        Client->>Instructor: Display Instant Feedback & Rationales
    end
```
