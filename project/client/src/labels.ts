// Human-readable names for codes used by the API.

export const STRATEGY_LABELS: Record<string, string> = {
  baseline: "Baseline (zero-shot)",
  prompt_v2: "Prompt v2 + key balancing",
  verify_repair: "Verify → repair → select",
  rag: "RAG (thesis)",
  multi_agent: "Multi-agent (thesis)",
};

export const DOMAIN_LABELS: Record<string, string> = {
  NETCOMP: "Computer networks",
  SPECALK: "Application development",
  SYSTEM: "Systems theory",
  OTHER: "Other",
};

export const PILLARS = [
  { key: "P1", name: "Alignment", metric: "alignment", hint: "Stays on the source material" },
  { key: "P2", name: "Readability", metric: "grade", hint: "Flesch-Kincaid grade, target 10–14" },
  { key: "P3a", name: "Plausibility", metric: "plausibility", hint: "Distractors tempting, not ≥ 0.80" },
  { key: "P3b", name: "Diversity", metric: "diversity", hint: "Distractors make different mistakes" },
] as const;

export const FLAG_LABELS: Record<string, string> = {
  off_topic: "Off topic",
  stem_too_simple: "Stem too simple",
  stem_too_dense: "Stem too dense",
  too_close: "Distractor ≈ key",
  weak: "Weak distractor",
  same_mistake: "Two distractors, same mistake",
  length_cue: "Key is the longest",
  evidence_not_in_context: "Evidence not in source",
  evidence_supports: "Evidence supports a distractor",
  invalid_schema: "Invalid question",
};

export const strategyLabel = (key: string) => STRATEGY_LABELS[key] ?? key;
export const flagLabel = (flag: string) => {
  const [code, targets] = flag.split(":");
  return targets ? `${FLAG_LABELS[code] ?? code} (${targets})` : FLAG_LABELS[code] ?? code;
};
