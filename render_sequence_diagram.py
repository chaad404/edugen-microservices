import matplotlib.pyplot as plt
import matplotlib.patches as patches

def generate_sequence_diagram(output_path="d:/class_materials/programming5/sequence_diagram.png"):
    fig, ax = plt.subplots(figsize=(15, 18), dpi=300)
    ax.set_xlim(0, 11)
    ax.set_ylim(0, 22)
    ax.axis("off")

    # Colors
    c_bg = "#FFFFFF"
    c_line = "#94A3B8"
    c_arrow_req = "#2563EB"   # Blue
    c_arrow_res = "#10B981"   # Emerald green
    c_arrow_sse = "#8B5CF6"   # Purple
    c_box_bg = "#0F172A"      # Slate 900
    c_box_border = "#38BDF8"  # Sky blue
    c_text_main = "#0F172A"
    c_group_bg1 = "#F8FAFC"
    c_group_bg2 = "#F1F5F9"

    # Participants
    participants = [
        {"name": "Client App\n(React Web SPA)", "x": 1.0},
        {"name": "Service 1:\nAPI Gateway", "x": 3.3},
        {"name": "Service 2:\nAIG Engine", "x": 5.6},
        {"name": "Service 3:\nEvaluator (Pillars)", "x": 7.9},
        {"name": "Service 4:\nQuiz & Psychometrics", "x": 10.1},
    ]

    top_y = 21.0
    bot_y = 1.0

    # Draw Group Boxes (Phase 1 & Phase 2)
    # Phase 1: Generation & Evaluation
    rect1 = patches.FancyBboxPatch(
        (0.3, 8.8), 10.4, 11.2,
        boxstyle="round,pad=0.2",
        linewidth=1.2,
        edgecolor="#CBD5E1",
        facecolor=c_group_bg1,
        zorder=0
    )
    ax.add_patch(rect1)
    ax.text(0.5, 19.8, "PHASE 1: BATCH GENERATION, THREE PILLARS EVALUATION & REAL-TIME STREAMING", 
            fontsize=10.5, fontweight="bold", color="#1E293B", va="top")

    # Phase 2: Exam Publishing & Student Assessment
    rect2 = patches.FancyBboxPatch(
        (0.3, 1.2), 10.4, 7.2,
        boxstyle="round,pad=0.2",
        linewidth=1.2,
        edgecolor="#CBD5E1",
        facecolor=c_group_bg2,
        zorder=0
    )
    ax.add_patch(rect2)
    ax.text(0.5, 8.2, "PHASE 2: EXAM PUBLISHING, STUDENT ASSESSMENT & LIVE PSYCHOMETRICS", 
            fontsize=10.5, fontweight="bold", color="#1E293B", va="top")

    # Draw Participant Headers & Lifelines
    for p in participants:
        x = p["x"]
        # Top Box
        hdr = patches.FancyBboxPatch(
            (x - 0.9, top_y - 0.4), 1.8, 0.9,
            boxstyle="round,pad=0.1",
            linewidth=1.5,
            edgecolor=c_box_border,
            facecolor=c_box_bg,
            zorder=3
        )
        ax.add_patch(hdr)
        ax.text(x, top_y + 0.05, p["name"], ha="center", va="center", color="#F8FAFC",
                fontsize=9.5, fontweight="bold", zorder=4)

        # Dashed Lifeline
        ax.plot([x, x], [top_y - 0.5, bot_y], color=c_line, linestyle="--", linewidth=1.2, zorder=1)

        # Bottom Box
        ftr = patches.FancyBboxPatch(
            (x - 0.9, bot_y - 0.7), 1.8, 0.6,
            boxstyle="round,pad=0.1",
            linewidth=1.5,
            edgecolor=c_box_border,
            facecolor=c_box_bg,
            zorder=3
        )
        ax.add_patch(ftr)
        ax.text(x, bot_y - 0.4, p["name"].split("\n")[0], ha="center", va="center", color="#F8FAFC",
                fontsize=8.5, fontweight="bold", zorder=4)

    # Helper function to draw message arrows
    def draw_msg(y, x1, x2, label, sublabel=None, is_res=False, is_sse=False, self_loop=False):
        color = c_arrow_sse if is_sse else (c_arrow_res if is_res else c_arrow_req)
        ls = "--" if is_res else "-"
        
        if self_loop:
            # Self loop arrow on x1
            loop_x = x1 + 0.5
            ax.plot([x1, loop_x, loop_x, x1], [y + 0.2, y + 0.2, y - 0.2, y - 0.2], 
                    color="#475569", linestyle="-", linewidth=1.2, zorder=2)
            ax.annotate("", xy=(x1, y - 0.2), xytext=(loop_x, y - 0.2),
                        arrowprops=dict(arrowstyle="->", color="#475569", lw=1.2), zorder=2)
            ax.text(loop_x + 0.1, y, label, color=c_text_main, fontsize=8.2, va="center", fontweight="bold")
            if sublabel:
                ax.text(loop_x + 0.1, y - 0.25, sublabel, color="#64748B", fontsize=7.5, va="center", style="italic")
            return

        # Direct arrow from x1 to x2
        ax.annotate(
            "", xy=(x2, y), xytext=(x1, y),
            arrowprops=dict(arrowstyle="->", color=color, lw=1.5, ls=ls),
            zorder=2
        )
        mid_x = (x1 + x2) / 2
        ax.text(mid_x, y + 0.12, label, ha="center", va="bottom", color=color, fontsize=8.3, fontweight="bold")
        if sublabel:
            ax.text(mid_x, y - 0.15, sublabel, ha="center", va="top", color="#64748B", fontsize=7.5)

    # ------------------ SEQUENCE MESSAGES ------------------
    # Step 1: POST /api/runs
    draw_msg(19.0, 1.0, 3.3, "1. POST /api/runs (topic_id, strategy, model, count)", 
             "Instructor initiates generation run")

    # Step 2: Validate JWT & Init Run
    draw_msg(18.3, 3.3, 3.3, "2. Validate JWT & Persist Run (state=INIT)", 
             "Writes run record to SQLite WAL", self_loop=True)

    # Step 3: Response with run_id & stream URL
    draw_msg(17.5, 3.3, 1.0, "3. 202 Accepted {run_id: UUID, stream_url}", 
             "Returns immediately to client", is_res=True)

    # Step 4: Client connects to SSE
    draw_msg(16.7, 1.0, 3.3, "4. GET /api/runs/{run_id}/stream (EventSource)", 
             "Client establishes SSE real-time connection", is_sse=True)

    # Step 5: Gateway calls AIG Generator
    draw_msg(15.9, 3.3, 5.6, "5. POST /generate/batch {topic, strategy, count}", 
             "Dispatches generation job")

    # Step 6: Generator processes prompt / LLM / Mock
    draw_msg(15.1, 5.6, 5.6, "6. Prompt Template -> LLM API / Mock Replay", 
             "Pydantic schema validation (MCQItemSchema)", self_loop=True)

    # Step 7: Generator returns MCQs
    draw_msg(14.3, 5.6, 3.3, "7. 200 OK {questions: [MCQ...], latency, tokens}", 
             "Returns verified JSON items", is_res=True)

    # Step 8: Gateway pushes SSE update (status: GENERATED)
    draw_msg(13.6, 3.3, 1.0, "8. SSE event: status_update (GENERATING -> EVALUATING)", 
             "Live progress stream to UI", is_sse=True)

    # Step 9: Gateway calls Evaluator
    draw_msg(12.8, 3.3, 7.9, "9. POST /evaluate/batch {questions, source_text}", 
             "Requests Three Pillars evaluation")

    # Step 10: Evaluator calculates Three Pillars
    draw_msg(12.0, 7.9, 7.9, "10. Compute P1 (Alignment), P2 (Grade), P3 (Plausibility)", 
             "TF-IDF Cosine, Flesch-Kincaid, Jaccard metrics", self_loop=True)

    # Step 11: Evaluator returns metrics
    draw_msg(11.2, 7.9, 3.3, "11. 200 OK {metrics_matrix: [Scores...]}", 
             "Returns mathematical quality scores", is_res=True)

    # Step 12: Gateway updates DB
    draw_msg(10.5, 3.3, 3.3, "12. Persist Questions & Metrics (state=COMPLETED)", 
             "Stores artifacts in relational database", self_loop=True)

    # Step 13: Gateway pushes final SSE event
    draw_msg(9.7, 3.3, 1.0, "13. SSE event: batch_completed {questions + metric_badges}", 
             "UI renders live cards with Pillars scores", is_sse=True)

    # ------------------ PHASE 2: ASSESSMENT ------------------
    # Step 14: Instructor publishes exam
    draw_msg(7.4, 1.0, 3.3, "14. POST /api/exams/publish {run_id, selected_q_ids}", 
             "Instructor selects approved items")

    # Step 15: Gateway delegates to Quiz Service
    draw_msg(6.7, 3.3, 10.1, "15. POST /exams {title, duration_min, questions}", 
             "Persists exam in question bank")

    # Step 16: Quiz service returns exam_id
    draw_msg(6.0, 10.1, 3.3, "16. 201 Created {exam_id, access_code}", 
             "Exam is now active", is_res=True)

    # Step 17: Gateway returns exam details to Instructor
    draw_msg(5.4, 3.3, 1.0, "17. 200 OK {exam_id, access_code}", 
             "Instructor shares code with students", is_res=True)

    # Step 18: Student fetches exam
    draw_msg(4.6, 1.0, 10.1, "18. GET /api/exams/{id}/take", 
             "Student requests exam (options randomly shuffled, key hidden)")

    # Step 19: Quiz Service returns sanitized questions
    draw_msg(3.9, 10.1, 1.0, "19. 200 OK {questions: [Stem, Shuffled Foils]}", 
             "Ground truth key stripped for security", is_res=True)

    # Step 20: Student submits answers
    draw_msg(3.1, 1.0, 10.1, "20. POST /api/exams/{id}/submit {student_answers: {...}}", 
             "Student completes examination")

    # Step 21: Quiz service grades & updates psychometrics
    draw_msg(2.4, 10.1, 10.1, "21. Auto-Grade & Update Item Difficulty Index (p)", 
             "Calculates distractor selection frequencies", self_loop=True)

    # Step 22: Returns score and rationales
    draw_msg(1.7, 10.1, 1.0, "22. 200 OK {score, grade, pass_fail, explanations}", 
             "Instant diagnostic feedback to student", is_res=True)

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Sequence diagram successfully generated at: {output_path}")

if __name__ == "__main__":
    generate_sequence_diagram()
