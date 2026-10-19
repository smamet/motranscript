import type { ReactNode } from "react";

export type ProgressTone = "indigo" | "amber" | "emerald";

const TONE: Record<ProgressTone, { text: string; bar: string }> = {
  indigo: { text: "text-indigo-700 dark:text-indigo-300", bar: "bg-indigo-500" },
  amber: { text: "text-amber-800 dark:text-amber-300", bar: "bg-amber-500" },
  emerald: { text: "text-emerald-700 dark:text-emerald-300", bar: "bg-emerald-500" },
};

export function ProgressBar({
  value,
  label,
  detail,
  tone = "indigo",
  className = "",
  thick = false,
}: {
  value: number;
  label?: ReactNode;
  detail?: ReactNode;
  tone?: ProgressTone;
  className?: string;
  thick?: boolean;
}) {
  const pct = Math.max(0, Math.min(100, value));
  const t = TONE[tone];
  return (
    <div className={className}>
      {(label != null || detail != null) && (
        <div className={`mb-1 flex items-center justify-between text-xs font-medium ${t.text}`}>
          <span>{label}</span>
          {detail != null && <span className="tabular-nums">{detail}</span>}
        </div>
      )}
      <div
        className={`overflow-hidden rounded-full bg-app-hover ${thick ? "h-2" : "h-1.5"}`}
      >
        <div
          className={`h-full rounded-full transition-all duration-500 ${t.bar}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export function ReviewProgress({ done, total }: { done: number; total: number }) {
  const complete = total > 0 && done >= total;
  const pct = total > 0 ? Math.min(100, (done / total) * 100) : 0;
  return (
    <ProgressBar
      className="mt-2.5"
      value={pct}
      tone={complete ? "emerald" : "amber"}
      label={complete ? "Ready to submit" : "In progress"}
      detail={`${done} / ${total}`}
    />
  );
}
