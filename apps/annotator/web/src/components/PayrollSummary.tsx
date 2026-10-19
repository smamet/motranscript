import type { PaymentPeriod, User } from "../types";
import { formatHours, formatMur } from "../types";

export { formatMur };

export function PayrollSummary({ user }: { user: User }) {
  const pills = [
    {
      key: "in_progress",
      label: "In progress",
      sec: user.in_progress_audio_sec ?? 0,
      mur: user.in_progress_mur ?? 0,
      className:
        "bg-amber-50 text-amber-900 dark:bg-amber-950/40 dark:text-amber-200",
    },
    {
      key: "done",
      label: "Done",
      sec: user.done_audio_sec ?? 0,
      mur: user.done_mur ?? 0,
      className: "bg-indigo-50 text-indigo-900 dark:bg-indigo-950/40 dark:text-indigo-200",
    },
    {
      key: "validated",
      label: "Validated",
      sec: user.validated_audio_sec ?? 0,
      mur: user.owed_mur ?? 0,
      className:
        "bg-emerald-50 text-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-200",
    },
  ];

  return (
    <div className="flex flex-wrap gap-2 text-sm">
      {pills.map((p) => (
        <span
          key={p.key}
          className={`rounded-full px-2.5 py-0.5 tabular-nums ${p.className}`}
        >
          {p.label}: <strong>{formatHours(p.sec)}</strong>
          {" · "}
          <strong>{formatMur(p.mur)}</strong>
        </span>
      ))}
    </div>
  );
}

function formatWhen(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function PaymentHistory({
  periods,
  showNotes = false,
}: {
  periods: PaymentPeriod[];
  showNotes?: boolean;
}) {
  if (periods.length === 0) {
    return <p className="text-xs text-app-text-muted">No payment periods yet.</p>;
  }
  return (
    <ul className="max-h-64 space-y-1.5 overflow-y-auto text-xs">
      {periods.map((p) => (
        <li
          key={p.id}
          className={`flex flex-wrap gap-x-2 gap-y-0.5 ${
            p.rolled_back_at
              ? "text-app-text-subtle line-through"
              : "text-app-text-muted"
          }`}
        >
          <span>{formatWhen(p.closed_at)}</span>
          <span>{formatHours(p.audio_sec)}</span>
          <span>@ Rs {Number(p.hourly_rate_mur).toFixed(2)}/h</span>
          <strong className="text-app-text">{formatMur(Number(p.amount_mur))}</strong>
          {p.rolled_back_at && <span>(rolled back)</span>}
          {showNotes && p.note && (
            <span className="w-full text-app-text-subtle">Note: {p.note}</span>
          )}
        </li>
      ))}
    </ul>
  );
}
