import { useEffect, useState } from "react";
import { HeroBackground } from "./components/HeroBackground";
import { PipelineAnimation } from "./components/PipelineAnimation";
import type { Snapshot, TaskCard, JournalEntry } from "./types";
import { STATUS_LABELS, STATUS_COLORS, KANBAN_GROUPS } from "./types";

/* ── Helpers ─────────────────────────────────── */

function fmtAgo(ts?: number): string {
  if (!ts) return "-";
  const delta = Math.max(0, Math.floor(Date.now() / 1000 - ts));
  if (delta < 60) return `${delta}s ago`;
  if (delta < 3600) return `${Math.floor(delta / 60)}m ago`;
  if (delta < 86400) return `${Math.floor(delta / 3600)}h ago`;
  return `${Math.floor(delta / 86400)}d ago`;
}

function statusBadgeClass(status: string): string {
  if (["running", "completed", "merged", "preparing"].includes(status)) return "badge-teal";
  if (["repairing"].includes(status)) return "badge-orange";
  if (["accepted", "pr_open"].includes(status)) return "badge-violet";
  if (["failed", "rejected"].includes(status)) return "badge-red";
  if (["verifying", "waiting_ci"].includes(status)) return "badge-blue";
  if (["superseded"].includes(status)) return "badge-amber";
  return "badge-gray";
}

/* ── Card Component ──────────────────────────── */

function CardView({ card }: { card: TaskCard }) {
  const labels = [...(card.labels || []), card.source_kind].filter(Boolean);
  const verification = (card.metadata?.verification_steps || [])
    .map((step) => `${step.status} · ${step.command}`)
    .slice(0, 2)
    .join(" | ");
  const borderColor = STATUS_COLORS[card.status] || "#333";

  return (
    <article
      className="card"
      style={{ "--card-accent": borderColor } as React.CSSProperties}
    >
      <div className="card-meta">
        <span>{card.id}</span>
        <span className={`badge ${statusBadgeClass(card.status)}`}>
          {STATUS_LABELS[card.status] || card.status}
        </span>
      </div>
      <h3>{card.title}</h3>
      {card.body && (
        <p className="card-body">{card.body.slice(0, 260)}</p>
      )}
      {labels.length > 0 && (
        <div className="card-tags">
          {labels.map((tag, i) => (
            <span key={i} className="tag">{tag}</span>
          ))}
        </div>
      )}
      <div className="card-footer">
        <div>
          score {card.score} · updated {fmtAgo(card.updated_at)}
          {card.source_ref ? ` · ref ${card.source_ref}` : ""}
        </div>
        <div>{card.metadata?.last_note || "no status note yet"}</div>
        {(verification || card.metadata?.last_ci_summary || card.metadata?.last_failure_summary || card.metadata?.human_gate_pending) && (
          <div>
            {verification || card.metadata?.last_ci_summary || card.metadata?.last_failure_summary ||
              (card.metadata?.human_gate_pending ? "verification passed; human gate pending" : "")}
          </div>
        )}
      </div>
    </article>
  );
}

/* ── Grouped Column Component ────────────────── */

function GroupColumnView({ label, color, cards }: {
  label: string;
  color: string;
  cards: TaskCard[];
}) {
  return (
    <section className="column">
      <div className="column-header">
        <div className="column-title-row">
          <span className="column-dot" style={{ background: color }} />
          <h2>{label}</h2>
        </div>
        <span className="column-count">{cards.length}</span>
      </div>
      <div className="cards">
        {cards.length > 0
          ? cards.map((card) => <CardView key={card.id} card={card} />)
          : <div className="empty">No cards.</div>
        }
      </div>
    </section>
  );
}

/* ── Journal Component ───────────────────────── */

function JournalView({ entries }: { entries: JournalEntry[] }) {
  return (
    <section className="journal">
      <div className="journal-header">
        <span style={{ color: "var(--accent)", fontSize: 10, letterSpacing: 2, fontWeight: 700 }}>
          //
        </span>
        <h2>RECENT JOURNAL</h2>
      </div>
      <div className="journal-list">
        {entries.length > 0
          ? entries.slice().reverse().map((entry, i) => (
              <article key={i} className="journal-item">
                <time>
                  {new Date(entry.timestamp * 1000)
                    .toISOString()
                    .replace("T", " ")
                    .replace(".000Z", " UTC")}
                </time>
                <div>
                  <span className="kind">{entry.kind}</span>
                  {entry.task_id && <span className="task-ref"> [{entry.task_id}]</span>}
                </div>
                <div className="summary">{entry.summary}</div>
              </article>
            ))
          : <div className="empty">Journal is empty.</div>
        }
      </div>
    </section>
  );
}

/* ── Main App ────────────────────────────────── */

export function App() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("./snapshot.json", { cache: "no-store" })
      .then((r) => r.json())
      .then(setSnapshot)
      .catch((e) => setError(String(e)));
  }, []);

  if (error) {
    return (
      <div className="shell" style={{ paddingTop: 80 }}>
        <div className="empty">Failed to load snapshot.json: {error}</div>
      </div>
    );
  }

  if (!snapshot) {
    return (
      <div className="shell" style={{ paddingTop: 80, textAlign: "center" }}>
        <div style={{ color: "var(--accent)", fontSize: 12, letterSpacing: 2 }}>
          LOADING SNAPSHOT...
        </div>
      </div>
    );
  }

  const counts = snapshot.counts || {};
  const normalizedFilter = filter.trim().toLowerCase();

  // Group cards into 4 kanban columns
  const groupedColumns = KANBAN_GROUPS.map((group) => {
    const allCards = group.statuses.flatMap((s) => snapshot.columns?.[s] || []);
    const cards = allCards.filter((card) => {
      if (!normalizedFilter) return true;
      const haystack = [
        card.id, card.title, card.body, card.source_kind, card.source_ref,
        ...(card.labels || []), ...(card.score_reasons || []),
      ].join(" ").toLowerCase();
      return haystack.includes(normalizedFilter);
    });
    return { ...group, cards };
  });

  const inProgress = (counts.preparing || 0) + (counts.running || 0) +
    (counts.verifying || 0) + (counts.waiting_ci || 0) +
    (counts.repairing || 0) + (counts.accepted || 0) + (counts.pr_open || 0);
  const completed = (counts.completed || 0) + (counts.merged || 0);
  const failed = (counts.failed || 0) + (counts.rejected || 0);

  const generated = new Date((snapshot.generated_at || 0) * 1000)
    .toISOString().replace("T", " ").replace(".000Z", " UTC");

  return (
    <>
      {/* ── Hero ─────────────────────────── */}
      <section className="hero">
        <div className="hero-bg">
          <HeroBackground />
        </div>
        <div className="hero-content">
          <div className="hero-main">
            <div className="eyebrow">// AUTOPILOT_KANBAN</div>
            <h1>
              OpenHarness<br />
              <span className="accent">SELF-EVOLUTION</span>
            </h1>
            <p className="hero-sub">
              Kanban for OpenHarness self-evolution.
            </p>
            <div className="focus-box">
              <div className="focus-label">// CURRENT_FOCUS</div>
              <div className="focus-text">
                {snapshot.focus
                  ? `[${snapshot.focus.status}] ${snapshot.focus.title} · score=${snapshot.focus.score} · ${snapshot.focus.source_kind}`
                  : "No active task focus yet."}
              </div>
            </div>
          </div>
          <div className="hero-side">
            <div className="hero-timestamp">
              Generated from repo state at {generated}
            </div>
            <div className="pipeline-viz">
              <PipelineAnimation />
            </div>
          </div>
        </div>
      </section>

      <div className="shell">
        {/* ── Stats Bar ──────────────────── */}
        <section className="stats-bar">
          <div className="stat">
            <div className="stat-label" style={{ color: "#64748b" }}>TO DO</div>
            <div className="stat-value">{counts.queued || 0}</div>
            <div className="stat-sub">queued + accepted</div>
          </div>
          <div className="stat">
            <div className="stat-label teal">IN PROGRESS</div>
            <div className="stat-value">{inProgress}</div>
            <div className="stat-sub">active pipeline</div>
          </div>
          <div className="stat">
            <div className="stat-label" style={{ color: "#3b82f6" }}>IN REVIEW</div>
            <div className="stat-value">
              {(counts.verifying || 0) + (counts.pr_open || 0) + (counts.waiting_ci || 0)}
            </div>
            <div className="stat-sub">verify + PR + CI</div>
          </div>
          <div className="stat">
            <div className="stat-label violet">DONE</div>
            <div className="stat-value">{completed + failed}</div>
            <div className="stat-sub">merged + completed + failed</div>
          </div>
        </section>

        {/* ── Toolbar ────────────────────── */}
        <section className="toolbar">
          <input
            type="search"
            placeholder="Filter by title, body, source, label, or task id..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
          <div className="hint">
            Reads <code>snapshot.json</code> — no backend required
          </div>
        </section>

        {/* ── Kanban Board ───────────────── */}
        <section className="board">
          {groupedColumns.map((group) => (
            <GroupColumnView
              key={group.key}
              label={group.label}
              color={group.color}
              cards={group.cards}
            />
          ))}
        </section>

        {/* ── Journal ────────────────────── */}
        <JournalView entries={snapshot.journal || []} />
      </div>
    </>
  );
}
