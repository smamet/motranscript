import { useMemo, useState } from "react";
import { Navigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../../auth/AuthProvider";
import type { SegmentFilterParams } from "../../types";
import { AppHeader } from "../AppHeader";
import { AuditTab } from "./AuditTab";
import { CleanupFilters } from "./CleanupFilters";
import { LexiconTab } from "./LexiconTab";
import { SearchReplaceTab } from "./SearchReplaceTab";
import { VocabularyTab } from "./VocabularyTab";

type Tab = "audit" | "vocabulary" | "replace" | "lexicon";

const TABS: { id: Tab; label: string }[] = [
  { id: "audit", label: "Audit" },
  { id: "vocabulary", label: "Vocabulary" },
  { id: "replace", label: "Search & Replace" },
  { id: "lexicon", label: "Lexicon" },
];

function parseFilter(params: URLSearchParams): SegmentFilterParams {
  const source = params.get("source_id");
  const category = params.get("category_id");
  return {
    source_id: source ? Number(source) : null,
    category_id: category ? Number(category) : null,
    lang: params.getAll("lang") as SegmentFilterParams["lang"],
    status: params.getAll("status") as SegmentFilterParams["status"],
    review_status: params.getAll("review_status") as SegmentFilterParams["review_status"],
    split: params.getAll("split") as SegmentFilterParams["split"],
    include_validated_sources: params.get("include_validated_sources") === "true",
  };
}

function writeFilter(f: SegmentFilterParams): URLSearchParams {
  const q = new URLSearchParams();
  if (f.source_id != null) q.set("source_id", String(f.source_id));
  if (f.category_id != null) q.set("category_id", String(f.category_id));
  for (const v of f.lang ?? []) q.append("lang", v);
  for (const v of f.status ?? []) q.append("status", v);
  for (const v of f.review_status ?? []) q.append("review_status", v);
  for (const v of f.split ?? []) q.append("split", v);
  if (f.include_validated_sources) q.set("include_validated_sources", "true");
  return q;
}

export function CleanupPage() {
  const { isAdmin, loading } = useAuth();
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as Tab) || "audit";
  const filter = useMemo(() => parseFilter(params), [params]);
  const [replaceSeed, setReplaceSeed] = useState<{
    query: string;
    replacement: string;
  } | null>(null);

  if (loading) {
    return <p className="p-8 text-app-text-muted">Loading…</p>;
  }
  if (!isAdmin) {
    return <Navigate to="/" replace />;
  }

  function setTab(next: Tab) {
    const q = writeFilter(filter);
    q.set("tab", next);
    setParams(q);
  }

  function setFilter(next: SegmentFilterParams) {
    const q = writeFilter(next);
    q.set("tab", tab);
    setParams(q);
  }

  return (
    <div className="mx-auto min-h-screen max-w-4xl px-4 py-8 text-app-text">
      <AppHeader />
      <main className="space-y-4">
        <div>
          <h1 className="text-xl font-semibold">Data cleanup</h1>
          <p className="text-sm text-app-text-muted">
            Audit short segments, explore vocabulary, mass-replace text, and
            maintain the Lortograf lexicon.
          </p>
        </div>

        <div className="flex flex-wrap gap-1 border-b border-app-border pb-2">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`rounded-md px-3 py-1.5 text-sm ${
                tab === t.id
                  ? "bg-indigo-600 text-white"
                  : "text-app-text-muted hover:bg-app-hover"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {tab !== "lexicon" && (
          <CleanupFilters value={filter} onChange={setFilter} />
        )}

        {tab === "audit" && <AuditTab filter={filter} />}
        {tab === "vocabulary" && (
          <VocabularyTab
            filter={filter}
            onSeedReplace={(query, replacement) => {
              setReplaceSeed({ query, replacement });
              setTab("replace");
            }}
          />
        )}
        {tab === "replace" && (
          <SearchReplaceTab filter={filter} seed={replaceSeed} />
        )}
        {tab === "lexicon" && <LexiconTab />}
      </main>
    </div>
  );
}
