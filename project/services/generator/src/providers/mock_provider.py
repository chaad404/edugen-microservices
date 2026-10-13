import re
import time
import random
from typing import List, Tuple
from .base import BaseLLMProvider
from ..schemas import GenerateBatchRequest, GeneratedMCQ

# Pre-cached benchmark questions derived from thesis runs
VERIFIED_BENCHMARK = [
    {
        "domain": "SYSTEM",
        "question_stem": "In linear time-invariant (LTI) systems, what does the transfer function H(s) represent mathematically?",
        "option_a": "The ratio of the Laplace transform of the output Y(s) to the input X(s)",
        "option_b": "The time derivative of the continuous state vector x(t)",
        "option_c": "The discrete Fourier transform of the unit step response",
        "option_d": "The eigenvalue determinant of the feedthrough matrix D",
        "correct_option": "A",
        "explanation": "H(s) = Y(s)/X(s) is the Laplace ratio representing system dynamics in the s-domain."
    },
    {
        "domain": "SYSTEM",
        "question_stem": "Which state-space matrix directly maps input signals u(t) to the derivative of state variables x'(t)?",
        "option_a": "Input matrix B",
        "option_b": "State matrix A",
        "option_c": "Output matrix C",
        "option_d": "Feedthrough matrix D",
        "correct_option": "A",
        "explanation": "In x'(t) = Ax(t) + Bu(t), B maps inputs to state variable derivatives."
    },
    {
        "domain": "SYSTEM",
        "question_stem": "What distinguishes a closed-loop control system fundamentally from an open-loop system?",
        "option_a": "Presence of a feedback loop that compares sensor output to a target setpoint",
        "option_b": "Exclusive use of discrete-time digital microcontrollers",
        "option_c": "Absence of actuators in the forward control signal path",
        "option_d": "Guaranteed zero transient settling time under all disturbances",
        "correct_option": "A",
        "explanation": "Closed-loop systems employ output feedback to adjust control actions dynamically."
    },
    {
        "domain": "NETCOMP",
        "question_stem": "During TCP congestion control, which event signals the transition from Slow Start to Congestion Avoidance?",
        "option_a": "Congestion window (cwnd) reaches or exceeds the slow start threshold (ssthresh)",
        "option_b": "Receipt of a single duplicate acknowledgment (ACK)",
        "option_c": "Expiration of the persistent Keep-Alive timer",
        "option_d": "Negotiation of the Maximum Segment Size (MSS) during SYN handshake",
        "correct_option": "A",
        "explanation": "When cwnd >= ssthresh, TCP switches from exponential growth to linear growth."
    },
    {
        "domain": "NETCOMP",
        "question_stem": "How does Fast Retransmit in TCP detect packet loss prior to Retransmission Timeout (RTO) expiration?",
        "option_a": "Arrival of three consecutive duplicate ACKs from the receiver",
        "option_b": "Explicit ICMP Source Quench notification from a router",
        "option_c": "Calculation of negative smoothed round-trip time (SRTT)",
        "option_d": "Reset flag (RST) injection by the transport gateway",
        "correct_option": "A",
        "explanation": "Three duplicate ACKs prompt the sender to retransmit the missing segment immediately."
    },
    {
        "domain": "SPECALK",
        "question_stem": "In Dijkstra's single-source shortest path algorithm, what fundamental restriction is placed on edge weights?",
        "option_a": "All edge weights must be strictly non-negative",
        "option_b": "The graph must be a directed acyclic graph (DAG)",
        "option_c": "All vertex degrees must be bounded by O(log V)",
        "option_d": "Edge capacities must follow integer conservation constraints",
        "correct_option": "A",
        "explanation": "Dijkstra assumes non-negative edge weights; negative edges require Bellman-Ford."
    }
]

class MockLLMProvider(BaseLLMProvider):
    """Deterministic local provider serving verified curriculum questions offline."""

    def generate(self, req: GenerateBatchRequest) -> Tuple[List[GeneratedMCQ], int, float]:
        start_time = time.time()
        
        # Filter matching domain questions if available
        domain = (req.domain or "SYSTEM").upper()
        candidates = [q for q in VERIFIED_BENCHMARK if q["domain"] == domain]
        if not candidates:
            candidates = VERIFIED_BENCHMARK

        # Select count questions (cyclically if needed)
        selected = []
        for i in range(req.count):
            template = candidates[i % len(candidates)]
            item = GeneratedMCQ(
                question_stem=template["question_stem"],
                option_a=template["option_a"],
                option_b=template["option_b"],
                option_c=template["option_c"],
                option_d=template["option_d"],
                correct_option=template["correct_option"],
                explanation=template["explanation"],
                strategy_used=req.strategy
            )
            selected.append(item)

        tokens = req.count * 350
        cost = round((tokens / 1000.0) * 0.005, 5)  # Simulated token cost
        return selected, tokens, cost
