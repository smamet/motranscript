import type { ReactNode } from "react";
import { useRef, type ChangeEvent, type UIEvent } from "react";
import type { NormalizePreview, WordChange } from "../types";

export function LortografHints({
  value,
  disabled,
  preview,
  showUnknown,
  onShowUnknownChange,
  onChange,
  onBlur,
  onApplyChange,
  onApplyAll,
  applying,
}: {
  value: string;
  disabled?: boolean;
  preview: NormalizePreview | null;
  showUnknown: boolean;
  onShowUnknownChange: (v: boolean) => void;
  onChange: (e: ChangeEvent<HTMLTextAreaElement>) => void;
  onBlur: () => void;
  onApplyChange: (change: WordChange) => void;
  onApplyAll: () => void;
  applying?: boolean;
}) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const mirrorRef = useRef<HTMLDivElement>(null);
  const changes = preview?.changes ?? [];
  const unknown = preview?.unknown_tokens ?? [];

  function syncScroll(e: UIEvent<HTMLTextAreaElement>) {
    if (mirrorRef.current) {
      mirrorRef.current.scrollTop = e.currentTarget.scrollTop;
      mirrorRef.current.scrollLeft = e.currentTarget.scrollLeft;
    }
  }

  return (
    <div>
      <div className="relative">
        <div
          ref={mirrorRef}
          aria-hidden
          className="app-input pointer-events-none absolute inset-0 min-h-40 overflow-auto whitespace-pre-wrap break-words leading-relaxed text-transparent"
        >
          {renderHighlighted(value, changes)}
        </div>
        <textarea
          ref={textareaRef}
          className="app-input relative min-h-40 w-full bg-transparent leading-relaxed disabled:opacity-60"
          value={value}
          disabled={disabled}
          onChange={onChange}
          onBlur={onBlur}
          onScroll={syncScroll}
        />
      </div>

      {(changes.length > 0 || (showUnknown && unknown.length > 0)) && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          {changes.map((c, i) => (
            <button
              key={`${c.start}-${i}`}
              type="button"
              title={`ASR alias, official form: ${c.normalized}`}
              disabled={disabled || applying}
              onClick={() => onApplyChange(c)}
              className="rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 text-xs text-amber-900 hover:bg-amber-100 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100"
            >
              {c.original} → {c.normalized}
            </button>
          ))}
          {changes.length > 0 && (
            <button
              type="button"
              disabled={disabled || applying}
              onClick={onApplyAll}
              className="rounded-full bg-indigo-600 px-2 py-0.5 text-xs text-white hover:bg-indigo-500 disabled:opacity-50"
            >
              Apply all
            </button>
          )}
          {showUnknown && unknown.length > 0 && (
            <span
              className="rounded-full border border-app-border px-2 py-0.5 text-xs text-app-text-muted"
              title={unknown.join(", ")}
            >
              {unknown.length} word{unknown.length === 1 ? "" : "s"} not in lexicon
            </span>
          )}
        </div>
      )}

      <label className="mt-2 flex items-center gap-1.5 text-xs text-app-text-muted">
        <input
          type="checkbox"
          checked={showUnknown}
          onChange={(e) => onShowUnknownChange(e.target.checked)}
        />
        Show unknown words
      </label>
    </div>
  );
}

function renderHighlighted(text: string, changes: WordChange[]) {
  if (!changes.length) return text;
  const sorted = [...changes].sort((a, b) => a.start - b.start);
  const nodes: ReactNode[] = [];
  let cursor = 0;
  sorted.forEach((c, i) => {
    if (c.start > cursor) nodes.push(text.slice(cursor, c.start));
    nodes.push(
      <span
        key={i}
        className="underline decoration-amber-500 decoration-wavy decoration-2"
        style={{ color: "transparent" }}
      >
        {text.slice(c.start, c.end)}
      </span>,
    );
    cursor = c.end;
  });
  if (cursor < text.length) nodes.push(text.slice(cursor));
  return nodes;
}
