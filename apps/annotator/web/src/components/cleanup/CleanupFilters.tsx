import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { api } from "../../api/client";
import type {
  Category,
  ReviewStatus,
  SegmentFilterParams,
  SegmentLang,
  SegmentSplit,
  SegmentStatus,
} from "../../types";
import { SEGMENT_LANG_LABELS, SEGMENT_LANGS } from "../../types";

const STATUSES: SegmentStatus[] = ["raw", "corrected", "validated", "ignored"];
const REVIEWS: ReviewStatus[] = ["todo", "done", "validated"];
const SPLITS: SegmentSplit[] = ["train", "test"];

export function CleanupFilters({
  value,
  onChange,
}: {
  value: SegmentFilterParams;
  onChange: (next: SegmentFilterParams) => void;
}) {
  const [categories, setCategories] = useState<Category[]>([]);

  useEffect(() => {
    void api.listCategories().then(setCategories).catch(() => setCategories([]));
  }, []);

  function toggle<T extends string>(key: keyof SegmentFilterParams, item: T) {
    const current = (value[key] as T[] | undefined) ?? [];
    const next = current.includes(item)
      ? current.filter((x) => x !== item)
      : [...current, item];
    onChange({ ...value, [key]: next.length ? next : undefined });
  }

  return (
    <div className="space-y-2 rounded-lg border border-app-border bg-app-surface p-3 text-sm">
      <div className="flex flex-wrap gap-3">
        <label className="flex items-center gap-1.5">
          <span className="text-xs text-app-text-muted">Source ID</span>
          <input
            type="number"
            className="app-input w-24 py-1 text-xs"
            value={value.source_id ?? ""}
            onChange={(e) =>
              onChange({
                ...value,
                source_id: e.target.value ? Number(e.target.value) : null,
              })
            }
          />
        </label>
        <label className="flex items-center gap-1.5">
          <span className="text-xs text-app-text-muted">Category</span>
          <select
            className="app-input py-1 text-xs"
            value={value.category_id ?? ""}
            onChange={(e) =>
              onChange({
                ...value,
                category_id: e.target.value ? Number(e.target.value) : null,
              })
            }
          >
            <option value="">All</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-1.5">
          <input
            type="checkbox"
            checked={!!value.include_validated_sources}
            onChange={(e) =>
              onChange({ ...value, include_validated_sources: e.target.checked })
            }
          />
          <span className="text-xs">Include validated sources</span>
        </label>
      </div>

      <FilterGroup label="Lang">
        {SEGMENT_LANGS.map((lang) => (
          <Chip
            key={lang}
            active={value.lang?.includes(lang)}
            onClick={() => toggle("lang", lang as SegmentLang)}
          >
            {SEGMENT_LANG_LABELS[lang]}
          </Chip>
        ))}
      </FilterGroup>

      <FilterGroup label="Status">
        {STATUSES.map((s) => (
          <Chip
            key={s}
            active={value.status?.includes(s)}
            onClick={() => toggle("status", s)}
          >
            {s}
          </Chip>
        ))}
      </FilterGroup>

      <FilterGroup label="Review">
        {REVIEWS.map((s) => (
          <Chip
            key={s}
            active={value.review_status?.includes(s)}
            onClick={() => toggle("review_status", s)}
          >
            {s}
          </Chip>
        ))}
      </FilterGroup>

      <FilterGroup label="Split">
        {SPLITS.map((s) => (
          <Chip
            key={s}
            active={value.split?.includes(s)}
            onClick={() => toggle("split", s)}
          >
            {s}
          </Chip>
        ))}
      </FilterGroup>
    </div>
  );
}

function FilterGroup({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="w-14 text-xs text-app-text-muted">{label}</span>
      {children}
    </div>
  );
}

function Chip({
  active,
  onClick,
  children,
}: {
  active?: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full px-2 py-0.5 text-xs ${
        active
          ? "bg-indigo-600 text-white"
          : "bg-app-muted text-app-text-muted hover:bg-app-hover"
      }`}
    >
      {children}
    </button>
  );
}
