import { useEffect, useRef, useState } from "react";
import { PauseIcon, PlayIcon } from "@heroicons/react/20/solid";

let activePreview: HTMLAudioElement | null = null;

function formatClock(sec: number): string {
  if (!Number.isFinite(sec) || sec < 0) return "0:00";
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function SourceAudioPreview({
  sourceId,
  durationSec,
}: {
  sourceId: number;
  durationSec: number | null;
}) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [srcReady, setSrcReady] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(durationSec ?? 0);

  useEffect(() => {
    setDuration(durationSec ?? 0);
  }, [durationSec]);

  useEffect(() => {
    return () => {
      const audio = audioRef.current;
      if (audio && activePreview === audio) {
        audio.pause();
        activePreview = null;
      }
    };
  }, []);

  function ensureAudio(): HTMLAudioElement {
    let audio = audioRef.current;
    if (!audio) {
      audio = new Audio();
      audio.preload = "metadata";
      audio.addEventListener("timeupdate", () => setCurrent(audio!.currentTime));
      audio.addEventListener("loadedmetadata", () => {
        if (Number.isFinite(audio!.duration) && audio!.duration > 0) {
          setDuration(audio!.duration);
        }
      });
      audio.addEventListener("ended", () => {
        setPlaying(false);
        setCurrent(0);
        if (activePreview === audio) activePreview = null;
      });
      audio.addEventListener("pause", () => {
        if (activePreview === audio) setPlaying(false);
      });
      audioRef.current = audio;
    }
    if (!srcReady) {
      audio.src = `/api/sources/${sourceId}/audio`;
      setSrcReady(true);
    }
    return audio;
  }

  async function togglePlay() {
    const audio = ensureAudio();
    if (playing) {
      audio.pause();
      setPlaying(false);
      if (activePreview === audio) activePreview = null;
      return;
    }
    if (activePreview && activePreview !== audio) {
      activePreview.pause();
    }
    activePreview = audio;
    try {
      await audio.play();
      setPlaying(true);
    } catch {
      setPlaying(false);
      if (activePreview === audio) activePreview = null;
    }
  }

  function onSeek(value: number) {
    const audio = ensureAudio();
    audio.currentTime = value;
    setCurrent(value);
  }

  const max = duration > 0 ? duration : Math.max(current, 1);

  return (
    <div className="mt-3 flex items-center gap-2.5">
      <button
        type="button"
        onClick={() => void togglePlay()}
        className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-app-border bg-app-surface text-app-text transition hover:bg-app-hover"
        aria-label={playing ? "Pause preview" : "Play preview"}
      >
        {playing ? (
          <PauseIcon className="h-4 w-4" aria-hidden />
        ) : (
          <PlayIcon className="ml-0.5 h-4 w-4" aria-hidden />
        )}
      </button>
      <input
        type="range"
        min={0}
        max={max}
        step={0.1}
        value={Math.min(current, max)}
        onChange={(e) => onSeek(Number(e.target.value))}
        className="h-1.5 min-w-0 flex-1 accent-indigo-600"
        aria-label="Seek"
      />
      <span className="shrink-0 tabular-nums text-[11px] text-app-text-subtle">
        {formatClock(current)} / {formatClock(duration)}
      </span>
    </div>
  );
}

export function sourceHasAudioPreview(status: string, durationSec: number | null): boolean {
  if (status === "downloaded" || status === "ready") return true;
  if ((status === "failed" || status === "cancelled") && durationSec != null && durationSec > 0) {
    return true;
  }
  return false;
}
