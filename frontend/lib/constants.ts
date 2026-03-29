import type { JobStatus, BrandStreamStage } from "./types";

export const TERMINAL_STATUSES: JobStatus[] = ["completed", "failed"];

export const JOB_STATUS_VARIANT: Record<
  JobStatus,
  "default" | "secondary" | "destructive" | "outline"
> = {
  pending: "secondary",
  researching: "outline",
  planning: "outline",
  generating: "outline",
  scoring: "outline",
  reviewing: "outline",
  editing: "outline",
  completed: "default",
  failed: "destructive",
};

export const PIPELINE_STEPS = [
  { key: "researching", label: "Research" },
  { key: "planning", label: "Plan" },
  { key: "generating", label: "Generate" },
  { key: "scoring", label: "Score" },
  { key: "reviewing", label: "Review" },
  { key: "editing", label: "Edit" },
] as const;

export const BRAND_STREAM_STAGES: { key: BrandStreamStage; label: string }[] = [
  { key: "scraping", label: "Scraping Website" },
  { key: "identifying-competitors", label: "Finding Competitors" },
  { key: "generating-prompts", label: "Generating Prompts" },
  { key: "fetching-responses", label: "Fetching AI Responses" },
  { key: "analyzing", label: "Analyzing Mentions" },
  { key: "scoring", label: "Computing Scores" },
  { key: "finalizing", label: "Finalizing" },
];

export const SUB_QUERY_TYPE_LABELS: Record<string, string> = {
  comparative: "Comparative",
  feature_specific: "Feature-Specific",
  use_case: "Use Case",
  trust_signals: "Trust Signals",
  how_to: "How-To",
  definitional: "Definitional",
};
