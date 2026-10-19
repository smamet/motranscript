import type { ButtonHTMLAttributes, ComponentType, ReactNode, SVGProps } from "react";

export type ButtonTone = "sky" | "green" | "amber" | "indigo" | "red" | "slate";
export type ButtonVariant = "primary" | "solid" | "outline" | "secondary" | "muted";
export type ButtonSize = "sm" | "md";

type Icon = ComponentType<SVGProps<SVGSVGElement>>;

const OUTLINE: Record<ButtonTone, string> = {
  sky: "border-sky-300 text-sky-800 hover:bg-sky-50 dark:border-sky-800/60 dark:text-sky-300 dark:hover:bg-sky-950/40",
  green:
    "border-green-300 text-green-800 hover:bg-green-50 dark:border-green-800/60 dark:text-green-300 dark:hover:bg-green-950/40",
  amber:
    "border-amber-300 text-amber-800 hover:bg-amber-50 dark:border-amber-800/60 dark:text-amber-300 dark:hover:bg-amber-950/40",
  indigo:
    "border-indigo-300 text-indigo-700 hover:bg-indigo-50 dark:border-indigo-800/60 dark:text-indigo-300 dark:hover:bg-indigo-950/40",
  red: "border-red-300 text-red-700 hover:bg-red-50 dark:border-red-900/60 dark:text-red-300 dark:hover:bg-red-950/40",
  slate:
    "border-slate-300 text-slate-700 hover:bg-slate-50 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800/60",
};

const SOLID: Record<ButtonTone, string> = {
  sky: "bg-sky-600 text-white hover:bg-sky-500",
  green: "bg-green-600 text-white hover:bg-green-500",
  amber: "bg-amber-600 text-white hover:bg-amber-500",
  indigo: "bg-indigo-600 text-white hover:bg-indigo-500",
  red: "bg-red-600 text-white hover:bg-red-500",
  slate: "bg-slate-600 text-white hover:bg-slate-500",
};

const SIZE: Record<ButtonSize, string> = {
  sm: "px-2.5 py-1.5 text-xs",
  md: "px-3 py-2 text-sm",
};

export function buttonClass({
  variant = "secondary",
  tone = "indigo",
  size = "md",
  className = "",
}: {
  variant?: ButtonVariant;
  tone?: ButtonTone;
  size?: ButtonSize;
  className?: string;
} = {}): string {
  const base =
    "inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition disabled:opacity-50";
  let look: string;
  switch (variant) {
    case "primary":
      look = "bg-indigo-600 text-white shadow-sm hover:bg-indigo-500";
      break;
    case "solid":
      look = `${SOLID[tone]} shadow-sm`;
      break;
    case "outline":
      look = `border ${OUTLINE[tone]}`;
      break;
    case "muted":
      look = "bg-app-muted text-app-text hover:bg-app-hover";
      break;
    default:
      look = "border border-app-border bg-app-surface text-app-text hover:bg-app-hover";
  }
  return `${base} ${SIZE[size]} ${look} ${className}`.trim();
}

export function Button({
  variant = "secondary",
  tone = "indigo",
  size = "md",
  icon: Icon,
  className = "",
  children,
  type = "button",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  tone?: ButtonTone;
  size?: ButtonSize;
  icon?: Icon;
  children?: ReactNode;
}) {
  return (
    <button
      type={type}
      className={buttonClass({ variant, tone, size, className })}
      {...rest}
    >
      {Icon && <Icon className="h-4 w-4 shrink-0" aria-hidden />}
      {children}
    </button>
  );
}
