import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ClockIcon, ShieldCheckIcon } from "@heroicons/react/20/solid";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import type { PaymentPeriod, User, UserRole, UserTimeEvent } from "../types";
import { formatHours } from "../types";
import { formatMur, PaymentHistory, PayrollSummary } from "./PayrollSummary";
import { AppHeader } from "./AppHeader";
import { Button, Pill, PillSelect } from "./ui";

type UsersTab = "active" | "deactivated";

function formatEventWhen(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function periodBadge(u: User): string | null {
  if (u.last_period_kind === "reset") {
    return `Reset ${formatEventWhen(u.last_period_at)}`;
  }
  if (u.last_period_kind === "rollback") {
    return `Rolled back ${formatEventWhen(u.last_period_at)}`;
  }
  return null;
}

function isActiveUser(u: User): boolean {
  return u.is_active && !u.deleted_at;
}

export function UsersPage() {
  const { user: me, isAdmin } = useAuth();
  const [users, setUsers] = useState<User[]>([]);
  const [tab, setTab] = useState<UsersTab>("active");
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<UserRole>("operator");
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [history, setHistory] = useState<Record<number, UserTimeEvent[]>>({});
  const [payments, setPayments] = useState<Record<number, PaymentPeriod[]>>({});
  const [historyBusy, setHistoryBusy] = useState<number | null>(null);
  const [emailDrafts, setEmailDrafts] = useState<Record<number, string>>({});
  const [rateDrafts, setRateDrafts] = useState<Record<number, string>>({});

  const refresh = useCallback(async () => {
    try {
      const list = await api.listUsers();
      setUsers(list);
      setEmailDrafts(Object.fromEntries(list.map((u) => [u.id, u.email])));
      setRateDrafts(
        Object.fromEntries(list.map((u) => [u.id, String(u.hourly_rate_mur ?? 0)])),
      );
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const visibleUsers = useMemo(
    () =>
      users.filter((u) => (tab === "active" ? isActiveUser(u) : !isActiveUser(u))),
    [users, tab],
  );

  const activeCount = users.filter(isActiveUser).length;
  const deactivatedCount = users.length - activeCount;

  if (!isAdmin) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-8">
        <p className="app-alert-error">Admin only.</p>
        <Link to="/" className="mt-4 inline-block text-sm text-indigo-600">
          ← Sources
        </Link>
      </div>
    );
  }

  const onCreate = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      await api.createUser({ email: email.trim(), password, role });
      setEmail("");
      setPassword("");
      setRole("operator");
      setMsg("User created");
      await refresh();
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  const onToggleActive = async (u: User) => {
    if (u.id === me?.id && u.is_active) {
      setError("Cannot deactivate yourself");
      return;
    }
    setBusy(true);
    try {
      if (!u.is_active || u.deleted_at) {
        await api.restoreUser(u.id);
        setMsg(`Restored ${u.email}`);
      } else {
        await api.updateUser(u.id, { is_active: false });
      }
      await refresh();
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  const onDelete = async (u: User) => {
    if (u.id === me?.id) {
      setError("Cannot delete yourself");
      return;
    }
    if (!window.confirm(`Delete ${u.email}? Soft-delete if they have history.`)) return;
    setBusy(true);
    setMsg(null);
    try {
      const result = await api.deleteUser(u.id);
      if (result.mode === "hard") {
        setMsg(`Permanently deleted ${u.email}`);
      } else {
        setMsg(`Deactivated ${u.email} (has linked history)`);
        setTab("deactivated");
      }
      await refresh();
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  const onChangeRole = async (u: User, next: UserRole) => {
    setBusy(true);
    try {
      await api.updateUser(u.id, { role: next });
      await refresh();
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  const onResetPassword = async (u: User) => {
    const next = window.prompt(`New password for ${u.email}`);
    if (!next || next.length < 4) return;
    setBusy(true);
    try {
      await api.updateUser(u.id, { password: next });
      setMsg(`Password updated for ${u.email}`);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  const saveEmail = async (u: User) => {
    const next = (emailDrafts[u.id] ?? u.email).trim().toLowerCase();
    if (!next || next === u.email) return;
    setBusy(true);
    try {
      await api.updateUser(u.id, { email: next });
      setMsg(`Email updated`);
      await refresh();
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  const saveRate = async (u: User) => {
    const raw = rateDrafts[u.id] ?? String(u.hourly_rate_mur ?? 0);
    const rate = Number(raw);
    if (!Number.isFinite(rate) || rate < 0) {
      setError("Hourly rate must be a non-negative number");
      return;
    }
    if (rate === (u.hourly_rate_mur ?? 0)) return;
    setBusy(true);
    try {
      await api.updateUser(u.id, { hourly_rate_mur: rate });
      setMsg(`Rate updated for ${u.email}`);
      await refresh();
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  const onResetTime = async (u: User) => {
    const hours = formatHours(u.validated_audio_sec ?? 0);
    const note =
      window.prompt(
        `Reset validated pay period for ${u.email}?\nCurrent payable: ${hours} (${formatMur(u.owed_mur ?? 0)})\n\nOptional note (admin only):`,
        "",
      ) ?? null;
    if (note === null) return;
    setBusy(true);
    try {
      await api.resetUserTime(u.id, note.trim() || undefined);
      setMsg(`Validated time reset for ${u.email}`);
      await refresh();
      if (expandedId === u.id) {
        const [events, periods] = await Promise.all([
          api.listUserTimeEvents(u.id),
          api.listPaymentPeriods(u.id),
        ]);
        setHistory((prev) => ({ ...prev, [u.id]: events }));
        setPayments((prev) => ({ ...prev, [u.id]: periods }));
      }
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  const onRollbackTime = async (u: User) => {
    if (!window.confirm(`Roll back the last validated reset for ${u.email}?`)) return;
    setBusy(true);
    try {
      await api.rollbackUserTime(u.id);
      setMsg(`Validated time rolled back for ${u.email}`);
      await refresh();
      if (expandedId === u.id) {
        const [events, periods] = await Promise.all([
          api.listUserTimeEvents(u.id),
          api.listPaymentPeriods(u.id),
        ]);
        setHistory((prev) => ({ ...prev, [u.id]: events }));
        setPayments((prev) => ({ ...prev, [u.id]: periods }));
      }
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  const toggleHistory = async (u: User) => {
    if (expandedId === u.id) {
      setExpandedId(null);
      return;
    }
    setExpandedId(u.id);
    if (history[u.id] && payments[u.id]) return;
    setHistoryBusy(u.id);
    try {
      const [events, periods] = await Promise.all([
        api.listUserTimeEvents(u.id),
        api.listPaymentPeriods(u.id),
      ]);
      setHistory((prev) => ({ ...prev, [u.id]: events }));
      setPayments((prev) => ({ ...prev, [u.id]: periods }));
    } catch (err) {
      setError(String(err));
    } finally {
      setHistoryBusy(null);
    }
  };

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <AppHeader />

      <div className="mb-6">
        <h2 className="text-xl font-semibold">Users</h2>
        <p className="text-sm text-app-text-muted">
          Accounts, net audio hours, and MUR payroll (Validated = payable)
        </p>
      </div>

      {error && <p className="app-alert-error mb-4">{error}</p>}
      {msg && <p className="app-alert-success mb-4">{msg}</p>}

      <section className="app-card mb-8 p-4">
        <h2 className="mb-3 font-medium">Add user</h2>
        <form onSubmit={(e) => void onCreate(e)} className="flex flex-wrap items-center gap-2">
          <input
            type="email"
            required
            placeholder="email@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="app-input min-w-[12rem] flex-1"
          />
          <input
            type="password"
            required
            minLength={4}
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="app-input min-w-[8rem] flex-1"
          />
          <PillSelect
            icon={ShieldCheckIcon}
            label="Role"
            value={role}
            placeholder="Role"
            options={[
              { value: "operator", label: "operator" },
              { value: "admin", label: "admin" },
            ]}
            onChange={(v) => {
              if (v) setRole(v as UserRole);
            }}
          />
          <Button type="submit" variant="primary" disabled={busy}>
            Create
          </Button>
        </form>
      </section>

      <div className="mb-4 flex gap-1 border-b border-app-border">
        <button
          type="button"
          onClick={() => setTab("active")}
          className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium transition ${
            tab === "active"
              ? "border-indigo-600 text-indigo-700 dark:text-indigo-300"
              : "border-transparent text-app-text-muted hover:text-app-text"
          }`}
        >
          Active ({activeCount})
        </button>
        <button
          type="button"
          onClick={() => setTab("deactivated")}
          className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium transition ${
            tab === "deactivated"
              ? "border-indigo-600 text-indigo-700 dark:text-indigo-300"
              : "border-transparent text-app-text-muted hover:text-app-text"
          }`}
        >
          Deactivated ({deactivatedCount})
        </button>
      </div>

      {visibleUsers.length === 0 && (
        <p className="text-sm text-app-text-muted">
          {tab === "active" ? "No active users." : "No deactivated users."}
        </p>
      )}

      <ul className="space-y-4">
        {visibleUsers.map((u) => {
          const badge = periodBadge(u);
          const softDeleted = Boolean(u.deleted_at);
          return (
            <li key={u.id} className="app-card space-y-3 p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1 space-y-2">
                  <input
                    type="email"
                    value={emailDrafts[u.id] ?? u.email}
                    disabled={busy}
                    onChange={(e) =>
                      setEmailDrafts((prev) => ({ ...prev, [u.id]: e.target.value }))
                    }
                    onBlur={() => void saveEmail(u)}
                    className="app-input w-full max-w-md text-[15px] font-semibold"
                  />
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    <Pill tone={u.role === "admin" ? "indigo" : "muted"}>{u.role}</Pill>
                    {u.id === me?.id && <Pill tone="sky">you</Pill>}
                    {softDeleted && <Pill tone="red">deleted</Pill>}
                    {!softDeleted && !u.is_active && <Pill tone="amber">inactive</Pill>}
                    {badge && (
                      <span className="inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-800 dark:bg-amber-950/50 dark:text-amber-300">
                        {badge}
                      </span>
                    )}
                  </div>
                  <div className="flex flex-wrap items-center gap-3 text-sm">
                    <label className="flex items-center gap-1.5 text-app-text-muted">
                      Rate MUR/h
                      <input
                        type="number"
                        min={0}
                        step="0.01"
                        value={rateDrafts[u.id] ?? "0"}
                        disabled={busy}
                        onChange={(e) =>
                          setRateDrafts((prev) => ({ ...prev, [u.id]: e.target.value }))
                        }
                        onBlur={() => void saveRate(u)}
                        className="app-input w-24 py-1 text-sm"
                      />
                    </label>
                  </div>
                  <PayrollSummary user={u} />
                </div>
                <div className="flex shrink-0 flex-wrap justify-end gap-1.5">
                  <PillSelect
                    icon={ShieldCheckIcon}
                    label="Role"
                    value={u.role}
                    placeholder="Role"
                    options={[
                      { value: "operator", label: "operator" },
                      { value: "admin", label: "admin" },
                    ]}
                    disabled={busy}
                    onChange={(v) => {
                      if (v) void onChangeRole(u, v as UserRole);
                    }}
                  />
                  <Button size="sm" disabled={busy} onClick={() => void onResetPassword(u)}>
                    Reset password
                  </Button>
                  {tab === "active" ? (
                    <>
                      <Button
                        size="sm"
                        disabled={busy || u.id === me?.id}
                        onClick={() => void onToggleActive(u)}
                      >
                        Deactivate
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        tone="red"
                        disabled={busy || u.id === me?.id}
                        onClick={() => void onDelete(u)}
                      >
                        Delete
                      </Button>
                    </>
                  ) : (
                    <Button
                      size="sm"
                      variant="outline"
                      tone="sky"
                      disabled={busy}
                      onClick={() => void onToggleActive(u)}
                    >
                      Restore
                    </Button>
                  )}
                </div>
              </div>

              <div className="flex flex-wrap gap-1.5 border-t border-app-border pt-3">
                <Button
                  size="sm"
                  variant="outline"
                  tone="amber"
                  disabled={busy}
                  onClick={() => void onResetTime(u)}
                >
                  Reset validated
                </Button>
                <Button
                  size="sm"
                  disabled={busy || !u.can_rollback}
                  onClick={() => void onRollbackTime(u)}
                  title={u.can_rollback ? "Undo last reset" : "No reset to roll back"}
                >
                  Rollback reset
                </Button>
                <Button
                  size="sm"
                  icon={ClockIcon}
                  disabled={historyBusy === u.id}
                  onClick={() => void toggleHistory(u)}
                >
                  {expandedId === u.id ? "Hide history" : "History"}
                </Button>
              </div>

              {expandedId === u.id && (
                <div className="space-y-3 rounded-md border border-app-border bg-app-muted/40 p-3">
                  {historyBusy === u.id && (
                    <p className="text-xs text-app-text-muted">Loading…</p>
                  )}
                  {!historyBusy && (
                    <>
                      <div>
                        <p className="mb-1 text-xs font-medium text-app-text">Payment history</p>
                        <PaymentHistory periods={payments[u.id] ?? []} showNotes />
                      </div>
                      <div>
                        <p className="mb-1 text-xs font-medium text-app-text">Time events</p>
                        {(history[u.id]?.length ?? 0) === 0 && (
                          <p className="text-xs text-app-text-muted">No time events yet.</p>
                        )}
                        <ul className="max-h-64 space-y-1.5 overflow-y-auto text-xs">
                          {(history[u.id] ?? []).map((ev) => (
                            <li
                              key={ev.id}
                              className={`flex flex-wrap gap-x-2 gap-y-0.5 ${
                                ev.kind === "reset" || ev.kind === "rollback"
                                  ? "font-medium text-amber-900 dark:text-amber-200"
                                  : "text-app-text-muted"
                              }`}
                            >
                              <span className="text-app-text-subtle">
                                {formatEventWhen(ev.created_at)}
                              </span>
                              <span className="uppercase tracking-wide">{ev.kind}</span>
                              {ev.bucket && <span>{ev.bucket}</span>}
                              <span>{formatHours(ev.audio_sec)}</span>
                              {ev.source_id != null && <span>source #{ev.source_id}</span>}
                            </li>
                          ))}
                        </ul>
                      </div>
                    </>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
