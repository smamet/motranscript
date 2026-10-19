import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../../api/client";
import type { AuditRow, AuditRule, SegmentFilterParams } from "../../types";
import { Button } from "../ui";
import { SegmentHitRow } from "./SegmentHitRow";

export function AuditTab({ filter }: { filter: SegmentFilterParams }) {
  const [rules, setRules] = useState<AuditRule[]>([]);
  const [ruleId, setRuleId] = useState("short_segment");
  const [maxSec, setMaxSec] = useState(1);
  const [minCharsPerSec, setMinCharsPerSec] = useState(40);
  const [includeKept, setIncludeKept] = useState(false);
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void api
      .cleanupAuditRules()
      .then((list) => {
        setRules(list);
        if (list.length && !list.some((r) => r.id === ruleId)) {
          setRuleId(list[0].id);
        }
      })
      .catch(() => setRules([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only on mount
  }, []);

  useEffect(() => {
    // Sensible defaults when switching rules
    if (ruleId === "short_segment") setMaxSec(1);
    if (ruleId === "dense_text") {
      setMaxSec(2);
      setMinCharsPerSec(40);
    }
  }, [ruleId]);

  const load = useCallback(async () => {
    setLoading(true);
    setMsg(null);
    try {
      const data = await api.cleanupAudit({
        ...filter,
        rule: ruleId,
        max_sec: maxSec,
        min_chars_per_sec: ruleId === "dense_text" ? minCharsPerSec : undefined,
        include_kept: includeKept,
      });
      setRows(data);
      setSelected(new Set());
    } catch (e) {
      setMsg(String(e));
    } finally {
      setLoading(false);
    }
  }, [filter, ruleId, maxSec, minCharsPerSec, includeKept]);

  useEffect(() => {
    void load();
  }, [load]);

  const selectedRows = useMemo(
    () => rows.filter((r) => selected.has(r.segment_id)),
    [rows, selected],
  );
  const hasValidated = selectedRows.some((r) => r.status === "validated");

  function toggleAll(checked: boolean) {
    setSelected(checked ? new Set(rows.map((r) => r.segment_id)) : new Set());
  }

  async function runAction(action: "ignore" | "keep" | "unkeep") {
    const ids = [...selected];
    if (!ids.length) return;
    setBusy(true);
    setMsg(null);
    try {
      if (action === "ignore") {
        const r = await api.cleanupIgnore(ids);
        setMsg(`Ignored ${r.count} segment(s)`);
      } else if (action === "keep") {
        const r = await api.cleanupKeep(ruleId, ids);
        setMsg(`Kept ${r.count} segment(s)`);
      } else {
        const r = await api.cleanupUnkeep(ruleId, ids);
        setMsg(`Unkept ${r.count} segment(s)`);
      }
      await load();
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  }

  const emptyLabel =
    ruleId === "dense_text"
      ? "No dense-text segments match the filters."
      : "No short segments match the filters.";

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-sm">
          <span className="mb-1 block text-xs text-app-text-muted">Rule</span>
          <select
            className="app-input"
            value={ruleId}
            onChange={(e) => setRuleId(e.target.value)}
          >
            {(rules.length
              ? rules
              : [
                  { id: "short_segment", label: "Short segments" },
                  { id: "dense_text", label: "Dense text (likely noise)" },
                ]
            ).map((r) => (
              <option key={r.id} value={r.id}>
                {r.label}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-xs text-app-text-muted">
            Duration &lt; (seconds)
          </span>
          <input
            type="number"
            min={0.1}
            step={0.1}
            className="app-input w-28"
            value={maxSec}
            onChange={(e) => setMaxSec(Number(e.target.value) || 1)}
          />
        </label>
        {ruleId === "dense_text" && (
          <label className="text-sm">
            <span className="mb-1 block text-xs text-app-text-muted">
              Min chars / sec
            </span>
            <input
              type="number"
              min={1}
              step={1}
              className="app-input w-28"
              value={minCharsPerSec}
              onChange={(e) => setMinCharsPerSec(Number(e.target.value) || 40)}
            />
          </label>
        )}
        <label className="flex items-center gap-1.5 text-sm">
          <input
            type="checkbox"
            checked={includeKept}
            onChange={(e) => setIncludeKept(e.target.checked)}
          />
          Show kept
        </label>
        <Button size="sm" onClick={() => void load()} disabled={loading}>
          Refresh
        </Button>
      </div>

      {ruleId === "dense_text" && (
        <p className="text-xs text-app-text-muted">
          Flags short clips with unusually high text density (Whisper
          hallucination / noise). Typical speech is ~10–20 chars/s.
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-1.5 text-sm">
          <input
            type="checkbox"
            checked={rows.length > 0 && selected.size === rows.length}
            onChange={(e) => toggleAll(e.target.checked)}
          />
          Select all ({selected.size}/{rows.length})
        </label>
        <Button
          size="sm"
          tone="amber"
          disabled={busy || !selected.size}
          onClick={() => void runAction("ignore")}
        >
          Ignore selected
        </Button>
        <Button
          size="sm"
          disabled={busy || !selected.size}
          onClick={() => void runAction("keep")}
        >
          Keep selected
        </Button>
        <Button
          size="sm"
          variant="muted"
          disabled={busy || !selected.size}
          onClick={() => void runAction("unkeep")}
        >
          Unkeep
        </Button>
      </div>

      {hasValidated && (
        <p className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100">
          Selection includes validated segments. Ignoring them removes them from
          training export.
        </p>
      )}
      {msg && <p className="text-sm text-app-text-muted">{msg}</p>}
      {loading ? (
        <p className="text-sm text-app-text-muted">Loading…</p>
      ) : (
        <ul className="overflow-hidden rounded-lg border border-app-border bg-app-surface">
          {rows.length === 0 ? (
            <li className="px-3 py-6 text-center text-sm text-app-text-muted">
              {emptyLabel}
            </li>
          ) : (
            rows.map((row) => (
              <SegmentHitRow
                key={row.segment_id}
                segmentId={row.segment_id}
                sourceId={row.source_id}
                sourceTitle={row.source_title}
                reviewStatus={row.review_status}
                status={row.status}
                text={row.text || "(empty)"}
                checked={selected.has(row.segment_id)}
                onCheck={(c) => {
                  setSelected((prev) => {
                    const next = new Set(prev);
                    if (c) next.add(row.segment_id);
                    else next.delete(row.segment_id);
                    return next;
                  });
                }}
                meta={
                  <span>
                    {row.duration_sec.toFixed(2)}s
                    {row.chars_per_sec != null
                      ? ` · ${row.chars_per_sec} chars/s`
                      : ""}
                    {row.kept ? " · kept" : ""}
                  </span>
                }
              />
            ))
          )}
        </ul>
      )}
    </div>
  );
}
