import type { ComponentType, SVGProps } from "react";
import { ChevronUpDownIcon } from "@heroicons/react/20/solid";

type Icon = ComponentType<SVGProps<SVGSVGElement>>;

export type PillOption = { value: string | number; label: string };

export function PillSelect({
  icon: PillIcon,
  label,
  value,
  placeholder,
  options,
  disabled,
  onChange,
  className = "",
}: {
  icon: Icon;
  label: string;
  value: string | number | null | undefined;
  placeholder: string;
  options: PillOption[];
  disabled?: boolean;
  onChange: (value: string | null) => void;
  className?: string;
}) {
  return (
    <span className={`relative inline-flex items-center ${className}`} title={label}>
      <PillIcon
        className="pointer-events-none absolute left-2 h-3.5 w-3.5 text-app-text-subtle"
        aria-hidden
      />
      <select
        aria-label={label}
        value={value ?? ""}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value || null)}
        className="max-w-[12rem] appearance-none truncate rounded-full border border-app-border bg-app-muted py-1 pl-7 pr-7 text-xs text-app-text transition hover:bg-app-hover focus:outline-none focus:ring-2 focus:ring-indigo-400 disabled:opacity-50"
      >
        <option value="">{placeholder}</option>
        {options.map((o) => (
          <option key={String(o.value)} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <ChevronUpDownIcon
        className="pointer-events-none absolute right-2 h-3.5 w-3.5 text-app-text-subtle"
        aria-hidden
      />
    </span>
  );
}
