import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import type {
  SearchHit,
  SegmentFilterParams,
  WordCluster,
  WordStat,
} from "../../types";
import { Button, Pill } from "../ui";
import { SegmentHitRow } from "./SegmentHitRow";

type SubView = "words" | "variants";

export function VocabularyTab({
  filter,
  onSeedReplace,
}: {
  filter: SegmentFilterParams;
  onSeedReplace: (query: string, replacement: string) => void;
}) {
  const [sub, setSub] = useState<SubView>("words");
  const [words, setWords] = useState<WordStat[]>([]);
  const [clusters, setClusters] = useState<WordCluster[]>([]);
  const [q, setQ] = useState("");
  const [lexStatus, setLexStatus] = useState("all");
  const [minCount, setMinCount] = useState(2);
  const [selectedWord, setSelectedWord] = useState<string | null>(null);
  const [occurrences, setOccurrences] = useState<SearchHit[]>([]);
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setMsg(null);
    try {
      if (sub === "words") {
        setWords(
          await api.cleanupVocabulary({
            ...filter,
            min_count: minCount,
            lexicon_status: lexStatus,
            q: q || undefined,
          }),
        );
      } else {
        setClusters(
          await api.cleanupVocabularyClusters({ ...filter, min_size: 2 }),
        );
      }
    } catch (e) {
      setMsg(String(e));
    } finally {
      setLoading(false);
    }
  }, [filter, sub, minCount, lexStatus, q]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!selectedWord) {
      setOccurrences([]);
      return;
    }
    void api
      .cleanupWordOccurrences(selectedWord, filter)
      .then(setOccurrences)
      .catch((e) => setMsg(String(e)));
  }, [selectedWord, filter]);

  async function addLexicon(
    word: string,
    kind: "official" | "alias" | "skip",
    canonical?: string,
  ) {
    setMsg(null);
    try {
      await api.lexiconCreate({
        word,
        kind,
        canonical: kind === "alias" ? canonical : null,
        origin: "corpus",
      });
      setMsg(`Added ${word} as ${kind}`);
      await load();
    } catch (e) {
      setMsg(String(e));
    }
  }

  async function setCanonical(cluster: WordCluster, canonical: string) {
    setMsg(null);
    try {
      for (const w of cluster.words) {
        if (w.word === canonical) {
          if (w.lexicon_status !== "official") {
            await api.lexiconCreate({
              word: canonical,
              kind: "official",
              origin: "corpus",
            });
          }
          continue;
        }
        await api.lexiconCreate({
          word: w.word,
          kind: "alias",
          canonical,
          origin: "corpus",
        });
      }
      const variants = cluster.words
        .map((w) => w.word)
        .filter((w) => w !== canonical);
      if (variants[0]) onSeedReplace(variants[0], canonical);
      setMsg(`Canonical set to ${canonical}. Review replace tab for mass replace.`);
      await load();
    } catch (e) {
      setMsg(String(e));
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          variant={sub === "words" ? "solid" : "muted"}
          onClick={() => setSub("words")}
        >
          Words
        </Button>
        <Button
          size="sm"
          variant={sub === "variants" ? "solid" : "muted"}
          onClick={() => setSub("variants")}
        >
          Variants
        </Button>
      </div>

      {sub === "words" && (
        <div className="flex flex-wrap gap-2">
          <input
            className="app-input w-40 text-sm"
            placeholder="Filter words…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <select
            className="app-input text-sm"
            value={lexStatus}
            onChange={(e) => setLexStatus(e.target.value)}
          >
            <option value="all">All lexicon statuses</option>
            <option value="unknown">Unknown</option>
            <option value="alias">Alias</option>
            <option value="official">Official</option>
            <option value="skip">Skip</option>
          </select>
          <label className="flex items-center gap-1 text-sm">
            Min
            <input
              type="number"
              min={1}
              className="app-input w-16 text-sm"
              value={minCount}
              onChange={(e) => setMinCount(Number(e.target.value) || 1)}
            />
          </label>
        </div>
      )}

      {msg && <p className="text-sm text-app-text-muted">{msg}</p>}

      <div className="grid gap-3 lg:grid-cols-2">
        <div className="max-h-[32rem] overflow-auto rounded-lg border border-app-border bg-app-surface">
          {loading ? (
            <p className="p-4 text-sm text-app-text-muted">Loading…</p>
          ) : sub === "words" ? (
            <table className="w-full text-left text-sm">
              <thead className="sticky top-0 bg-app-muted text-xs text-app-text-muted">
                <tr>
                  <th className="px-3 py-2">Word</th>
                  <th className="px-3 py-2">Count</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {words.map((w) => (
                  <tr
                    key={w.word}
                    className={`border-t border-app-border ${
                      selectedWord === w.word ? "bg-indigo-50 dark:bg-indigo-950/30" : ""
                    }`}
                  >
                    <td className="px-3 py-1.5">
                      <button
                        type="button"
                        className="font-medium hover:underline"
                        onClick={() => setSelectedWord(w.word)}
                      >
                        {w.word}
                      </button>
                    </td>
                    <td className="px-3 py-1.5">{w.count}</td>
                    <td className="px-3 py-1.5">
                      <Pill tone="slate">{w.lexicon_status}</Pill>
                    </td>
                    <td className="px-3 py-1.5">
                      <div className="flex flex-wrap gap-1">
                        <button
                          type="button"
                          className="text-xs text-indigo-600 hover:underline dark:text-indigo-400"
                          onClick={() => void addLexicon(w.word, "official")}
                        >
                          Official
                        </button>
                        <button
                          type="button"
                          className="text-xs text-indigo-600 hover:underline dark:text-indigo-400"
                          onClick={() => {
                            const can = window.prompt(
                              `Canonical form for alias "${w.word}"`,
                              w.canonical ?? "",
                            );
                            if (can) void addLexicon(w.word, "alias", can);
                          }}
                        >
                          Alias…
                        </button>
                        <button
                          type="button"
                          className="text-xs text-indigo-600 hover:underline dark:text-indigo-400"
                          onClick={() => void addLexicon(w.word, "skip")}
                        >
                          Skip
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <ul className="divide-y divide-app-border">
              {clusters.map((c) => (
                <li key={c.cluster_key} className="p-3 text-sm">
                  <p className="mb-1 text-xs text-app-text-muted">
                    key={c.cluster_key} · {c.total_count} total
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {c.words.map((w) => (
                      <button
                        key={w.word}
                        type="button"
                        className="rounded-full border border-app-border px-2 py-0.5 text-xs hover:bg-app-hover"
                        onClick={() => void setCanonical(c, w.word)}
                        title="Set as canonical"
                      >
                        {w.word} ({w.count})
                      </button>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="max-h-[32rem] overflow-auto rounded-lg border border-app-border bg-app-surface">
          {!selectedWord ? (
            <p className="p-4 text-sm text-app-text-muted">
              Select a word to see occurrences.
            </p>
          ) : (
            <ul>
              {occurrences.map((hit) => (
                <SegmentHitRow
                  key={hit.segment_id}
                  segmentId={hit.segment_id}
                  sourceId={hit.source_id}
                  sourceTitle={hit.source_title}
                  reviewStatus={hit.review_status}
                  status={hit.status}
                  text={hit.text}
                  matches={hit.matches}
                  showCheckbox={false}
                />
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
