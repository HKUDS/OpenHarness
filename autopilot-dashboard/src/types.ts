export interface TaskCard {
  id: string;
  title: string;
  body?: string;
  status: string;
  score: number;
  score_reasons?: string[];
  source_kind?: string;
  source_ref?: string;
  labels?: string[];
  updated_at?: number;
  metadata?: {
    last_note?: string;
    last_ci_summary?: string;
    last_failure_summary?: string;
    human_gate_pending?: boolean;
    verification_steps?: { status: string; command: string }[];
  };
}

export interface JournalEntry {
  timestamp: number;
  kind: string;
  task_id?: string;
  summary: string;
}

export interface Snapshot {
  generated_at: number;
  repo_name: string;
  focus?: TaskCard;
  counts: Record<string, number>;
  status_order: string[];
  columns: Record<string, TaskCard[]>;
  cards: TaskCard[];
  journal: JournalEntry[];
}

export const STATUS_LABELS: Record<string, string> = {
  queued: "Queued",
  accepted: "Accepted",
  preparing: "Preparing",
  running: "Running",
  verifying: "Verifying",
  pr_open: "PR Open",
  waiting_ci: "Waiting CI",
  repairing: "Repairing",
  completed: "Completed",
  merged: "Merged",
  failed: "Failed",
  rejected: "Rejected",
  superseded: "Superseded",
};

export const STATUS_COLORS: Record<string, string> = {
  queued: "#64748b",
  accepted: "#8b5cf6",
  preparing: "#0f766e",
  running: "#00d4aa",
  verifying: "#3b82f6",
  pr_open: "#8b5cf6",
  waiting_ci: "#3b82f6",
  repairing: "#ff6b35",
  completed: "#00d4aa",
  merged: "#00d4aa",
  failed: "#ff4444",
  rejected: "#ff4444",
  superseded: "#ffaa00",
};

/** Grouped kanban columns — vibe-kanban style */
export interface KanbanGroup {
  key: string;
  label: string;
  color: string;
  statuses: string[];
}

export const KANBAN_GROUPS: KanbanGroup[] = [
  { key: "todo",        label: "To Do",       color: "#64748b", statuses: ["queued", "accepted"] },
  { key: "in_progress", label: "In Progress", color: "#00d4aa", statuses: ["preparing", "running", "repairing"] },
  { key: "in_review",   label: "In Review",   color: "#3b82f6", statuses: ["verifying", "pr_open", "waiting_ci"] },
  { key: "done",        label: "Done",        color: "#8b5cf6", statuses: ["completed", "merged", "failed", "rejected", "superseded"] },
];
