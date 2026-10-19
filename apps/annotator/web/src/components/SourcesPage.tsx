import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChevronDownIcon, ChevronUpIcon, UserIcon } from "@heroicons/react/20/solid";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import { AppHeader } from "./AppHeader";
import { SourceCard } from "./SourceCard";
import { SystemAlerts } from "./SystemAlerts";
import { PaymentHistory, PayrollSummary } from "./PayrollSummary";
import { Button, PillSelect } from "./ui";
import type {
  Category,
  PaymentPeriod,
  ReviewHours,
  SourceListItem,
  SourcesTab,
  SystemAlert,
  User,
} from "../types";
import {
  ADMIN_TABS,
  REVIEW_TABS,
  formatHours,
  hasActiveTranscribe,
} from "../types";

const TAB_STORAGE_KEY = "motranscript-review-tab";

const TAB_DOT: Record<SourcesTab, string> = {
  downloaded: "bg-violet-500",
  todo: "bg-amber-500",
  done: "bg-indigo-500",
  validated: "bg-emerald-500",
};

function readStoredTab(): SourcesTab | null {
  try {
    const stored = localStorage.getItem(TAB_STORAGE_KEY);
    const all = ["downloaded", "todo", "done", "validated"];
    return all.includes(stored ?? "") ? (stored as SourcesTab) : null;
  } catch {
    return null;
  }
}

const emptyHours = (): ReviewHours => ({
  todo: 0,
  done: 0,
  validated: 0,
  downloaded: 0,
  downloaded_by_category: {},
});

export function SourcesPage() {
  const { user, isAdmin } = useAuth();
  const [sources, setSources] = useState<SourceListItem[]>([]);
  const [hours, setHours] = useState<ReviewHours>(emptyHours);
  const [tab, setTab] = useState<SourcesTab>(() => readStoredTab() ?? "todo");
  const hadStoredTab = useRef(readStoredTab() !== null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [operators, setOperators] = useState<User[]>([]);
  const [mePayroll, setMePayroll] = useState<User | null>(null);
  const [myPayments, setMyPayments] = useState<PaymentPeriod[]>([]);
  const [showPayments, setShowPayments] = useState(false);
  const [assignFilter, setAssignFilter] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [workerAlive, setWorkerAlive] = useState<boolean | null>(null);
  const [systemAlerts, setSystemAlerts] = useState<SystemAlert[]>([]);

  // Downloaded catalog selection / filters
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [filterCats, setFilterCats] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState("");
  const [minMin, setMinMin] = useState("");
  const [maxMin, setMaxMin] = useState("");
  const [targetHours, setTargetHours] = useState("10");
  const [weights, setWeights] = useState<Record<string, string>>({});

  useEffect(() => {
    if (hadStoredTab.current) return;
    setTab(isAdmin ? "downloaded" : "todo");
  }, [isAdmin]);

  useEffect(() => {
    if (!isAdmin && tab === "downloaded") setTab("todo");
  }, [isAdmin, tab]);

  useEffect(() => {
    try {
      localStorage.setItem(TAB_STORAGE_KEY, tab);
    } catch {
      /* ignore */
    }
  }, [tab]);

  const refresh = useCallback(async () => {
    try {
      const list = await api.listSources(
        isAdmin && assignFilter ? assignFilter : undefined,
      );
      setSources(list.sources);
      setHours({
        ...emptyHours(),
        ...list.hours,
        downloaded_by_category: list.hours.downloaded_by_category ?? {},
      });
      setError(null);
      const me = await api.me();
      setMePayroll(me);
      if (isAdmin) {
        const [cfg, cats, users] = await Promise.all([
          api.getConfig(),
          api.listCategories(),
          api.listUsers(),
        ]);
        setWorkerAlive(cfg.worker_alive);
        setSystemAlerts(cfg.alerts ?? []);
        setCategories(cats);
        setOperators(users.filter((u) => u.is_active && !u.deleted_at));
        setWeights((prev) => {
          const next = { ...prev };
          for (const c of cats) {
            if (next[c.slug] == null) next[c.slug] = "1";
          }
          return next;
        });
      } else {
        setWorkerAlive(null);
        setSystemAlerts([]);
        setCategories([]);
        setOperators([]);
      }
    } catch (e) {
      setError(String(e));
    }
  }, [isAdmin, assignFilter]);

  useEffect(() => {
    void refresh();
    const interval = setInterval(refresh, 3000);
    return () => clearInterval(interval);
  }, [refresh]);

  useEffect(() => {
    if (!showPayments || !user?.id || isAdmin) return;
    void api.listPaymentPeriods(user.id).then(setMyPayments).catch(() => undefined);
  }, [showPayments, user?.id, isAdmin, mePayroll?.owed_mur, mePayroll?.validated_audio_sec]);

  const tabs = isAdmin ? ADMIN_TABS : REVIEW_TABS;

  const catalogPool = useMemo(() => {
    return sources.filter((s) => {
      if (s.status === "downloaded") return true;
      // Ingest in progress / failed downloads live only in Downloaded (admin)
      if (["pending", "processing", "failed", "cancelled"].includes(s.status)) {
        return !hasActiveTranscribe(s);
      }
      return false;
    });
  }, [sources]);

  const filteredCatalog = useMemo(() => {
    const q = search.trim().toLowerCase();
    const minSec = minMin ? Number(minMin) * 60 : null;
    const maxSec = maxMin ? Number(maxMin) * 60 : null;
    return catalogPool.filter((s) => {
      if (filterCats.size > 0) {
        const slug = s.category?.slug;
        if (!slug || !filterCats.has(slug)) return false;
      }
      if (q) {
        const title = (s.title ?? "").toLowerCase();
        const url = (s.source_url ?? "").toLowerCase();
        const id = String(s.id);
        if (!title.includes(q) && !url.includes(q) && !id.includes(q)) return false;
      }
      const dur = s.duration_sec ?? 0;
      if (minSec != null && !Number.isNaN(minSec) && dur < minSec) return false;
      if (maxSec != null && !Number.isNaN(maxSec) && dur > maxSec) return false;
      return true;
    });
  }, [catalogPool, filterCats, search, minMin, maxMin]);

  const filtered = useMemo(() => {
    if (tab === "downloaded") {
      return { ready: filteredCatalog.filter((s) => s.status === "downloaded"), importing: filteredCatalog.filter((s) => s.status !== "downloaded") };
    }
    const ready = sources.filter(
      (s) => s.status === "ready" && s.review_status === tab,
    );
    const importing =
      tab === "todo"
        ? sources.filter(
            (s) =>
              ["pending", "processing", "failed", "cancelled"].includes(s.status) &&
              hasActiveTranscribe(s),
          )
        : [];
    const sortedReady = [...ready].sort((a, b) => {
      if (a.partial !== b.partial) return a.partial ? -1 : 1;
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    });
    return { ready: sortedReady, importing };
  }, [sources, tab, filteredCatalog]);

  const tabCounts = useMemo(() => {
    const counts: Record<SourcesTab, number> = {
      downloaded: 0,
      todo: 0,
      done: 0,
      validated: 0,
    };
    for (const s of sources) {
      if (s.status === "ready") counts[s.review_status] += 1;
    }
    counts.downloaded = catalogPool.length;
    return counts;
  }, [sources, catalogPool]);

  const selectionSeconds = useMemo(() => {
    let total = 0;
    const byCat: Record<string, number> = {};
    for (const s of sources) {
      if (!selectedIds.has(s.id)) continue;
      const sec = s.duration_sec ?? 0;
      total += sec;
      const slug = s.category?.slug ?? "uncategorized";
      byCat[slug] = (byCat[slug] ?? 0) + sec;
    }
    return { total, byCat };
  }, [sources, selectedIds]);

  const hourForTab = (t: SourcesTab): number => {
    if (t === "downloaded") return hours.downloaded;
    return hours[t];
  };

  const runAction = async (fn: () => Promise<unknown>) => {
    setActionBusy(true);
    try {
      await fn();
      await refresh();
    } catch (err) {
      setError(String(err));
    } finally {
      setActionBusy(false);
    }
  };

  const onCancel = async (id: number) => {
    if (!window.confirm("Cancel this source? The worker will stop processing it.")) return;
    await runAction(() => api.cancelSource(id));
  };

  const onRetranscribe = async (id: number) => {
    if (
      !window.confirm(
        "Re-transcribe this source? Existing segments will be replaced (audio is kept).",
      )
    ) {
      return;
    }
    await runAction(() => api.retranscribeSource(id));
  };

  const onResume = async (id: number) => {
    await runAction(() => api.resumeSource(id));
  };

  const onDelete = async (id: number) => {
    if (!window.confirm("Delete this source and all its audio/segments? This cannot be undone.")) {
      return;
    }
    await runAction(() => api.deleteSource(id));
    setSelectedIds((prev) => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
  };

  const onMarkDone = async (id: number) => {
    await runAction(() => api.setReviewStatus(id, "done"));
  };

  const onReopen = async (id: number) => {
    await runAction(() => api.setReviewStatus(id, "todo"));
  };

  const onValidate = async (id: number) => {
    if (!window.confirm("Validate this source? Operator work is accepted.")) return;
    await runAction(() => api.setReviewStatus(id, "validated"));
  };

  const onReject = async (id: number) => {
    const note = window.prompt("Reason for sending back (optional):") ?? undefined;
    await runAction(() => api.setReviewStatus(id, "todo", note || undefined));
  };

  const onCategoryChange = async (id: number, categoryId: number | null) => {
    await runAction(() => api.setSourceCategory(id, categoryId));
  };

  const onClaim = async (id: number) => {
    if (!user) return;
    await runAction(() => api.claimSource(id, user.id));
  };

  const onAssign = async (id: number, userId: number | null) => {
    await runAction(() => api.setSourceAssignment(id, userId));
  };

  const toggleSelect = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const onRandomSelect = async () => {
    const hoursTarget = Number(targetHours);
    if (!hoursTarget || hoursTarget <= 0) {
      setError("Target hours must be > 0");
      return;
    }
    const weightNums: Record<string, number> = {};
    for (const [slug, raw] of Object.entries(weights)) {
      const n = Number(raw);
      if (!Number.isNaN(n) && n > 0) weightNums[slug] = n;
    }
    setActionBusy(true);
    try {
      const result = await api.catalogSample({
        target_hours: hoursTarget,
        weights: weightNums,
        source_ids: filteredCatalog.filter((s) => s.status === "downloaded").map((s) => s.id),
      });
      setSelectedIds(new Set(result.source_ids));
      setError(null);
    } catch (err) {
      setError(String(err));
    } finally {
      setActionBusy(false);
    }
  };

  const onPromote = async () => {
    const ids = [...selectedIds];
    if (ids.length === 0) return;
    if (
      !window.confirm(
        `Send ${ids.length} source(s) (${formatHours(selectionSeconds.total)}) to To do for ASR?`,
      )
    ) {
      return;
    }
    await runAction(async () => {
      await api.promoteSources(ids);
      setSelectedIds(new Set());
      setTab("todo");
    });
  };

  const toggleFilterCat = (slug: string) => {
    setFilterCats((prev) => {
      const next = new Set(prev);
      if (next.has(slug)) next.delete(slug);
      else next.add(slug);
      return next;
    });
  };

  const hasPendingSources = sources.some((s) => s.status === "pending");
  const hasProcessingSources = sources.some((s) => s.status === "processing");
  const showWorkerWarning =
    isAdmin && (hasPendingSources || hasProcessingSources) && workerAlive === false;

  const cardProps = {
    busy: actionBusy,
    isAdmin,
    onCancel,
    onDelete,
    onRetranscribe,
    onResume,
    onMarkDone,
    onReopen,
    onValidate,
    onReject,
    onCategoryChange: isAdmin ? onCategoryChange : undefined,
    categories: isAdmin ? categories : undefined,
    onClaim,
    onAssign: isAdmin ? onAssign : undefined,
    operators: isAdmin ? operators : undefined,
    currentUserId: user?.id,
  };

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <AppHeader />

      {mePayroll && (
        <div className="mb-4 space-y-2">
          <PayrollSummary user={mePayroll} />
          {!isAdmin && (
            <div>
              <button
                type="button"
                className="inline-flex items-center gap-1 text-xs font-medium text-indigo-600 hover:text-indigo-500 dark:text-indigo-400"
                onClick={() => setShowPayments((v) => !v)}
              >
                {showPayments ? "Hide my payments" : "My payments"}
                {showPayments ? (
                  <ChevronUpIcon className="h-3.5 w-3.5" aria-hidden />
                ) : (
                  <ChevronDownIcon className="h-3.5 w-3.5" aria-hidden />
                )}
              </button>
              {showPayments && (
                <div className="mt-2 rounded-md border border-app-border bg-app-muted/40 p-3">
                  <PaymentHistory periods={myPayments} />
                </div>
              )}
            </div>
          )}
        </div>
      )}

      <div
        className={`mb-6 grid gap-1 rounded-xl bg-app-muted p-1 ${
          isAdmin ? "grid-cols-4" : "grid-cols-3"
        }`}
        role="tablist"
        aria-label="Queues"
      >
        {tabs.map((t) => {
          const active = tab === t.id;
          return (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setTab(t.id)}
              className={`flex flex-col items-center gap-0.5 rounded-lg px-1 py-2.5 transition sm:px-2 ${
                active
                  ? "bg-app-surface text-app-text shadow-sm ring-1 ring-app-border"
                  : "text-app-text-muted hover:text-app-text"
              }`}
            >
              <span className="flex items-center gap-1.5 text-sm font-medium">
                <span className={`h-1.5 w-1.5 rounded-full ${TAB_DOT[t.id]}`} />
                {t.label}
              </span>
              <span className="flex items-center gap-1.5 text-xs tabular-nums">
                <span className={active ? "text-app-text" : "text-app-text-subtle"}>
                  {formatHours(hourForTab(t.id))}
                </span>
                <span className="text-app-text-subtle">· {tabCounts[t.id]}</span>
              </span>
            </button>
          );
        })}
      </div>

      {isAdmin && (
        <div className="mb-4 flex flex-wrap items-center gap-2 text-sm">
          <PillSelect
            icon={UserIcon}
            label="Assigned to"
            value={assignFilter || ""}
            placeholder="All"
            options={[
              { value: "unassigned", label: "Unassigned" },
              ...operators.map((op) => ({ value: String(op.id), label: op.email })),
            ]}
            onChange={(v) => setAssignFilter(v ?? "")}
          />
        </div>
      )}

      {isAdmin && systemAlerts.length > 0 && (
        <SystemAlerts alerts={systemAlerts} className="mb-4" />
      )}

      {showWorkerWarning && !systemAlerts.some((a) => a.id === "worker_down") && (
        <p className="app-alert-warning mb-4">
          <strong>Worker not running.</strong> Run{" "}
          <code className="font-mono">uv run python -m apps.annotator.worker</code> in a separate
          terminal. Pending jobs resume automatically after restart.
        </p>
      )}

      {error && <p className="app-alert-error mb-4">{error}</p>}

      {isAdmin && tab === "downloaded" && (
        <section className="app-card mb-6 space-y-3 p-4">
          <h2 className="font-medium">Catalog filters & mix</h2>
          <div className="flex flex-wrap gap-2">
            {categories.map((c) => {
              const active = filterCats.has(c.slug);
              const sec = hours.downloaded_by_category[c.slug] ?? 0;
              return (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => toggleFilterCat(c.slug)}
                  className={`rounded-full px-3 py-1 text-xs font-medium transition ${
                    active
                      ? "bg-violet-600 text-white"
                      : "bg-app-muted text-app-text-muted hover:bg-app-hover hover:text-app-text"
                  }`}
                >
                  {c.label} · {formatHours(sec)}
                </button>
              );
            })}
          </div>
          <div className="flex flex-wrap gap-2">
            <input
              type="search"
              placeholder="Search title / URL / id"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="app-input min-w-[12rem] flex-1 text-sm"
            />
            <input
              type="number"
              min={0}
              placeholder="Min min"
              value={minMin}
              onChange={(e) => setMinMin(e.target.value)}
              className="app-input w-24 text-sm"
            />
            <input
              type="number"
              min={0}
              placeholder="Max min"
              value={maxMin}
              onChange={(e) => setMaxMin(e.target.value)}
              className="app-input w-24 text-sm"
            />
          </div>
          <div className="space-y-3 border-t border-app-border pt-3">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <label className="flex flex-col gap-1 text-xs text-app-text-muted">
                Target hours
                <input
                  type="number"
                  min={0.1}
                  step={0.5}
                  value={targetHours}
                  onChange={(e) => setTargetHours(e.target.value)}
                  className="app-input w-full text-sm"
                />
              </label>
              {categories.map((c) => (
                <label
                  key={c.id}
                  className="flex flex-col gap-1 text-xs text-app-text-muted"
                >
                  {c.label} weight
                  <input
                    type="number"
                    min={0}
                    step={0.1}
                    value={weights[c.slug] ?? "1"}
                    onChange={(e) =>
                      setWeights((prev) => ({ ...prev, [c.slug]: e.target.value }))
                    }
                    className="app-input w-full text-sm"
                  />
                </label>
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="secondary"
                disabled={actionBusy}
                onClick={() => void onRandomSelect()}
              >
                Random select
              </Button>
              <Button
                variant="secondary"
                disabled={actionBusy || selectedIds.size === 0}
                onClick={() => setSelectedIds(new Set())}
              >
                Clear
              </Button>
              <Button
                variant="primary"
                disabled={actionBusy || selectedIds.size === 0}
                onClick={() => void onPromote()}
              >
                Send to To do ({selectedIds.size})
              </Button>
            </div>
          </div>
          <p className="text-xs text-app-text-subtle">
            Selected {formatHours(selectionSeconds.total)}
            {Object.keys(selectionSeconds.byCat).length > 0 &&
              ` · ${Object.entries(selectionSeconds.byCat)
                .map(([slug, sec]) => `${slug}: ${formatHours(sec)}`)
                .join(", ")}`}
          </p>
        </section>
      )}

      <section>
        <h2 className="mb-3 font-medium">
          {tabs.find((t) => t.id === tab)?.label}
        </h2>
        {filtered.ready.length === 0 && filtered.importing.length === 0 ? (
          <p className="text-sm text-app-text-subtle">Nothing here yet.</p>
        ) : (
          <ul className="space-y-3">
            {filtered.ready.map((s) => (
              <SourceCard
                key={s.id}
                source={s}
                {...cardProps}
                selectable={tab === "downloaded"}
                selected={selectedIds.has(s.id)}
                onToggleSelect={toggleSelect}
              />
            ))}
            {filtered.importing.length > 0 && (
              <>
                <li className="pt-2 text-xs font-medium uppercase tracking-wide text-app-text-subtle">
                  {tab === "downloaded" ? "Downloading" : "Transcribing"}
                </li>
                {filtered.importing.map((s) => (
                  <SourceCard
                    key={s.id}
                    source={s}
                    {...cardProps}
                    selectable={false}
                  />
                ))}
              </>
            )}
          </ul>
        )}
      </section>
    </div>
  );
}
