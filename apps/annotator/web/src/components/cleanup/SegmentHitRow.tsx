import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import type { MatchSpan, ReviewStatus, SegmentStatus } from "../../types";
import { Pill } from "../ui";
import { SegmentClipPlayer } from "./SegmentClipPlayer";

const REVIEW_TONE: Record<ReviewStatus, "slate" | "amber" | "red"> = {
  todo: "slate",
  done: "amber",
  validated: "red",
};

function highlightText(text: string, matches: MatchSpan[]) {
  if (!matches.length) return text;
  const parts: ReactNode[] = [];
  let cursor = 0;
  const sorted = [...matches].sort((a, b) => a.start - b.start);
  sorted.forEach((m, i) => {
    if (m.start > cursor) parts.push(text.slice(cursor, m.start));
    parts.push(
      <mark key={i} className="rounded bg-amber-200 px-0.5 dark:bg-amber-800/60">
        {text.slice(m.start, m.end)}
      </mark>,
    );
    cursor = m.end;
  });
  if (cursor < text.length) parts.push(text.slice(cursor));
  return parts;
}

export function SegmentHitRow({
  segmentId,
  sourceId,
  sourceTitle,
  reviewStatus,
  status,
  text,
  matches = [],
  meta,
  checked,
  onCheck,
  showCheckbox = true,
}: {
  segmentId: number;
  sourceId: number;
  sourceTitle?: string | null;
  reviewStatus: ReviewStatus;
  status: SegmentStatus;
  text: string;
  matches?: MatchSpan[];
  meta?: ReactNode;
  checked?: boolean;
  onCheck?: (checked: boolean) => void;
  showCheckbox?: boolean;
}) {
  return (
    <li className="flex gap-3 border-b border-app-border px-3 py-2 text-sm last:border-0">
      {showCheckbox && (
        <input
          type="checkbox"
          className="mt-1"
          checked={!!checked}
          onChange={(e) => onCheck?.(e.target.checked)}
        />
      )}
      <SegmentClipPlayer segmentId={segmentId} />
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex flex-wrap items-center gap-1.5 text-xs text-app-text-muted">
          <span>#{segmentId}</span>
          <Pill tone={REVIEW_TONE[reviewStatus]}>{reviewStatus}</Pill>
          <Pill tone="slate">{status}</Pill>
          {meta}
          <Link
            to={`/editor/${sourceId}?segment=${segmentId}`}
            className="ml-auto text-indigo-600 hover:underline dark:text-indigo-400"
          >
            Open in editor
          </Link>
        </div>
        {sourceTitle && (
          <p className="mb-0.5 truncate text-xs text-app-text-subtle">{sourceTitle}</p>
        )}
        <p className="whitespace-pre-wrap break-words text-app-text">
          {highlightText(text, matches)}
        </p>
      </div>
    </li>
  );
}
