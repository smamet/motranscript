import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import type {
  LexiconEntry,
  LexiconKind,
  LexiconOrigin,
  LexiconSuggestion,
} from "../../types";
import { Button, Pill } from "../ui";

export function LexiconTab() {
  const [entries, setEntries] = useState<LexiconEntry[]>([]);
  const [suggestions, setSuggestions] = useState<LexiconSuggestion[]>([]);
  const [kind, setKind] = useState<LexiconKind | "">("");
  const [origin, setOrigin] = useState<LexiconOrigin | "">("");
  const [q, setQ] = useState("");
  const [word, setWord] = useState("");
  const [newKind, setNewKind] = useState<LexiconKind>("official");
  const [canonical, setCanonical] = useState("");
  const [importText, setImportText] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [showSuggestions, setShowSuggestions] = useState(false);

  const load = useCallback(async () => {
    setEntries(
      await api.lexiconList({
        kind: kind || undefined,
        origin: origin || undefined,
        q: q || undefined,
        limit: 1000,
      }),
    );
  }, [kind, origin, q]);

  useEffect(() => {
    void load().catch((e) => setMsg(String(e)));
  }, [load]);

  async function addEntry() {
    if (!word.trim()) return;
    try {
      await api.lexiconCreate({
        word: word.trim(),
        kind: newKind,
        canonical: newKind === "alias" ? canonical.trim() : null,
      });
      setWord("");
      setCanonical("");
      setMsg("Entry added");
      await load();
    } catch (e) {
      setMsg(String(e));
    }
  }

  async function remove(id: number) {
    try {
      await api.lexiconDelete(id);
      await load();
    } catch (e) {
      setMsg(String(e));
    }
  }

  async function doImport() {
    try {
      const r = await api.lexiconImport(importText);
      setMsg(`Imported: +${r.added}, ~${r.updated}`);
      setImportText("");
      await load();
    } catch (e) {
      setMsg(String(e));
    }
  }

  async function doExport() {
    try {
      const text = await api.lexiconExport();
      const blob = new Blob([text], { type: "text/plain" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "lexicon.txt";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setMsg(String(e));
    }
  }

  async function loadSuggestions() {
    setShowSuggestions(true);
    try {
      setSuggestions(await api.lexiconSuggestions(3));
    } catch (e) {
      setMsg(String(e));
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <input
          className="app-input w-40 text-sm"
          placeholder="Search…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <select
          className="app-input text-sm"
          value={kind}
          onChange={(e) => setKind(e.target.value as LexiconKind | "")}
        >
          <option value="">All kinds</option>
          <option value="official">official</option>
          <option value="alias">alias</option>
          <option value="skip">skip</option>
        </select>
        <select
          className="app-input text-sm"
          value={origin}
          onChange={(e) => setOrigin(e.target.value as LexiconOrigin | "")}
        >
          <option value="">All origins</option>
          <option value="pdf">pdf</option>
          <option value="manual">manual</option>
          <option value="corpus">corpus</option>
        </select>
        <Button size="sm" onClick={() => void doExport()}>
          Export
        </Button>
        <Button size="sm" variant="muted" onClick={() => void loadSuggestions()}>
          Suggestions from corpus
        </Button>
      </div>

      <div className="flex flex-wrap items-end gap-2 rounded-lg border border-app-border bg-app-surface p-3">
        <label className="text-sm">
          <span className="mb-1 block text-xs text-app-text-muted">Word</span>
          <input
            className="app-input"
            value={word}
            onChange={(e) => setWord(e.target.value)}
          />
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-xs text-app-text-muted">Kind</span>
          <select
            className="app-input"
            value={newKind}
            onChange={(e) => setNewKind(e.target.value as LexiconKind)}
          >
            <option value="official">official</option>
            <option value="alias">alias</option>
            <option value="skip">skip</option>
          </select>
        </label>
        {newKind === "alias" && (
          <label className="text-sm">
            <span className="mb-1 block text-xs text-app-text-muted">Canonical</span>
            <input
              className="app-input"
              value={canonical}
              onChange={(e) => setCanonical(e.target.value)}
            />
          </label>
        )}
        <Button size="sm" onClick={() => void addEntry()}>
          Add
        </Button>
      </div>

      {msg && <p className="text-sm text-app-text-muted">{msg}</p>}

      {showSuggestions && (
        <div className="rounded-lg border border-app-border bg-app-surface p-3">
          <h3 className="mb-2 text-sm font-medium">
            Unknown words in validated segments
          </h3>
          <ul className="flex flex-wrap gap-2">
            {suggestions.length === 0 ? (
              <li className="text-sm text-app-text-muted">No suggestions.</li>
            ) : (
              suggestions.map((s) => (
                <li key={s.word}>
                  <button
                    type="button"
                    className="rounded-full border border-app-border px-2 py-0.5 text-xs hover:bg-app-hover"
                    onClick={() =>
                      void api
                        .lexiconCreate({
                          word: s.word,
                          kind: "official",
                          origin: "corpus",
                        })
                        .then(load)
                        .then(() =>
                          setSuggestions((prev) =>
                            prev.filter((x) => x.word !== s.word),
                          ),
                        )
                    }
                  >
                    {s.word} ({s.count}) — Add
                  </button>
                </li>
              ))
            )}
          </ul>
        </div>
      )}

      <div className="max-h-[24rem] overflow-auto rounded-lg border border-app-border bg-app-surface">
        <table className="w-full text-left text-sm">
          <thead className="sticky top-0 bg-app-muted text-xs text-app-text-muted">
            <tr>
              <th className="px-3 py-2">Word</th>
              <th className="px-3 py-2">Kind</th>
              <th className="px-3 py-2">Canonical</th>
              <th className="px-3 py-2">Origin</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {entries.map((e) => (
              <tr key={e.id} className="border-t border-app-border">
                <td className="px-3 py-1.5 font-medium">{e.word}</td>
                <td className="px-3 py-1.5">
                  <Pill tone="slate">{e.kind}</Pill>
                </td>
                <td className="px-3 py-1.5">{e.canonical ?? "—"}</td>
                <td className="px-3 py-1.5 text-app-text-muted">{e.origin}</td>
                <td className="px-3 py-1.5 text-right">
                  <button
                    type="button"
                    className="text-xs text-red-600 hover:underline dark:text-red-400"
                    onClick={() => void remove(e.id)}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div>
        <h3 className="mb-2 text-sm font-medium">Import</h3>
        <textarea
          className="app-input min-h-28 w-full font-mono text-xs"
          placeholder={"official words one per line, or alias:canonical"}
          value={importText}
          onChange={(e) => setImportText(e.target.value)}
        />
        <Button
          size="sm"
          className="mt-2"
          disabled={!importText.trim()}
          onClick={() => void doImport()}
        >
          Import
        </Button>
      </div>
    </div>
  );
}
