import { Link } from "react-router-dom";
import {
  ArrowUpTrayIcon,
  ChatBubbleLeftIcon,
  ClockIcon,
  PlayCircleIcon,
  TagIcon,
  UserGroupIcon,
  UserIcon,
} from "@heroicons/react/20/solid";
import type { Category, SourceListItem } from "../types";
import { Button, buttonClass, Meta, Pill, PillSelect, ProgressBar, ReviewProgress } from "./ui";
import { SourceAudioPreview, sourceHasAudioPreview } from "./SourceAudioPreview";
import { SystemAlerts } from "./SystemAlerts";

const PHASE_ICON: Record<string, string> = {
  completed: "✓",
  running: "●",
  failed: "✗",
  cancelled: "—",
  pending: "○",
  skipped: "–",
};

const STATUS_PILL: Record<string, "red" | "amber" | "indigo" | "muted"> = {
  failed: "red",
  cancelled: "amber",
  processing: "indigo",
  pending: "muted",
};

export function YoutubeLink({
  url,
  children,
  className = "hover:underline",
}: {
  url: string | null | undefined;
  children: string;
  className?: string;
}) {
  if (!url) return children;
  return (
    <a href={url} target="_blank" rel="noopener noreferrer" className={className}>
      {children}
    </a>
  );
}

export function SourceCard({
  source,
  onCancel,
  onDelete,
  onRetranscribe,
  onResume,
  onMarkDone,
  onReopen,
  onValidate,
  onReject,
  onCategoryChange,
  categories,
  onClaim,
  onAssign,
  operators,
  currentUserId,
  selectable,
  selected,
  onToggleSelect,
  busy,
  isAdmin,
}: {
  source: SourceListItem;
  onCancel: (id: number) => void;
  onDelete: (id: number) => void;
  onRetranscribe: (id: number) => void;
  onResume: (id: number) => void;
  onMarkDone: (id: number) => void;
  onReopen: (id: number) => void;
  onValidate: (id: number) => void;
  onReject: (id: number) => void;
  onCategoryChange?: (id: number, categoryId: number | null) => void;
  categories?: Category[];
  onClaim?: (id: number) => void;
  onAssign?: (id: number, userId: number | null) => void;
  operators?: { id: number; email: string }[];
  currentUserId?: number;
  selectable?: boolean;
  selected?: boolean;
  onToggleSelect?: (id: number) => void;
  busy: boolean;
  isAdmin: boolean;
}) {
  const { pipeline } = source;
  const isActive = source.status === "pending" || source.status === "processing";
  const isDownloaded = source.status === "downloaded";
  const showPipeline =
    isActive || source.status === "failed" || source.status === "cancelled";
  const showAudio = sourceHasAudioPreview(source.status, source.duration_sec);
  const isReady = source.status === "ready";
  const review = source.review_status;
  const unassigned = source.assigned_to_user_id == null;
  const canClaim =
    Boolean(onClaim) &&
    isReady &&
    review === "todo" &&
    unassigned &&
    Boolean(currentUserId);
  const canEditAssigned =
    isAdmin || source.assigned_to_user_id === currentUserId;
  const showAssignSelect = isAdmin && Boolean(onAssign) && isReady && review === "todo" && operators;
  const showCategorySelect =
    isAdmin && Boolean(onCategoryChange) && categories && categories.length > 0;
  const assigneeLabel = unassigned
    ? "Unassigned"
    : source.assigned_to_email ?? `user #${source.assigned_to_user_id}`;
  const speakerCount =
    isReady && pipeline.diarization_status === "ok" ? pipeline.speaker_count : null;
  const statusTone = STATUS_PILL[source.status];
  const showReviewProgress =
    isReady && review === "todo" && (source.can_mark_done || source.partial);

  return (
    <li
      className={`app-card p-4 transition ${
        source.partial
          ? "border-amber-300 bg-amber-50/60 dark:border-amber-800/60 dark:bg-amber-950/30"
          : selected
            ? "ring-2 ring-indigo-400 dark:ring-indigo-500"
            : ""
      }`}
    >
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="flex min-w-0 flex-1 gap-3">
          {selectable && (
            <input
              type="checkbox"
              className="mt-1 h-4 w-4 shrink-0 accent-indigo-600"
              checked={!!selected}
              disabled={busy || !isDownloaded}
              onChange={() => onToggleSelect?.(source.id)}
              aria-label={`Select ${source.title ?? source.id}`}
            />
          )}
          <div className="min-w-0 flex-1">
            <p className="truncate text-[15px] font-semibold leading-snug">
              {source.title ?? source.original_filename ?? `Source ${source.id}`}
            </p>

            <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs">
              <Meta
                icon={source.source_type === "youtube" ? PlayCircleIcon : ArrowUpTrayIcon}
                className="text-indigo-600 dark:text-indigo-400"
              >
                <YoutubeLink url={source.source_url}>{source.source_type}</YoutubeLink>
              </Meta>
              {source.duration_sec ? (
                <Meta icon={ClockIcon}>
                  <span className="tabular-nums">{formatDuration(source.duration_sec)}</span>
                  {isReady && source.segment_count > 0 && (
                    <span className="text-app-text-subtle">
                      · net {formatDuration(source.net_audio_sec ?? 0)}
                    </span>
                  )}
                </Meta>
              ) : null}
              {speakerCount != null && (
                <Meta icon={UserGroupIcon}>
                  {speakerCount} speaker{speakerCount === 1 ? "" : "s"}
                </Meta>
              )}
              {statusTone && <Pill tone={statusTone}>{source.status}</Pill>}
            </div>

            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs empty:hidden">
              {showAssignSelect ? (
                <PillSelect
                  icon={UserIcon}
                  label="Assign to"
                  value={source.assigned_to_user_id}
                  placeholder="Unassigned"
                  options={operators!.map((op) => ({ value: op.id, label: op.email }))}
                  disabled={busy}
                  onChange={(v) => onAssign!(source.id, v ? Number(v) : null)}
                />
              ) : (
                isReady && (
                  <Meta
                    icon={UserIcon}
                    className={
                      unassigned ? "text-app-text-subtle" : "text-sky-700 dark:text-sky-300"
                    }
                  >
                    {assigneeLabel}
                  </Meta>
                )
              )}
              {showCategorySelect ? (
                <PillSelect
                  icon={TagIcon}
                  label="Category"
                  value={source.category?.id}
                  placeholder="No category"
                  options={categories!.map((c) => ({ value: c.id, label: c.label }))}
                  disabled={busy}
                  onChange={(v) => onCategoryChange!(source.id, v ? Number(v) : null)}
                />
              ) : (
                source.category && (
                  <Meta icon={TagIcon} className="text-violet-700 dark:text-violet-300">
                    {source.category.label}
                  </Meta>
                )
              )}
            </div>

            {showReviewProgress && (
              <ReviewProgress
                done={source.can_mark_done ? source.segment_count : source.touched_count}
                total={source.segment_count}
              />
            )}
            {source.review_note && review === "todo" && (
              <p className="mt-2 rounded-md border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-xs text-amber-900 dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-amber-200">
                <span className="font-medium">Admin note:</span> {source.review_note}
              </p>
            )}
            {source.comment_count > 0 && review === "todo" && (
              <Meta icon={ChatBubbleLeftIcon} className="mt-2 text-xs text-amber-700 dark:text-amber-400">
                {source.comment_count} segment comment{source.comment_count > 1 ? "s" : ""} to
                review
              </Meta>
            )}
            {showAudio && (
              <SourceAudioPreview
                sourceId={source.id}
                durationSec={source.duration_sec}
              />
            )}
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap justify-end gap-1.5">
          {canClaim && (
            <Button
              size="sm"
              variant="outline"
              tone="sky"
              disabled={busy}
              onClick={() => onClaim?.(source.id)}
            >
              Take
            </Button>
          )}
          {isReady && canEditAssigned && (
            <Link
              to={`/editor/${source.id}`}
              className={buttonClass({ variant: "primary", size: "sm" })}
            >
              Edit
            </Link>
          )}
          {isReady && review === "todo" && source.can_mark_done && canEditAssigned && (
            <Button
              size="sm"
              variant="outline"
              tone="green"
              disabled={busy}
              onClick={() => onMarkDone(source.id)}
            >
              Done
            </Button>
          )}
          {isReady && review === "done" && canEditAssigned && (
            <Button size="sm" disabled={busy} onClick={() => onReopen(source.id)}>
              Reopen
            </Button>
          )}
          {isAdmin && isReady && review === "done" && (
            <Button
              size="sm"
              variant="outline"
              tone="green"
              disabled={busy}
              onClick={() => onValidate(source.id)}
            >
              Validate
            </Button>
          )}
          {isAdmin && isReady && (review === "done" || review === "validated") && (
            <Button
              size="sm"
              variant="outline"
              tone="amber"
              disabled={busy}
              onClick={() => onReject(source.id)}
            >
              Send back
            </Button>
          )}
          {isAdmin &&
            (source.status === "failed" ||
              (source.status === "ready" && review === "todo")) && (
            <Button size="sm" disabled={busy} onClick={() => onRetranscribe(source.id)}>
              Re-transcribe
            </Button>
          )}
          {isAdmin &&
            (source.status === "cancelled" || source.status === "failed") &&
            !source.duration_sec && (
              <Button
                size="sm"
                variant="outline"
                tone="indigo"
                disabled={busy}
                onClick={() => onResume(source.id)}
              >
                Resume
              </Button>
            )}
          {isAdmin && pipeline.can_cancel && (
            <Button
              size="sm"
              variant="outline"
              tone="amber"
              disabled={busy}
              onClick={() => onCancel(source.id)}
            >
              Cancel
            </Button>
          )}
          {isAdmin && pipeline.can_delete && (
            <Button
              size="sm"
              variant="outline"
              tone="red"
              disabled={busy}
              onClick={() => onDelete(source.id)}
            >
              Delete
            </Button>
          )}
        </div>
      </div>

      {showPipeline && isActive && (
        <ProgressBar
          className="mb-3"
          thick
          value={pipeline.overall_progress}
          tone="indigo"
          label={pipeline.current_label}
          detail={`${pipeline.overall_progress.toFixed(0)}%`}
        />
      )}

      {showPipeline && (
        <ul className="space-y-1 text-xs">
          {pipeline.phases.map((phase) => (
            <li
              key={phase.id}
              className={`flex items-center gap-2 ${
                phase.status === "running"
                  ? "text-indigo-600 dark:text-indigo-300"
                  : phase.status === "completed"
                    ? "text-app-text-muted"
                    : phase.status === "failed"
                      ? "text-red-600 dark:text-red-400"
                      : "text-app-text-subtle"
              }`}
            >
              <span className="w-3 text-center">{PHASE_ICON[phase.status] ?? "○"}</span>
              <span className="flex-1">{phase.label}</span>
              {(phase.status === "running" || phase.status === "skipped") && phase.detail && (
                <span className="truncate text-app-text-subtle">{phase.detail}</span>
              )}
            </li>
          ))}
        </ul>
      )}

      {source.alerts && source.alerts.length > 0 && (
        <SystemAlerts alerts={source.alerts} className="mt-2" compact />
      )}

      {source.error && <p className="app-alert-error mt-2 text-xs">{source.error}</p>}

      {source.status === "cancelled" && (
        <p className="mt-2 text-xs text-app-text-subtle">
          {isAdmin
            ? "Cancelled — click Resume to continue, or Delete to remove."
            : "Cancelled — ask an admin to resume or delete."}
        </p>
      )}

      {isDownloaded && (
        <p className="mt-2 text-xs text-app-text-subtle">
          Audio ready — select and Send to To do to run ASR.
        </p>
      )}

      {isActive && (
        <p className="mt-2 text-xs text-app-text-subtle">{pipeline.restart_note}</p>
      )}
    </li>
  );
}

function formatDuration(sec: number): string {
  const total = Math.round(sec);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return s ? `${m}m ${s}s` : `${m}m`;
  return `${s}s`;
}
