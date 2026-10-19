import type { ReactNode } from "react";
import type { BulkNormalizeResult, NormalizePreview, WordChange } from "../types";

interface NormalizeModalProps {
  title: string;
  previews: NormalizePreview[];
  onApply: () => void;
  onClose: () => void;
  applying?: boolean;
}

export function NormalizeModal({
  title,
  previews,
  onApply,
  onClose,
  applying = false,
}: NormalizeModalProps) {
  const changed = previews.filter((p) => p.changed);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 dark:bg-black/60">
      <div className="max-h-[80vh] w-full max-w-2xl overflow-hidden rounded-xl border border-app-border bg-app-surface shadow-xl">
        <div className="border-b border-app-border px-4 py-3">
          <h2 className="font-medium">{title}</h2>
          <p className="text-xs text-app-text-muted">
            {changed.length} of {previews.length} segment(s) would change
          </p>
        </div>
        <ul className="max-h-96 space-y-3 overflow-y-auto p-4">
          {changed.length === 0 ? (
            <li className="space-y-2 text-sm text-app-text-muted">
              <p>All Kreol/mix segments already match Lortograf.</p>
              {previews.some((p) => p.unknown_tokens?.length > 0) && (
                <p className="text-xs text-amber-700 dark:text-amber-400/90">
                  Some segments contain words not in the lexicon — check segment previews.
                </p>
              )}
            </li>
          ) : (
            changed.map((p) => (
              <li key={p.segment_id} className="rounded-md border border-app-border p-3 text-sm">
                <p className="mb-1 text-xs text-app-text-subtle">Segment #{p.segment_id}</p>
                <p className="whitespace-pre-wrap break-words leading-relaxed text-app-text">
                  {renderNormalizeInlineDiff(p.original, p.changes)}
                </p>
                {p.changes.length > 0 && (
                  <p className="mt-2 text-xs text-app-text-subtle">
                    {p.changes.map((c) => `${c.original} → ${c.normalized}`).join(", ")}
                  </p>
                )}
              </li>
            ))
          )}
        </ul>
        <div className="flex justify-end gap-2 border-t border-app-border px-4 py-3">
          <button type="button" onClick={onClose} className="app-btn-secondary">
            Cancel
          </button>
          {changed.length > 0 && (
            <button
              type="button"
              disabled={applying}
              onClick={onApply}
              className="app-btn-primary"
            >
              {applying ? "Applying…" : "Apply all"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export function SegmentNormalizePreview({
  preview,
  onAccept,
  onReject,
}: {
  preview: NormalizePreview;
  onAccept: () => void;
  onReject: () => void;
}) {
  if (!preview.changed) {
    return (
      <div className="rounded-md border border-app-border bg-app-muted p-3 text-sm text-app-text-muted">
        <p>Spelling already matches Lortograf.</p>
        {preview.unknown_tokens?.length > 0 && (
          <p className="mt-2 text-xs text-amber-700 dark:text-amber-400/90">
            Unknown to lexicon: {preview.unknown_tokens.join(", ")}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="rounded-md border border-indigo-200 bg-indigo-50 p-3 text-sm dark:border-indigo-900/50 dark:bg-indigo-950/30">
      <p className="mb-2 text-xs font-medium text-indigo-700 dark:text-indigo-300">
        Lortograf suggestion
      </p>
      <p className="whitespace-pre-wrap break-words leading-relaxed text-app-text">
        {renderNormalizeInlineDiff(preview.original, preview.changes)}
      </p>
      {preview.changes.length > 0 && (
        <p className="mt-2 text-xs text-app-text-subtle">
          {preview.changes.map((c) => `${c.original} → ${c.normalized}`).join(", ")}
        </p>
      )}
      <div className="mt-3 flex gap-2">
        <button type="button" onClick={onAccept} className="app-btn-primary px-2.5 py-1.5 text-xs">
          Accept
        </button>
        <button type="button" onClick={onReject} className="app-btn-secondary px-2.5 py-1.5 text-xs">
          Reject
        </button>
      </div>
    </div>
  );
}

/** Highlight only changed spans: deleted (red) → inserted (green). */
export function renderNormalizeInlineDiff(
  text: string,
  changes: WordChange[],
): ReactNode {
  if (!changes.length) return text;
  const parts: ReactNode[] = [];
  let cursor = 0;
  const sorted = [...changes].sort((a, b) => a.start - b.start);
  sorted.forEach((c, i) => {
    if (c.start > cursor) parts.push(text.slice(cursor, c.start));
    parts.push(
      <span key={i} className="inline-flex items-baseline gap-0.5">
        <span className="rounded bg-red-100 px-0.5 text-red-700 line-through dark:bg-red-950/50 dark:text-red-300">
          {c.original}
        </span>
        <span className="rounded bg-green-100 px-0.5 text-green-800 dark:bg-green-950/50 dark:text-green-300">
          {c.normalized}
        </span>
      </span>,
    );
    cursor = c.end;
  });
  if (cursor < text.length) parts.push(text.slice(cursor));
  return parts;
}

export type { BulkNormalizeResult };
