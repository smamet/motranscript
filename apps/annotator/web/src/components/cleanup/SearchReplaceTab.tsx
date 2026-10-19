import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import type {
  MatchSpan,
  ReplacePreviewRow,
  RevisionBatch,
  SearchMode,
  SegmentFilterParams,
} from "../../types";
import { Button, Pill } from "../ui";
import { SegmentClipPlayer } from "./SegmentClipPlayer";

export function SearchReplaceTab({
  filter,
  seed,
}: {
  filter: SegmentFilterParams;
  seed?: { query: string; replacement: string } | null;
}) {
  const [query, setQuery] = useState(seed?.query ?? "");
  const [replacement, setReplacement] = useState(seed?.replacement ?? "");
  const [mode, setMode] = useState<SearchMode>("word");
  const [caseSensitive, setCaseSensitive] = useState(false);
  const [previews, setPreviews] = useState<ReplacePreviewRow[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [batches, setBatches] = useState<RevisionBatch[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (seed) {
      setQuery(seed.query);
      setReplacement(seed.replacement);
      setMode("word");
    }
  }, [seed]);

  const loadBatches = useCallback(async () => {
    try {
      setBatches(await api.cleanupRevisionBatches());
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    void loadBatches();
  }, [loadBatches]);

  async function runPreview() {
    if (!query) return;
    setBusy(true);
    setMsg(null);
    try {
      const rows = await api.cleanupReplacePreview({
        ...filter,
        query,
        replacement,
        mode,
        case_sensitive: caseSensitive,
      });
      setPreviews(rows);
      setSelected(new Set(rows.map((r) => r.segment_id)));
      setMsg(`${rows.length} segment(s) would change`);
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function runApply() {
    const items = previews
      .filter((p) => selected.has(p.segment_id))
      .map((p) => ({
        segment_id: p.segment_id,
        text_before: p.text_before,
      }));
    if (!items.length) return;
    setBusy(true);
    setMsg(null);
    try {
      const result = await api.cleanupReplaceApply({
        query,
        replacement,
        mode,
        case_sensitive: caseSensitive,
        items,
      });
      setMsg(
        `Applied ${result.applied}; skipped ${result.skipped.length} (batch ${result.batch_id.slice(0, 8)})`,
      );
      setPreviews([]);
      setSelected(new Set());
      await loadBatches();
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function runRollback(batchId: string) {
    if (!window.confirm("Rollback this batch?")) return;
    setBusy(true);
    try {
      const r = await api.cleanupRollback(batchId);
      setMsg(`Restored ${r.restored}; skipped ${r.skipped.length}`);
      await loadBatches();
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-2 sm:grid-cols-2">
        <label className="text-sm">
          <span className="mb-1 block text-xs text-app-text-muted">Find</span>
          <input
            className="app-input w-full"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-xs text-app-text-muted">Replace with</span>
          <input
            className="app-input w-full"
            value={replacement}
            onChange={(e) => setReplacement(e.target.value)}
          />
        </label>
      </div>
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <select
          className="app-input"
          value={mode}
          onChange={(e) => setMode(e.target.value as SearchMode)}
        >
          <option value="word">Whole word</option>
          <option value="substring">Substring</option>
          <option value="regex">Regex</option>
        </select>
        <label className="flex items-center gap-1.5">
          <input
            type="checkbox"
            checked={caseSensitive}
            onChange={(e) => setCaseSensitive(e.target.checked)}
          />
          Case sensitive
        </label>
        <Button size="sm" disabled={busy || !query} onClick={() => void runPreview()}>
          Preview
        </Button>
        <Button
          size="sm"
          tone="amber"
          disabled={busy || !selected.size}
          onClick={() => void runApply()}
        >
          Apply selected ({selected.size})
        </Button>
      </div>
      {msg && <p className="text-sm text-app-text-muted">{msg}</p>}

      <ul className="max-h-[28rem] overflow-auto rounded-lg border border-app-border bg-app-surface">
        {previews.length === 0 ? (
          <li className="px-3 py-6 text-center text-sm text-app-text-muted">
            Run Preview to see changes.
          </li>
        ) : (
          previews.map((row) => (
            <li
              key={row.segment_id}
              className="flex gap-3 border-b border-app-border px-3 py-2 text-sm last:border-0"
            >
              <input
                type="checkbox"
                className="mt-1"
                checked={selected.has(row.segment_id)}
                onChange={(e) => {
                  setSelected((prev) => {
                    const next = new Set(prev);
                    if (e.target.checked) next.add(row.segment_id);
                    else next.delete(row.segment_id);
                    return next;
                  });
                }}
              />
              <SegmentClipPlayer segmentId={row.segment_id} />
              <div className="min-w-0 flex-1">
                <div className="mb-1 flex flex-wrap items-center gap-1.5 text-xs text-app-text-muted">
                  <span>#{row.segment_id}</span>
                  <Pill tone={row.review_status === "validated" ? "red" : "slate"}>
                    {row.review_status}
                  </Pill>
                  <Pill tone="slate">{row.status}</Pill>
                  <span>
                    {row.matches.length} change
                    {row.matches.length === 1 ? "" : "s"}
                  </span>
                  <Link
                    to={`/editor/${row.source_id}?segment=${row.segment_id}`}
                    className="ml-auto text-indigo-600 hover:underline dark:text-indigo-400"
                  >
                    Open in editor
                  </Link>
                </div>
                {row.source_title && (
                  <p className="mb-0.5 truncate text-xs text-app-text-subtle">
                    {row.source_title}
                  </p>
                )}
                <p className="whitespace-pre-wrap break-words leading-relaxed text-app-text">
                  {renderInlineReplaceDiff(
                    row.text_before,
                    row.matches,
                    replacement,
                  )}
                </p>
              </div>
            </li>
          ))
        )}
      </ul>

      <section>
        <h3 className="mb-2 text-sm font-medium">History</h3>
        <ul className="divide-y divide-app-border rounded-lg border border-app-border bg-app-surface text-sm">
          {batches.length === 0 ? (
            <li className="px-3 py-4 text-app-text-muted">No replace batches yet.</li>
          ) : (
            batches.map((b) => (
              <li
                key={b.batch_id}
                className="flex flex-wrap items-center gap-2 px-3 py-2"
              >
                <span className="font-mono text-xs">{b.batch_id.slice(0, 8)}</span>
                <span>
                  {b.query} → {b.replacement}
                </span>
                <span className="text-app-text-muted">
                  {b.count} · {b.created_by_email} ·{" "}
                  {new Date(b.created_at).toLocaleString()}
                </span>
                <Button
                  size="sm"
                  variant="muted"
                  className="ml-auto"
                  disabled={busy}
                  onClick={() => void runRollback(b.batch_id)}
                >
                  Rollback
                </Button>
              </li>
            ))
          )}
        </ul>
      </section>
    </div>
  );
}

/** Highlight only the matched spans: deleted (red) → inserted (green). */
function renderInlineReplaceDiff(
  text: string,
  matches: MatchSpan[],
  replacement: string,
): ReactNode {
  if (!matches.length) return text;
  const parts: ReactNode[] = [];
  let cursor = 0;
  const sorted = [...matches].sort((a, b) => a.start - b.start);
  sorted.forEach((m, i) => {
    if (m.start > cursor) parts.push(text.slice(cursor, m.start));
    const removed = text.slice(m.start, m.end);
    parts.push(
      <span key={`d-${i}`} className="inline-flex items-baseline gap-0.5">
        <span className="rounded bg-red-100 px-0.5 text-red-700 line-through dark:bg-red-950/50 dark:text-red-300">
          {removed || "∅"}
        </span>
        <span className="rounded bg-green-100 px-0.5 text-green-800 dark:bg-green-950/50 dark:text-green-300">
          {replacement || "∅"}
        </span>
      </span>,
    );
    cursor = m.end;
  });
  if (cursor < text.length) parts.push(text.slice(cursor));
  return parts;
}
