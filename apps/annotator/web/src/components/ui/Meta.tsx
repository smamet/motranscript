import type { ComponentType, ReactNode, SVGProps } from "react";

type Icon = ComponentType<SVGProps<SVGSVGElement>>;

export function Meta({
  icon: MetaIcon,
  className = "text-app-text-muted",
  children,
}: {
  icon: Icon;
  className?: string;
  children: ReactNode;
}) {
  return (
    <span className={`inline-flex items-center gap-1 ${className}`}>
      <MetaIcon className="h-3.5 w-3.5 shrink-0 opacity-70" aria-hidden />
      {children}
    </span>
  );
}

export type PillTone =
  | "indigo"
  | "sky"
  | "amber"
  | "emerald"
  | "green"
  | "red"
  | "violet"
  | "slate"
  | "muted";

const PILL_TONE: Record<PillTone, string> = {
  indigo: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/50 dark:text-indigo-300",
  sky: "bg-sky-100 text-sky-800 dark:bg-sky-950/50 dark:text-sky-200",
  amber: "bg-amber-100 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300",
  emerald: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300",
  green: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300",
  red: "bg-red-100 text-red-700 dark:bg-red-950/50 dark:text-red-300",
  violet: "bg-violet-100 text-violet-700 dark:bg-violet-950/50 dark:text-violet-300",
  slate: "bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200",
  muted: "bg-app-muted text-app-text-muted",
};

export function Pill({
  tone = "muted",
  className = "",
  children,
}: {
  tone?: PillTone;
  className?: string;
  children: ReactNode;
}) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ${PILL_TONE[tone]} ${className}`}
    >
      {children}
    </span>
  );
}
