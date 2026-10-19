import { FormEvent, useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowDownTrayIcon, ArrowUpTrayIcon } from "@heroicons/react/20/solid";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import { AppHeader } from "./AppHeader";
import { LangSelect } from "./LangSelect";
import { Button, buttonClass } from "./ui";
import type { ModelVersion, SegmentLang } from "../types";

export function SettingsPage() {
  const { isAdmin } = useAuth();
  const [models, setModels] = useState<ModelVersion[]>([]);
  const [modelName, setModelName] = useState("");
  const [modelRepo, setModelRepo] = useState("");
  const [modelMsg, setModelMsg] = useState<string | null>(null);
  const [modelMsgOk, setModelMsgOk] = useState(true);
  const [youtubeUrl, setYoutubeUrl] = useState("");
  const [defaultLang, setDefaultLang] = useState<SegmentLang>("kreol");
  const [sourceMsg, setSourceMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setModels(await api.listModels());
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    if (isAdmin) void refresh();
  }, [isAdmin, refresh]);

  const run = async (fn: () => Promise<void>, onError: (msg: string) => void) => {
    setBusy(true);
    try {
      await fn();
    } catch (err) {
      onError(String(err));
    } finally {
      setBusy(false);
    }
  };

  const onRegisterModel = async (e: FormEvent) => {
    e.preventDefault();
    if (!modelName.trim() || !modelRepo.trim()) return;
    setModelMsg(null);
    await run(
      async () => {
        await api.registerModel(modelName.trim(), modelRepo.trim(), true);
        setModelName("");
        setModelRepo("");
        setModelMsgOk(true);
        setModelMsg("Model registered and activated. Restart the worker to load it.");
        await refresh();
      },
      (msg) => {
        setModelMsgOk(false);
        setModelMsg(msg);
      },
    );
  };

  const onExportAll = () =>
    run(
      async () => {
        const result = await api.exportAll();
        setModelMsgOk(true);
        setModelMsg(
          `Exported ${result.segment_count} segments (${result.wav_count} WAVs) → ${result.jsonl_path}`,
        );
      },
      (msg) => {
        setModelMsgOk(false);
        setModelMsg(msg);
      },
    );

  const onYouTube = async (e: FormEvent) => {
    e.preventDefault();
    if (!youtubeUrl.trim()) return;
    setError(null);
    await run(async () => {
      await api.createYouTube(youtubeUrl.trim(), { default_lang: defaultLang });
      setYoutubeUrl("");
      setSourceMsg("Source queued for download.");
    }, setError);
  };

  const onFile = (file: File) => {
    setError(null);
    return run(async () => {
      await api.uploadFile(file, { default_lang: defaultLang });
      setSourceMsg(`Uploaded ${file.name}.`);
    }, setError);
  };

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

  const currentModel = models.find((m) => m.is_current);

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <AppHeader />

      <div className="mb-6">
        <h2 className="text-xl font-semibold">Settings</h2>
        <p className="text-sm text-app-text-muted">ASR model and source ingestion</p>
      </div>

      {error && <p className="app-alert-error mb-4">{error}</p>}

      <section className="app-card mb-6 p-4">
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="font-medium">ASR model registry</h3>
          {currentModel && (
            <span className="text-xs text-app-text-muted">
              Current: <span className="text-app-text">{currentModel.name}</span>
              {currentModel.hf_repo && (
                <span className="text-app-text-subtle"> ({currentModel.hf_repo})</span>
              )}
            </span>
          )}
        </div>
        <p className="mb-3 text-xs text-app-text-subtle">
          After training, register a private Hugging Face CT2 repo (e.g. creole-asr-v1). Restart
          the worker after activating.
        </p>
        <form onSubmit={onRegisterModel} className="mb-3 flex flex-wrap gap-2">
          <input
            type="text"
            placeholder="Display name"
            value={modelName}
            onChange={(e) => setModelName(e.target.value)}
            className="app-input min-w-[8rem] flex-1"
          />
          <input
            type="text"
            placeholder="HF repo (user/creole-asr-v1)"
            value={modelRepo}
            onChange={(e) => setModelRepo(e.target.value)}
            className="app-input min-w-[12rem] flex-[2]"
          />
          <Button type="submit" variant="primary" disabled={busy}>
            Register & activate
          </Button>
        </form>
        <Button
          variant="secondary"
          icon={ArrowDownTrayIcon}
          disabled={busy}
          onClick={() => void onExportAll()}
        >
          Export all validated (training JSONL)
        </Button>
        {modelMsg && (
          <p
            className={`mt-3 whitespace-pre-wrap ${
              modelMsgOk ? "app-alert-success" : "app-alert-error"
            }`}
          >
            {modelMsg}
          </p>
        )}
      </section>

      <section className="app-card p-4">
        <h3 className="mb-3 font-medium">Add source</h3>
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-app-text-muted">
            Main language
            <LangSelect pill value={defaultLang} onChange={setDefaultLang} />
          </label>
          <span className="text-xs text-app-text-subtle">Applied to all segments on import</span>
        </div>
        <form onSubmit={onYouTube} className="mb-4 flex gap-2">
          <input
            type="url"
            placeholder="YouTube URL"
            value={youtubeUrl}
            onChange={(e) => setYoutubeUrl(e.target.value)}
            className="app-input flex-1"
          />
          <Button type="submit" variant="primary" disabled={busy}>
            Ingest
          </Button>
        </form>
        <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-app-text-muted">
          <span className={buttonClass({ variant: "secondary" })}>
            <ArrowUpTrayIcon className="h-4 w-4" aria-hidden />
            Upload audio/video
          </span>
          <input
            type="file"
            accept="audio/*,video/*"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void onFile(f);
            }}
          />
        </label>
        {sourceMsg && (
          <p className="app-alert-success mt-3">
            {sourceMsg}{" "}
            <Link to="/" className="font-medium text-indigo-700 hover:underline dark:text-indigo-300">
              View in Sources →
            </Link>
          </p>
        )}
      </section>
    </div>
  );
}
