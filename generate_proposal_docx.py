import os
import docx
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

def set_cell_background(cell, fill_hex):
    tcPr = cell._element.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
    tcPr.append(shd)

def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    tcPr = cell._element.get_or_add_tcPr()
    tcMar = parse_xml(f'''
        <w:tcMar {nsdecls("w")}>
            <w:top w:w="{top}" w:type="dxa"/>
            <w:bottom w:w="{bottom}" w:type="dxa"/>
            <w:left w:w="{left}" w:type="dxa"/>
            <w:right w:w="{right}" w:type="dxa"/>
        </w:tcMar>
    ''')
    tcPr.append(tcMar)

def set_table_borders(table, color="CCCCCC", sz="4", val="single"):
    tblPr = table._element.xpath('w:tblPr')
    if tblPr:
        borders = parse_xml(f'''
            <w:tblBorders {nsdecls("w")}>
                <w:top w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>
                <w:bottom w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>
                <w:insideH w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>
                <w:insideV w:val="none"/>
                <w:left w:val="none"/>
                <w:right w:val="none"/>
            </w:tblBorders>
        ''')
        tblPr[0].append(borders)

def build_proposal_document(file_path):
    doc = Document()

    # Set Margins (1 inch)
    sections = doc.sections
    for section in sections:
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)

    # Base Colors
    PRIMARY = RGBColor(15, 23, 42)      # Slate 900
    ACCENT = RGBColor(37, 99, 235)      # Blue 600
    MUTED = RGBColor(100, 116, 139)     # Slate 500
    DARK_TEXT = RGBColor(30, 41, 59)    # Slate 800

    # ------------------ TITLE & HEADER ------------------
    title_p = doc.add_paragraph()
    title_p.paragraph_format.space_before = Pt(0)
    title_p.paragraph_format.space_after = Pt(4)
    run_sub = title_p.add_run("PROGRAMMING 5 (PROGRAMOZÁS 5) — PROJECT PROPOSAL\n")
    run_sub.font.name = "Arial"
    run_sub.font.size = Pt(11)
    run_sub.font.bold = True
    run_sub.font.color.rgb = ACCENT

    run_title = title_p.add_run("EduGen: Distributed Microservices Platform for Automated Question Generation, Deterministic Evaluation, and Assessment Delivery")
    run_title.font.name = "Arial"
    run_title.font.size = Pt(20)
    run_title.font.bold = True
    run_title.font.color.rgb = PRIMARY

    # Metadata Box
    meta_table = doc.add_table(rows=4, cols=2)
    meta_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    meta_table.autofit = False

    metadata = [
        ("Course & Faculty:", "Programming 5 (PTE MIK — Faculty of Engineering & IT)"),
        ("Instructor / Professor:", "Prof. Gergely Laborci"),
        ("Student & Neptun ID:", "Rakhi Mst Rokaya Akter (Neptun: ZA0P52)"),
        ("Architectural Target:", "4 Independent Microservices + Web Client (Docker Compose Orchestration)")
    ]

    for i, (k, v) in enumerate(metadata):
        row = meta_table.rows[i]
        c0, c1 = row.cells[0], row.cells[1]
        c0.width = Inches(2.2)
        c1.width = Inches(4.3)
        set_cell_background(c0, "F8FAFC")
        set_cell_background(c1, "F8FAFC")
        set_cell_margins(c0, top=60, bottom=60, left=100, right=100)
        set_cell_margins(c1, top=60, bottom=60, left=100, right=100)
        
        p0 = c0.paragraphs[0]
        p0.paragraph_format.space_after = Pt(2)
        r0 = p0.add_run(k)
        r0.font.name = "Arial"
        r0.font.bold = True
        r0.font.size = Pt(9.5)
        r0.font.color.rgb = DARK_TEXT

        p1 = c1.paragraphs[0]
        p1.paragraph_format.space_after = Pt(2)
        r1 = p1.add_run(v)
        r1.font.name = "Arial"
        r1.font.size = Pt(9.5)
        r1.font.color.rgb = PRIMARY
    
    set_table_borders(meta_table, color="E2E8F0")

    doc.add_paragraph().paragraph_format.space_after = Pt(12)

    # Helper for Section Headings
    def add_h1(text):
        h = doc.add_paragraph()
        h.paragraph_format.space_before = Pt(18)
        h.paragraph_format.space_after = Pt(6)
        h.paragraph_format.keep_with_next = True
        r = h.add_run(text)
        r.font.name = "Arial"
        r.font.size = Pt(14)
        r.font.bold = True
        r.font.color.rgb = PRIMARY
        return h

    def add_h2(text):
        h = doc.add_paragraph()
        h.paragraph_format.space_before = Pt(12)
        h.paragraph_format.space_after = Pt(4)
        h.paragraph_format.keep_with_next = True
        r = h.add_run(text)
        r.font.name = "Arial"
        r.font.size = Pt(11.5)
        r.font.bold = True
        r.font.color.rgb = ACCENT
        return h

    def add_body(text, bold_prefix=None, space_after=6):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(space_after)
        p.paragraph_format.line_spacing = 1.15
        if bold_prefix:
            rb = p.add_run(bold_prefix)
            rb.font.name = "Calibri"
            rb.font.size = Pt(11)
            rb.font.bold = True
            rb.font.color.rgb = DARK_TEXT
        r = p.add_run(text)
        r.font.name = "Calibri"
        r.font.size = Pt(11)
        r.font.color.rgb = DARK_TEXT
        return p

    def add_bullet(bold_prefix, text):
        p = doc.add_paragraph(style='List Bullet')
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.line_spacing = 1.15
        rb = p.add_run(bold_prefix)
        rb.font.name = "Calibri"
        rb.font.size = Pt(10.5)
        rb.font.bold = True
        rb.font.color.rgb = DARK_TEXT
        r = p.add_run(text)
        r.font.name = "Calibri"
        r.font.size = Pt(10.5)
        r.font.color.rgb = DARK_TEXT
        return p

    # ------------------ 1. EXECUTIVE SUMMARY & MOTIVATION ------------------
    add_h1("1. Project Executive Summary & Motivation")
    add_body(
        "Modern university curricula in computer engineering require continuous, diagnostic testing to reinforce complex conceptual mechanisms. "
        "However, constructing high-quality Multiple-Choice Questions (MCQs) manually is notoriously labor-intensive: educators must craft unambiguous "
        "problem stems while formulating plausible, non-trivial distractors (incorrect alternatives). While Large Language Models (LLMs) can generate "
        "questions at high velocity, naive generation suffers from hallucinations, format drifts, and trivial giveaway options."
    )
    add_body(
        "This project proposes EduGen, a cloud-native, distributed microservices platform designed to operationalize Automated Item Generation (AIG) "
        "and empirical pedagogical evaluation. The project directly satisfies all requirements of Programming 5 by implementing 4 decoupled microservices "
        "and a modern client application, managed via Docker Compose. Furthermore, this project directly operationalizes the candidate's BSc thesis research "
        "('LLM Comparative Framework for Automated Technical Question Generation'), transforming an offline research pipeline into a scalable, observable, "
        "and production-grade software system."
    )

    # ------------------ 2. SYSTEM ARCHITECTURE & BOUNDED CONTEXTS ------------------
    add_h1("2. High-Level Architectural Blueprint")
    add_body(
        "The system adheres to Domain-Driven Design (DDD) principles with strict separation of concerns. Rather than an arbitrary technical split, "
        "each microservice encapsulates an independent bounded context with its own distinct lifecycle, data model, and API contracts:"
    )

    arch_table = doc.add_table(rows=6, cols=3)
    arch_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    arch_table.autofit = False

    headers = ["Service Component", "Bounded Domain / Responsibility", "Technology Stack"]
    for j, h in enumerate(headers):
        cell = arch_table.rows[0].cells[j]
        set_cell_background(cell, "1E293B")
        set_cell_margins(cell, top=100, bottom=100, left=120, right=120)
        p = cell.paragraphs[0]
        p.paragraph_format.space_after = Pt(0)
        r = p.add_run(h)
        r.font.name = "Arial"
        r.font.bold = True
        r.font.size = Pt(9.5)
        r.font.color.rgb = RGBColor(255, 255, 255)

    services_summary = [
        ("Service 1: API Gateway & Orchestrator", "Routing, JWT authentication, batch workflow coordination, and real-time generation progress streaming (SSE).", "Python / FastAPI, SQLite, EventSource"),
        ("Service 2: AIG Generation & Multi-Agent Engine", "Prompt injection, LLM provider abstraction (OpenAI / NIM / Mock mode), and multi-agent drafting (Examiner-Critic loop).", "Python / FastAPI, Pydantic, HTTP Client"),
        ("Service 3: Deterministic Evaluation Service", "Independent NLP engine computing 'The Three Pillars': Semantic Alignment, Flesch-Kincaid Complexity, and Distractor Plausibility.", "Python / FastAPI, textstat, scikit-learn, NumPy"),
        ("Service 4: Assessment & Psychometrics Delivery", "Test bank management, timed student quiz delivery, automated scoring, and real-time item difficulty (p-value) analytics.", "Python / FastAPI, SQLite, SQLAlchemy"),
        ("Client Application (Web Portal)", "Interactive Single-Page Application (SPA) offering an Instructor Studio, Live Metric Badges, and a Student Exam Room.", "React 18 / Vite / Tailwind CSS")
    ]

    for i, row_data in enumerate(services_summary, start=1):
        row = arch_table.rows[i]
        for j, val in enumerate(row_data):
            cell = row.cells[j]
            if j == 0:
                cell.width = Inches(2.0)
                set_cell_background(cell, "F1F5F9")
            elif j == 1:
                cell.width = Inches(3.0)
            else:
                cell.width = Inches(1.5)
            set_cell_margins(cell, top=80, bottom=80, left=100, right=100)
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            r = p.add_run(val)
            r.font.name = "Calibri"
            r.font.size = Pt(9.5)
            r.font.color.rgb = DARK_TEXT

    set_table_borders(arch_table, color="CBD5E1")
    doc.add_paragraph().paragraph_format.space_after = Pt(12)

    # ------------------ 3. COMBINED FUNCTIONAL & TECHNICAL SPECIFICATIONS ------------------
    add_h1("3. Combined Functional & Technical Specification Requirements")
    add_body(
        "To provide a rigorous blueprint for evaluation, the functional capabilities (what the system accomplishes for users) "
        "and technical specifications (how the underlying architecture implements them) are paired systematically across every component."
    )

    # 3.1 Service 1
    add_h2("3.1 Service 1: API Gateway & Orchestrator Service")
    add_body("The API Gateway acts as the single entry point for external traffic, managing security, request routing, and lifecycle state.")
    
    add_bullet("FR-1.1 (Centralized Routing & Reverse Proxy): ", "The gateway shall ingest all client requests and dispatch them to downstream services (Generation, Evaluation, Quiz) while shielding internal network topologies.")
    add_bullet("TR-1.1 (Gateway Architecture): ", "Implemented as an asynchronous FastAPI application running on Uvicorn. Exposes CORS-configured REST endpoints and proxies internal microservice requests over an isolated Docker virtual network.")

    add_bullet("FR-1.2 (Role-Based Authentication & Session Handling): ", "The service shall distinguish between Instructor accounts (generation privileges, metric inspection) and Student accounts (quiz-taking privileges only).")
    add_bullet("TR-1.2 (Security Tokens): ", "Issues cryptographically signed JSON Web Tokens (JWT) with HS256 algorithm. Requests to protected endpoints validate claims via dependency injection middleware.")

    add_bullet("FR-1.3 (Pipeline Orchestration & Job Tracking): ", "Allows instructors to initiate a generation-and-evaluation batch run for a selected topic, tracking execution state across stages (INIT -> GENERATING -> EVALUATING -> COMPLETED -> FAILED).")
    add_bullet("TR-1.3 (State Management): ", "Maintains job execution state in an internal SQLite database using Write-Ahead Logging (WAL) to prevent lock contention during parallel status queries.")

    add_bullet("FR-1.4 (Real-Time Generation Progress Streaming): ", "Provides a live progress feed to the client UI as questions are synthesized and evaluated, avoiding long polling.")
    add_bullet("TR-1.4 (Streaming Protocol): ", "Implements Server-Sent Events (SSE) via FastAPI's EventSourceResponse, streaming granular event packets (`status_update`, `question_generated`, `question_evaluated`) to connected clients.")

    # 3.2 Service 2
    add_h2("3.2 Service 2: AIG Generation & Multi-Agent Engine")
    add_body("This service isolates the non-deterministic generative models from the rest of the application, enforcing strict schema validation.")

    add_bullet("FR-2.1 (Multi-Strategy Question Synthesis): ", "Supports multiple question generation strategies: Baseline Zero-Shot (single prompt injection), RAG-grounded generation (retrieving syllabus text chunks), and Multi-Agent refinement (Examiner drafts -> Critic audits distractors -> Editor finalizes).")
    add_bullet("TR-2.1 (Prompt & Pipeline Architecture): ", "Modular template managers format prompts with topic titles, domains, and source texts. Structured outputs are parsed and strictly validated against Pydantic schemas (`MCQItemSchema`: question_stem, options A/B/C/D, correct_option, explanation).")

    add_bullet("FR-2.2 (LLM Provider Abstraction & Dual-Mode Execution): ", "Provides support for live external foundation models (OpenAI GPT-4o, NVIDIA NIM Llama 3.3 / Mistral) alongside a 100% deterministic Local Mock / Replay Mode.")
    add_bullet("TR-2.2 (Offline Resilience & Mock Provider): ", "The Local Mock Provider delivers pre-cached, realistic technical MCQs from the thesis benchmark dataset ($N=2,080$). This guarantees zero dependency on active internet connection, zero API credit costs, and 100% demo stability during professor audits.")

    add_bullet("FR-2.3 (Batch Synthesis Endpoint): ", "Accepts requests specifying topic domain, item count (1 to 10), and model alias, returning structured question objects with latency and token usage metrics.")
    add_bullet("TR-2.3 (API Contract): ", "Exposes `POST /generate/batch` accepting JSON payload `{topic_id, domain, source_text, strategy, model_name, count}` and returning `{questions: [...], latency_seconds, token_usage}`.")

    # 3.3 Service 3
    add_h2("3.3 Service 3: Deterministic Evaluation Service ('The Three Pillars')")
    add_body("A specialized NLP microservice that computes mathematical, non-biased quality metrics without relying on subjective 'AI-judging-AI'.")

    add_bullet("FR-3.1 (Pillar 1 — Semantic Alignment & Hallucination Guard): ", "Computes the factual proximity of the generated question stem to the authorized syllabus reference text to detect hallucinations.")
    add_bullet("TR-3.1 (Mathematical Implementation): ", "Implements Term Frequency-Inverse Document Frequency (TF-IDF) vectorization and Cosine Similarity over normalized n-grams. Emits an alignment score bounded in $[0.0, 1.0]$.")

    add_bullet("FR-3.2 (Pillar 2 — Linguistic Complexity & Readability): ", "Assesses the readability and academic grade level of the question stem to ensure it targets undergraduate engineering students.")
    add_bullet("TR-3.2 (Readability Algorithm): ", "Calculates Flesch-Kincaid Grade Level and Flesch Reading Ease via the `textstat` library using syllable counts and sentence lengths.")

    add_bullet("FR-3.3 (Pillar 3 — Distractor Plausibility & Foil Diversity): ", "Measures how challenging and plausible the incorrect options (foils) are relative to the correct answer, ensuring distractors are not giveaway trivialities.")
    add_bullet("TR-3.3 (Foil-to-Key Similarity Metrics): ", "Computes pairwise Jaccard Token Similarity and lexical overlap between each distractor and the correct answer, plus pairwise inter-distractor divergence to verify distinct misconceptions.")

    add_bullet("FR-3.4 (Automated Quality Gate & Flagging): ", "Flags questions that fail minimal pedagogical criteria (e.g., duplicated options, extreme length imbalance between options, or zero semantic overlap with syllabus).")
    add_bullet("TR-3.4 (Stateless REST Evaluation API): ", "Exposes `POST /evaluate/item` and `POST /evaluate/batch`. Being completely stateless, this service can scale horizontally without shared database locks.")

    # 3.4 Service 4
    add_h2("3.4 Service 4: Assessment & Psychometrics Delivery Service")
    add_body("Bridges automated item generation with authentic educational consumption, simulating real exam sessions and student response analysis.")

    add_bullet("FR-4.1 (Test Bank Repository & Exam Publishing): ", "Maintains approved questions in organized question pools, allowing instructors to package items into published exams with time limits and passing thresholds.")
    add_bullet("TR-4.1 (Persistence Schema): ", "Relational SQLite/PostgreSQL schema tracking `exams` (id, title, duration_minutes), `exam_questions` (foreign keys to approved items), and `student_submissions`.")

    add_bullet("FR-4.2 (Interactive Student Exam Delivery): ", "Serves active exams to students with randomized option shuffling (to prevent positional bias) while hiding the ground-truth key.")
    add_bullet("TR-4.2 (Secure Quiz Payload): ", "Exposes `GET /exams/{id}/take`, returning questions with randomized option labels and strictly sanitizing out `correct_option` and `explanation` until submission.")

    add_bullet("FR-4.3 (Instant Automated Grading & Feedback): ", "Grades student submissions instantaneously upon receipt, providing a final percentage score, pass/fail status, and per-item rationales.")
    add_bullet("TR-4.3 (Grading Logic): ", "Exposes `POST /exams/{id}/submit` receiving student option selections `{question_id: selected_option}`, comparing against ground truth, and writing results to `student_responses`.")

    add_bullet("FR-4.4 (Empirical Psychometric Analytics): ", "Calculates authentic psychometric metrics on delivered questions: Item Difficulty Index ($p$-value = correct responses / total attempts) and Distractor Efficiency (selection frequency of each foil).")
    add_bullet("TR-4.4 (Psychometric Endpoint): ", "Exposes `GET /exams/{id}/analytics` aggregating item statistics. Flags flawed questions where students never chose a distractor (dead distractor) or where $p < 0.20$ (excessively confusing item).")

    # 3.5 Client
    add_h2("3.5 Client Web Application (Frontend)")
    add_body("A responsive, single-page web dashboard providing tailored user experiences for both instructors and students.")

    add_bullet("FR-5.1 (Instructor Studio & Generation Controls): ", "Allows instructors to select topics from computer engineering syllabi (e.g., Computer Networks, Algorithms, Systems Theory), choose model strategies, and trigger batch generation.")
    add_bullet("TR-5.1 (Instructor UI Implementation): ", "Built with React 18, Vite, and Tailwind CSS. Utilizes EventSource listeners to render a live step-by-step progress indicator and dynamically populated question review cards.")

    add_bullet("FR-5.2 (Pillar Metric Inspection Badges): ", "Displays visual color-coded badges for each generated question showing Semantic Alignment, Grade Level, and Distractor Plausibility scores, enabling rapid quality auditing.")
    add_bullet("TR-5.2 (Data Visualization): ", "Integrates lightweight charts/badges illustrating metric distributions and flags low-performing items.")

    add_bullet("FR-5.3 (Student Exam Room): ", "Provides a clean, distraction-free examination view featuring a countdown timer, question navigator, and instant post-submission score review.")
    add_bullet("TR-5.3 (Student UI Implementation): ", "Responsive design supporting desktop and mobile viewports with accessible keyboard navigation.")

    # ------------------ 4. INTER-SERVICE COMMUNICATION ------------------
    add_h1("4. Inter-Service Communication & Sequence Flow")
    add_body(
        "Communication between microservices is mediated via clean, synchronous REST JSON contracts, with Server-Sent Events (SSE) "
        "bridging the Gateway and Client for real-time progress. The sequence diagram below details the end-to-end distributed interactions "
        "across the two core lifecycle phases: (1) Generation & Evaluation, and (2) Exam Publishing & Student Assessment:"
    )

    # Insert Sequence Diagram Image
    img_path = "d:/class_materials/programming5/sequence_diagram.png"
    if os.path.exists(img_path):
        p_img = doc.add_paragraph()
        p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_img.paragraph_format.space_before = Pt(8)
        p_img.paragraph_format.space_after = Pt(4)
        run_img = p_img.add_run()
        run_img.add_picture(img_path, width=Inches(6.2))

        p_cap = doc.add_paragraph()
        p_cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_cap.paragraph_format.space_after = Pt(12)
        r_cap = p_cap.add_run("Figure 1: End-to-End Sequence Diagram illustrating Batch Generation, Three Pillars Evaluation, and Student Assessment Delivery.")
        r_cap.font.name = "Calibri"
        r_cap.font.size = Pt(9.5)
        r_cap.font.italic = True
        r_cap.font.color.rgb = MUTED

    dataflow_steps = [
        ("1. Generation Trigger: ", "Instructor clicks 'Generate' in Client UI. Client dispatches `POST /api/runs` to API Gateway."),
        ("2. Request Dispatch: ", "Gateway creates a Run record (ID: UUID) and dispatches `POST /generate/batch` to Service 2 (AIG Engine)."),
        ("3. Item Synthesis: ", "Service 2 loads syllabus context, formats the prompt template, queries the LLM (or Mock Provider), validates Pydantic schema, and returns JSON MCQs to Gateway."),
        ("4. Metric Evaluation: ", "Gateway dispatches `POST /evaluate/batch` with generated questions and source text to Service 3 (Evaluation Engine)."),
        ("5. Score Computation: ", "Service 3 calculates TF-IDF alignment, Flesch-Kincaid readability, and Jaccard foil plausibility, returning complete metric matrices to Gateway."),
        ("6. Real-Time Streaming: ", "Gateway broadcasts evaluated questions and status updates to Client UI over the open SSE connection."),
        ("7. Exam Publishing: ", "Instructor reviews questions and clicks 'Publish Exam'. Gateway forwards approved items to Service 4 (Quiz Service)."),
        ("8. Student Interaction: ", "Student takes quiz via Client UI; Service 4 records answer choices and updates live psychometric item difficulty indices.")
    ]
    for bold_p, text_p in dataflow_steps:
        add_bullet(bold_p, text_p)

    doc.add_paragraph().paragraph_format.space_after = Pt(8)

    # ------------------ 5. CONTAINERIZATION & DEPLOYMENT ------------------
    add_h1("5. DevOps, Containerization & Deployment (Docker Compose)")
    add_body(
        "To ensure effortless portability across development workstations, faculty evaluation labs, and grading environments, "
        "the entire platform is packaged into containerized services managed by a single root `docker-compose.yml` file:"
    )

    deploy_table = doc.add_table(rows=6, cols=3)
    deploy_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    deploy_table.autofit = False

    dep_headers = ["Docker Container", "Internal Port / Mapping", "Key Responsibilities"]
    for j, h in enumerate(dep_headers):
        cell = deploy_table.rows[0].cells[j]
        set_cell_background(cell, "1E293B")
        set_cell_margins(cell, top=80, bottom=80, left=100, right=100)
        p = cell.paragraphs[0]
        p.paragraph_format.space_after = Pt(0)
        r = p.add_run(h)
        r.font.name = "Arial"
        r.font.bold = True
        r.font.size = Pt(9.5)
        r.font.color.rgb = RGBColor(255, 255, 255)

    dep_data = [
        ("edugen-client", "Port 3000 -> 80 (Nginx)", "Serves compiled React static assets and proxies `/api` calls to Gateway."),
        ("edugen-gateway", "Port 8000 -> 8000 (FastAPI)", "Exposes public API, manages JWT tokens, coordinates inter-service calls, SSE streaming."),
        ("edugen-generator", "Port 8001 (Internal)", "Processes LLM prompts, enforces Pydantic schemas, runs Mock/Live generator."),
        ("edugen-evaluator", "Port 8002 (Internal)", "Computes Three Pillars NLP metrics (Alignment, Grade Level, Plausibility)."),
        ("edugen-quiz", "Port 8003 (Internal)", "Manages exam pools, handles student quiz attempts, grades submissions, computes psychometrics.")
    ]

    for i, row_data in enumerate(dep_data, start=1):
        row = deploy_table.rows[i]
        for j, val in enumerate(row_data):
            cell = row.cells[j]
            if j == 0:
                cell.width = Inches(1.8)
                set_cell_background(cell, "F1F5F9")
            elif j == 1:
                cell.width = Inches(2.2)
            else:
                cell.width = Inches(2.5)
            set_cell_margins(cell, top=70, bottom=70, left=90, right=90)
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            r = p.add_run(val)
            r.font.name = "Calibri"
            r.font.size = Pt(9.0)
            r.font.color.rgb = DARK_TEXT

    set_table_borders(deploy_table, color="CBD5E1")
    doc.add_paragraph().paragraph_format.space_after = Pt(10)

    add_body(
        "One-Command Startup: The professor or evaluator can run the entire distributed infrastructure with zero manual configuration using:\n"
        "`docker compose up --build`\n"
        "All microservice health checks and inter-container DNS resolutions (`http://generator:8001`, `http://evaluator:8002`, etc.) are automated.",
        bold_prefix="Verification & Reproducibility: "
    )

    # ------------------ 6. PROJECT MILESTONES & ROADMAP ------------------
    add_h1("6. Project Milestones & Implementation Roadmap")
    add_body(
        "Development is structured into four sequential, verifiable milestones designed to deliver incremental value:"
    )

    milestones = [
        ("Milestone 1: Architecture & Service Scaffolding (Weeks 1–2)", 
         "Initialize monorepo repository; configure Docker Compose network and shared configuration schemas. Implement Service 3 (Evaluator) with unit tests for The Three Pillars metrics."),
        ("Milestone 2: Generative Engine & Mock Replay Layer (Weeks 3–4)", 
         "Implement Service 2 (AIG Generator) with Pydantic output validation and offline Mock Provider using verified thesis benchmark datasets. Validate batch generation API."),
        ("Milestone 3: Gateway Orchestration & Quiz Delivery (Weeks 5–6)", 
         "Implement Service 1 (API Gateway) with JWT auth and SSE event streaming. Implement Service 4 (Quiz & Psychometrics) with database models and auto-grading algorithms."),
        ("Milestone 4: Client Web Application & Integrated Testing (Weeks 7–8)", 
         "Develop React/Tailwind frontend (Instructor Studio + Student Exam Portal). Execute end-to-end integration tests, package final Docker build, and prepare live demonstration.")
    ]

    for title, desc in milestones:
        add_bullet(title + ": ", desc)

    # ------------------ 7. ACADEMIC & THESIS VALUE ------------------
    add_h1("7. Academic Alignment & Pedagogical Value")
    add_body(
        "This project bridges the gap between academic research and modern software engineering. By adapting the research concepts from the "
        "candidate's BSc thesis into a decoupled microservices architecture, the project provides unique benefits:"
    )
    add_bullet("Complete Domain Justification: ", "Rather than creating an artificial toy example, the microservices cleanly delineate real computational boundaries: high-latency generative AI inference is decoupled from mathematical NLP evaluation, and exam delivery is isolated from backend generation.")
    add_bullet("Pedagogical Reinforcement: ", "Implementing the Three Pillars and psychometric item evaluation in production clarifies the theoretical equations for the candidate's upcoming diploma thesis defense.")
    add_bullet("Guaranteed Evaluation Stability: ", "The built-in dual execution mode (Live API + Mock Replay) ensures that the project can be demonstrated seamlessly in any classroom or grading environment without external API dependencies or latency bottlenecks.")

    # Save Document
    doc.save(file_path)
    print(f"Document successfully created at: {file_path}")

if __name__ == "__main__":
    out_path = "d:/class_materials/programming5/EduGen_Programming5_Project_Proposal_ZA0P52.docx"
    build_proposal_document(out_path)
