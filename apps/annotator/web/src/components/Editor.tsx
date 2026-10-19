import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import WaveSurfer from "wavesurfer.js";
import RegionsPlugin from "wavesurfer.js/dist/plugins/regions.esm.js";
import TimelinePlugin from "wavesurfer.js/dist/plugins/timeline.esm.js";
import { Link } from "react-router-dom";
import {
  ArrowDownTrayIcon,
  PauseIcon,
  PlayIcon,
} from "@heroicons/react/20/solid";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import { NormalizeModal, SegmentNormalizePreview } from "./NormalizePanel";
import { LortografHints } from "./LortografHints";
import { LangSelect } from "./LangSelect";
import { SpeakersPanel } from "./SpeakersPanel";
import { YoutubeLink } from "./SourceCard";
import { SystemAlerts } from "./SystemAlerts";
import { ThemeToggle } from "./ThemeToggle";
import { Button } from "./ui";
import { useKeyboardShortcuts } from "../hooks/useKeyboardShortcuts";
import { useLortografPreview } from "../hooks/useLortografPreview";
import { getWaveformColors, useTheme } from "../theme/ThemeProvider";
import type {
  EditorSession,
  NormalizePreview,
  Segment,
  WordChange,
  SegmentLang,
  SegmentStatus,
  Speaker,
  SystemAlert,
  WaveformPeaks,
} from "../types";
import { SEGMENT_LANG_LABELS, SEGMENT_LANGS } from "../types";

const STATUSES: SegmentStatus[] = ["raw", "corrected", "validated", "ignored"];

function statusBadgeClass(status: SegmentStatus): string {
  if (status === "validated") {
    return "rounded-full bg-green-100 px-1.5 py-0.5 text-green-800 dark:bg-green-900 dark:text-green-300";
  }
  if (status === "corrected") {
    return "rounded-full bg-amber-100 px-1.5 py-0.5 text-amber-900 dark:bg-amber-900 dark:text-amber-300";
  }
  if (status === "ignored") {
    return "rounded-full bg-slate-200 px-1.5 py-0.5 text-slate-600 dark:bg-slate-700 dark:text-slate-300";
  }
  return "rounded-full bg-app-hover px-1.5 py-0.5 text-app-text-muted";
}

function unignoreStatus(segment: Segment): SegmentStatus {
  const text = (segment.text_corrected ?? segment.text_raw ?? "").trim();
  return text ? "corrected" : "raw";
}

function segmentHasText(segment: Segment): boolean {
  return Boolean((segment.text_corrected ?? segment.text_raw ?? "").trim());
}
const PLAY_ON_SINGLE_CLICK_KEY = "motranscript.playOnSingleClick";

function readPlayOnSingleClick(): boolean {
  try {
    const raw = localStorage.getItem(PLAY_ON_SINGLE_CLICK_KEY);
    if (raw === null) return true;
    return raw !== "false";
  } catch {
    return true;
  }
}

function waveformStructureKey(segments: Segment[]): string {
  return segments
    .map(
      (s) =>
        `${s.id}:${s.start_sec}:${s.end_sec}:${s.speaker_id}:${s.review_comment?.trim() ? 1 : 0}`,
    )
    .join("|");
}

const TRANSPARENT_REGION = "rgba(0,0,0,0)";

interface EditorProps {
  session: EditorSession;
  mockMode?: boolean;
  onSessionChange?: (session: EditorSession) => void;
  initialSegmentId?: number;
}

export function Editor({
  session: initialSession,
  mockMode = false,
  onSessionChange,
  initialSegmentId,
}: EditorProps) {
  const { theme } = useTheme();
  const { isAdmin } = useAuth();
  const [session, setSession] = useState(initialSession);
  const initialId =
    initialSegmentId != null &&
    initialSession.segments.some((s) => s.id === initialSegmentId)
      ? initialSegmentId
      : (initialSession.segments[0]?.id ?? null);
  const [selectedId, setSelectedId] = useState<number | null>(initialId);
  const [saving, setSaving] = useState(false);
  const [exportMsg, setExportMsg] = useState<string | null>(null);
  const [segmentPreview, setSegmentPreview] = useState<NormalizePreview | null>(null);
  const [bulkModal, setBulkModal] = useState<NormalizePreview[] | null>(null);
  const [normalizing, setNormalizing] = useState(false);
  const [checkedIds, setCheckedIds] = useState<Set<number>>(() => new Set());
  const [bulkLang, setBulkLang] = useState<SegmentLang>("kreol");
  const [bulkLangBusy, setBulkLangBusy] = useState(false);
  const [globalAlerts, setGlobalAlerts] = useState<SystemAlert[]>([]);
  const [frozenTestBusy, setFrozenTestBusy] = useState(false);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [playOnSingleClick, setPlayOnSingleClick] = useState(readPlayOnSingleClick);
  const [playingSegmentId, setPlayingSegmentId] = useState<number | null>(null);
  const [isAudioPlaying, setIsAudioPlaying] = useState(false);
  const [audioDuration, setAudioDuration] = useState(0);
  const [peaksData, setPeaksData] = useState<WaveformPeaks | null>(null);
  const [peaksReady, setPeaksReady] = useState(false);
  const [waveformZoomed, setWaveformZoomed] = useState(false);
  const waveformRef = useRef<HTMLDivElement>(null);
  const timelineRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WaveSurfer | null>(null);
  const regionsRef = useRef<ReturnType<typeof RegionsPlugin.create> | null>(null);
  const selectionAnchorRef = useRef(0);
  const selectedIdRef = useRef<number | null>(initialId);
  const segmentsRef = useRef(initialSession.segments);
  const speakerMapRef = useRef(new Map(initialSession.speakers.map((s) => [s.id, s])));
  const playingSegmentIdRef = useRef<number | null>(null);
  const startingPlayRef = useRef(false);
  const waveformZoomedRef = useRef(false);
  const minPxPerSecRef = useRef(0);
  const zoomToSegmentRef = useRef<(seg: Segment) => void>(() => {});

  const speakerMap = useMemo(
    () => new Map(session.speakers.map((s) => [s.id, s])),
    [session.speakers],
  );

  const structureKey = useMemo(
    () => waveformStructureKey(session.segments),
    [session.segments],
  );

  useEffect(() => {
    if (initialSegmentId == null) return;
    const el = document.querySelector(`[data-segment-id="${initialSegmentId}"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [initialSegmentId]);

  useEffect(() => {
    segmentsRef.current = session.segments;
  }, [session.segments]);

  useEffect(() => {
    speakerMapRef.current = speakerMap;
  }, [speakerMap]);

  useEffect(() => {
    playingSegmentIdRef.current = playingSegmentId;
  }, [playingSegmentId]);

  useEffect(() => {
    waveformZoomedRef.current = waveformZoomed;
  }, [waveformZoomed]);

  useEffect(() => {
    try {
      localStorage.setItem(PLAY_ON_SINGLE_CLICK_KEY, playOnSingleClick ? "true" : "false");
    } catch {
      /* ignore quota / private mode */
    }
  }, [playOnSingleClick]);

  const selectedIndex = session.segments.findIndex((s) => s.id === selectedId);
  const selected = selectedIndex >= 0 ? session.segments[selectedIndex] : null;

  const selectSegment = useCallback((id: number | null) => {
    selectedIdRef.current = id;
    setSelectedId(id);
  }, []);

  const zoomToSegment = useCallback((seg: Segment) => {
    const ws = wsRef.current;
    if (!ws) return;
    const duration = ws.getDuration() || audioDuration;
    if (duration <= 0) return;
    const width = ws.getWidth() || waveformRef.current?.clientWidth || 0;
    if (width <= 0) return;

    const pad = 0.5;
    const start = Math.max(0, seg.start_sec - pad);
    const end = Math.min(duration, seg.end_sec + pad);
    const windowSec = Math.max(end - start, 2);
    const minPxPerSec = width / windowSec;
    minPxPerSecRef.current = minPxPerSec;
    ws.zoom(minPxPerSec);
    ws.setScrollTime(start);
    waveformZoomedRef.current = true;
    setWaveformZoomed(true);
  }, [audioDuration]);

  const zoomToFull = useCallback(() => {
    const ws = wsRef.current;
    if (!ws) {
      waveformZoomedRef.current = false;
      setWaveformZoomed(false);
      minPxPerSecRef.current = 0;
      return;
    }
    const duration = ws.getDuration() || audioDuration;
    const width = ws.getWidth() || waveformRef.current?.clientWidth || 0;
    if (duration > 0 && width > 0) {
      const fit = width / duration;
      minPxPerSecRef.current = fit;
      ws.zoom(fit);
      ws.setScroll(0);
    }
    waveformZoomedRef.current = false;
    setWaveformZoomed(false);
  }, [audioDuration]);

  useEffect(() => {
    zoomToSegmentRef.current = zoomToSegment;
  }, [zoomToSegment]);

  const allChecked =
    session.segments.length > 0 && checkedIds.size === session.segments.length;

  const alerts = useMemo(() => {
    const seen = new Set<string>();
    const merged = [...globalAlerts, ...(session.alerts ?? [])];
    return merged.filter((alert) => {
      if (seen.has(alert.id)) return false;
      seen.add(alert.id);
      return true;
    });
  }, [globalAlerts, session.alerts]);

  useEffect(() => {
    if (mockMode || !isAdmin) return;
    const load = () => {
      void api
        .getConfig()
        .then((cfg) => setGlobalAlerts(cfg.alerts ?? []))
        .catch(() => {});
    };
    load();
    const id = window.setInterval(load, 5000);
    return () => window.clearInterval(id);
  }, [mockMode, isAdmin]);

  const toggleChecked = useCallback((id: number) => {
    setCheckedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const toggleAllChecked = useCallback(() => {
    setCheckedIds((prev) =>
      prev.size === session.segments.length
        ? new Set()
        : new Set(session.segments.map((s) => s.id)),
    );
  }, [session.segments]);

  const selectSegmentRange = useCallback(
    (fromIndex: number, toIndex: number, additive: boolean) => {
      const start = Math.min(fromIndex, toIndex);
      const end = Math.max(fromIndex, toIndex);
      const rangeIds = session.segments.slice(start, end + 1).map((s) => s.id);
      setCheckedIds((prev) => {
        if (additive) {
          const next = new Set(prev);
          rangeIds.forEach((id) => next.add(id));
          return next;
        }
        return new Set(rangeIds);
      });
    },
    [session.segments],
  );

  const handleSelectionClick = useCallback(
    (seg: Segment, index: number, e: { metaKey: boolean; ctrlKey: boolean; shiftKey: boolean; preventDefault: () => void; stopPropagation: () => void }) => {
      if (e.shiftKey) {
        e.preventDefault();
        e.stopPropagation();
        selectSegmentRange(selectionAnchorRef.current, index, e.metaKey || e.ctrlKey);
        selectSegment(seg.id);
        selectionAnchorRef.current = index;
        return true;
      }
      if (e.metaKey || e.ctrlKey) {
        e.preventDefault();
        e.stopPropagation();
        toggleChecked(seg.id);
        selectSegment(seg.id);
        selectionAnchorRef.current = index;
        return true;
      }
      selectionAnchorRef.current = index;
      return false;
    },
    [selectSegment, selectSegmentRange, toggleChecked],
  );

  useEffect(() => {
    setSegmentPreview(null);
  }, [selectedId]);

  const updateSession = useCallback(
    (updater: (prev: EditorSession) => EditorSession) => {
      setSession((prev) => {
        const next = updater(prev);
        onSessionChange?.(next);
        return next;
      });
    },
    [onSessionChange],
  );

  const applyBulkLang = useCallback(async () => {
    const ids = Array.from(checkedIds);
    if (!ids.length) return;
    setBulkLangBusy(true);
    try {
      if (mockMode) {
        updateSession((prev) => ({
          ...prev,
          segments: prev.segments.map((s) =>
            checkedIds.has(s.id) ? { ...s, lang: bulkLang } : s,
          ),
        }));
      } else {
        const updated = await api.bulkUpdateSegmentLang(session.source.id, ids, bulkLang);
        const byId = new Map(updated.map((s) => [s.id, s]));
        updateSession((prev) => ({
          ...prev,
          segments: prev.segments.map((s) => (byId.has(s.id) ? { ...s, lang: byId.get(s.id)!.lang } : s)),
        }));
      }
      setCheckedIds(new Set());
    } catch (e) {
      setExportMsg(String(e));
    } finally {
      setBulkLangBusy(false);
    }
  }, [bulkLang, checkedIds, mockMode, session.source.id, updateSession]);

  const reviewStatus = session.source.review_status ?? "todo";
  const readOnly = !isAdmin && reviewStatus === "validated";
  const canMarkDone =
    reviewStatus === "todo" &&
    session.segments.length > 0 &&
    session.segments.every(
      (s) => s.status === "corrected" || s.status === "validated" || s.status === "ignored",
    );
  const flaggedSegments = useMemo(
    () => session.segments.filter((s) => Boolean(s.review_comment?.trim())),
    [session.segments],
  );

  const persistSegment = useCallback(
    async (segment: Segment) => {
      if (mockMode || readOnly) return;
      setSaving(true);
      try {
        await api.updateSegment(segment.id, {
          text_corrected: segment.text_corrected ?? undefined,
          lang: segment.lang,
          status: segment.status,
        });
      } finally {
        setSaving(false);
      }
    },
    [mockMode, readOnly],
  );

  const persistSpeaker = useCallback(
    async (speaker: Speaker) => {
      if (mockMode) return;
      await api.updateSpeaker(speaker.id, { display_name: speaker.display_name ?? undefined });
    },
    [mockMode],
  );

  const renameSpeaker = useCallback(
    (speakerId: number, displayName: string) => {
      updateSession((prev) => ({
        ...prev,
        speakers: prev.speakers.map((s) =>
          s.id === speakerId ? { ...s, display_name: displayName } : s,
        ),
      }));
    },
    [updateSession],
  );

  const saveSpeaker = useCallback(
    (speakerId: number) => {
      const speaker = session.speakers.find((s) => s.id === speakerId);
      if (!speaker) return;
      const finalName = speaker.display_name?.trim() || speaker.label;
      if (finalName !== speaker.display_name) {
        renameSpeaker(speakerId, finalName);
      }
      void persistSpeaker({ ...speaker, display_name: finalName });
    },
    [persistSpeaker, renameSpeaker, session.speakers],
  );

  const patchSegment = useCallback(
    (id: number, patch: Partial<Segment>) => {
      updateSession((prev) => ({
        ...prev,
        segments: prev.segments.map((s) => (s.id === id ? { ...s, ...patch } : s)),
      }));
    },
    [updateSession],
  );

  const toggleIgnoreSegment = useCallback(
    async (segment: Segment) => {
      if (readOnly) return;
      const nextStatus: SegmentStatus =
        segment.status === "ignored" ? unignoreStatus(segment) : "ignored";
      const updated = { ...segment, status: nextStatus };
      patchSegment(segment.id, { status: nextStatus });
      await persistSegment(updated);
    },
    [patchSegment, persistSegment, readOnly],
  );

  // Prefetch peaks so WaveSurfer can skip full-file decode
  useEffect(() => {
    let cancelled = false;
    setPeaksReady(false);
    setPeaksData(null);

    if (mockMode || !session.source.id) {
      setPeaksReady(true);
      return;
    }

    void api
      .getPeaks(session.source.id)
      .then((data) => {
        if (cancelled) return;
        setPeaksData(data);
        setPeaksReady(true);
      })
      .catch(() => {
        if (cancelled) return;
        setPeaksData(null);
        setPeaksReady(true);
      });

    return () => {
      cancelled = true;
    };
  }, [session.audio_url, session.source.id, mockMode]);

  // WaveSurfer setup — remount only when audio URL changes (after peaks settle)
  useEffect(() => {
    if (!peaksReady || !waveformRef.current || !timelineRef.current) return;

    const regions = RegionsPlugin.create();
    regionsRef.current = regions;

    const { waveColor, cursorColor } = getWaveformColors();

    const opts: Parameters<typeof WaveSurfer.create>[0] = {
      container: waveformRef.current,
      waveColor,
      progressColor: "#818cf8",
      cursorColor,
      height: 120,
      url: session.audio_url,
      dragToSeek: true,
      plugins: [
        regions,
        TimelinePlugin.create({ container: timelineRef.current }),
      ],
    };
    if (peaksData?.peaks?.length && peaksData.duration > 0) {
      opts.peaks = peaksData.peaks;
      opts.duration = peaksData.duration;
    }

    const ws = WaveSurfer.create(opts);
    wsRef.current = ws;

    ws.on("ready", () => {
      setAudioDuration(ws.getDuration() || peaksData?.duration || 0);
    });
    ws.on("play", () => {
      startingPlayRef.current = false;
      setIsAudioPlaying(true);
    });
    ws.on("pause", () => {
      if (startingPlayRef.current) return;
      setIsAudioPlaying(false);
      playingSegmentIdRef.current = null;
      setPlayingSegmentId(null);
    });
    ws.on("finish", () => {
      startingPlayRef.current = false;
      setIsAudioPlaying(false);
      playingSegmentIdRef.current = null;
      setPlayingSegmentId(null);
    });

    regions.on("region-clicked", (region, e) => {
      e.stopPropagation();
      const id = Number(region.id);
      const seg = segmentsRef.current.find((s) => s.id === id);
      selectedIdRef.current = id;
      setSelectedId(id);
      const duration = ws.getDuration() || 1;
      const rect = waveformRef.current?.getBoundingClientRect();
      let clickTime: number;
      const pxPerSec = minPxPerSecRef.current;
      if (waveformZoomedRef.current && pxPerSec > 0 && rect) {
        const xInWave = e.clientX - rect.left + ws.getScroll();
        clickTime = Math.min(Math.max(xInWave / pxPerSec, 0), duration);
      } else {
        const relX = rect ? (e.clientX - rect.left) / rect.width : region.start / duration;
        clickTime = Math.min(Math.max(relX * duration, 0), duration);
      }
      const clamped = seg
        ? Math.min(Math.max(clickTime, seg.start_sec), Math.max(seg.start_sec, seg.end_sec - 0.01))
        : region.start;
      if (seg) zoomToSegmentRef.current(seg);
      if (ws.isPlaying() && seg) {
        startingPlayRef.current = true;
        playingSegmentIdRef.current = seg.id;
        setPlayingSegmentId(seg.id);
        setIsAudioPlaying(true);
        void ws.play(clamped, seg.end_sec).catch(() => {
          startingPlayRef.current = false;
          setIsAudioPlaying(false);
        });
      } else {
        ws.setTime(clamped);
      }
    });

    // Click on empty waveform (outside regions): deselect when showing full track
    ws.on("interaction", (newTime) => {
      const selId = selectedIdRef.current;
      if (selId == null) return;
      const seg = segmentsRef.current.find((s) => s.id === selId);
      if (!seg) return;
      if (newTime >= seg.start_sec && newTime < seg.end_sec) {
        // Scrub inside selected block — keep selection; if playing, stop at end
        if (ws.isPlaying()) {
          void ws.play(newTime, seg.end_sec);
        }
        return;
      }
      // While zoomed, allow scrubbing nearby without clearing selection
      if (waveformZoomedRef.current) return;
      selectedIdRef.current = null;
      setSelectedId(null);
    });

    return () => {
      ws.destroy();
      wsRef.current = null;
      regionsRef.current = null;
      playingSegmentIdRef.current = null;
      setPlayingSegmentId(null);
      setIsAudioPlaying(false);
      setAudioDuration(0);
      minPxPerSecRef.current = 0;
      waveformZoomedRef.current = false;
      setWaveformZoomed(false);
    };
  }, [session.audio_url, peaksReady, peaksData]);

  // Theme colors without remounting (keeps playback + overlay duration)
  useEffect(() => {
    const ws = wsRef.current;
    if (!ws) return;
    const { waveColor, cursorColor } = getWaveformColors();
    ws.setOptions({ waveColor, cursorColor });
  }, [theme, peaksReady]);

  // Sync regions in place when segments / selection change (no WaveSurfer remount)
  useEffect(() => {
    const regions = regionsRef.current;
    if (!regions || !peaksReady) return;

    const existing = new Map(regions.getRegions().map((r) => [r.id, r]));
    const wanted = new Set(session.segments.map((s) => String(s.id)));

    session.segments.forEach((seg) => {
      const id = String(seg.id);
      const region = existing.get(id);
      if (region) {
        region.setOptions({
          start: seg.start_sec,
          end: seg.end_sec,
          color: TRANSPARENT_REGION,
        });
      } else {
        regions.addRegion({
          id,
          start: seg.start_sec,
          end: seg.end_sec,
          color: TRANSPARENT_REGION,
          drag: false,
          resize: false,
        });
      }
    });

    existing.forEach((region, id) => {
      if (!wanted.has(id)) region.remove();
    });
  }, [structureKey, session.segments, peaksReady]);

  const seekToSegment = useCallback(
    (seg: Segment) => {
      wsRef.current?.pause();
      selectSegment(seg.id);
      wsRef.current?.setTime(seg.start_sec);
      const index = session.segments.findIndex((s) => s.id === seg.id);
      if (index >= 0) selectionAnchorRef.current = index;
      zoomToSegment(seg);
    },
    [selectSegment, session.segments, zoomToSegment],
  );

  const playSelectedSegment = useCallback(
    (seg?: Segment) => {
      const target = seg ?? selected;
      const ws = wsRef.current;
      if (!target || !ws) return;
      selectSegment(target.id);
      zoomToSegment(target);
      startingPlayRef.current = true;
      playingSegmentIdRef.current = target.id;
      setPlayingSegmentId(target.id);
      setIsAudioPlaying(true);
      void ws.play(target.start_sec, target.end_sec).catch(() => {
        startingPlayRef.current = false;
        setIsAudioPlaying(false);
        playingSegmentIdRef.current = null;
        setPlayingSegmentId(null);
      });
    },
    [selectSegment, selected, zoomToSegment],
  );

  const toggleSegmentPlayback = useCallback(
    (seg: Segment) => {
      const ws = wsRef.current;
      if (!ws) return;
      if ((ws.isPlaying() || isAudioPlaying) && playingSegmentIdRef.current === seg.id) {
        startingPlayRef.current = false;
        ws.pause();
        setIsAudioPlaying(false);
        playingSegmentIdRef.current = null;
        setPlayingSegmentId(null);
        return;
      }
      playSelectedSegment(seg);
    },
    [isAudioPlaying, playSelectedSegment],
  );

  const clearSelection = useCallback(() => {
    selectedIdRef.current = null;
    setSelectedId(null);
    startingPlayRef.current = false;
    wsRef.current?.pause();
    zoomToFull();
  }, [zoomToFull]);

  const toggleSelectedSegmentPlayback = useCallback(() => {
    const ws = wsRef.current;
    if (!ws) return;
    if (ws.isPlaying() || isAudioPlaying) {
      startingPlayRef.current = false;
      ws.pause();
      setIsAudioPlaying(false);
      playingSegmentIdRef.current = null;
      setPlayingSegmentId(null);
      return;
    }
    if (selected) {
      const t = ws.getCurrentTime();
      const start =
        t >= selected.start_sec && t < selected.end_sec ? t : selected.start_sec;
      startingPlayRef.current = true;
      playingSegmentIdRef.current = selected.id;
      setPlayingSegmentId(selected.id);
      setIsAudioPlaying(true);
      void ws.play(start, selected.end_sec).catch(() => {
        startingPlayRef.current = false;
        setIsAudioPlaying(false);
        playingSegmentIdRef.current = null;
        setPlayingSegmentId(null);
      });
      return;
    }
    startingPlayRef.current = true;
    playingSegmentIdRef.current = null;
    setPlayingSegmentId(null);
    setIsAudioPlaying(true);
    void ws.play().catch(() => {
      startingPlayRef.current = false;
      setIsAudioPlaying(false);
    });
  }, [isAudioPlaying, selected]);

  const handlers = useMemo(
    () => ({
      onPlayPause: toggleSelectedSegmentPlayback,
      onPrev: () => {
        if (selectedIndex > 0) seekToSegment(session.segments[selectedIndex - 1]);
      },
      onNext: () => {
        if (selectedIndex < session.segments.length - 1)
          seekToSegment(session.segments[selectedIndex + 1]);
      },
      onValidate: async () => {
        if (!selected || selected.status === "ignored") return;
        if (!segmentHasText(selected)) {
          setExportMsg("Cannot validate empty text — Ignore the segment instead.");
          return;
        }
        const updated = { ...selected, status: "validated" as SegmentStatus };
        patchSegment(selected.id, { status: "validated" });
        await persistSegment(updated);
        if (selectedIndex < session.segments.length - 1)
          seekToSegment(session.segments[selectedIndex + 1]);
      },
      onSave: () => {
        if (selected) void persistSegment(selected);
      },
      onDeselect: clearSelection,
    }),
    [
      clearSelection,
      patchSegment,
      persistSegment,
      seekToSegment,
      selected,
      selectedIndex,
      session.segments,
      toggleSelectedSegmentPlayback,
    ],
  );

  useKeyboardShortcuts(handlers);

  const canNormalize = (lang: SegmentLang) => lang === "kreol" || lang === "mix";

  const handleSegmentNormalize = async () => {
    if (!selected || mockMode) return;
    setNormalizing(true);
    try {
      const preview = await api.normalizeSegment(selected.id, false);
      setSegmentPreview(preview);
    } catch (e) {
      setExportMsg(String(e));
    } finally {
      setNormalizing(false);
    }
  };

  const acceptSegmentNormalize = async () => {
    if (!selected || !segmentPreview || mockMode) return;
    setNormalizing(true);
    try {
      const applied = await api.normalizeSegment(selected.id, true);
      patchSegment(selected.id, {
        text_corrected: applied.proposed,
        status: selected.status === "raw" ? "corrected" : selected.status,
      });
      setSegmentPreview(null);
    } finally {
      setNormalizing(false);
    }
  };

  const handleBulkNormalize = async () => {
    if (mockMode) {
      setExportMsg("Normalize requires API connection");
      return;
    }
    setNormalizing(true);
    try {
      const result = await api.normalizeSource(session.source.id, false);
      setBulkModal(result.previews);
    } catch (e) {
      setExportMsg(String(e));
    } finally {
      setNormalizing(false);
    }
  };

  const applyBulkNormalize = async () => {
    if (mockMode || !bulkModal) return;
    setNormalizing(true);
    try {
      const result = await api.normalizeSource(session.source.id, true);
      updateSession((prev) => ({
        ...prev,
        segments: prev.segments.map((seg) => {
          const preview = result.previews.find((p) => p.segment_id === seg.id);
          if (!preview?.changed) return seg;
          return {
            ...seg,
            text_corrected: preview.proposed,
            status: seg.status === "raw" ? "corrected" : seg.status,
          };
        }),
      }));
      setBulkModal(null);
    } finally {
      setNormalizing(false);
    }
  };

  const handleExport = async () => {
    if (mockMode) {
      setExportMsg("Export requires API connection");
      return;
    }
    try {
      const check = await api.exportCheck(session.source.id);
      if (check.needs_normalization_count > 0) {
        const ok = window.confirm(
          `${check.needs_normalization_count} validated segment(s) still have non-Lortograf spelling. Export anyway?`,
        );
        if (!ok) return;
      }
      const result = await api.exportSource(session.source.id);
      let msg = `Exported ${result.segment_count} segments (${result.wav_count} WAVs) → ${result.jsonl_path}`;
      if (result.normalization_warnings.length) {
        msg += `\nWarning: ${result.normalization_warnings.join("; ")}`;
      }
      setExportMsg(msg);
    } catch (e) {
      setExportMsg(String(e));
    }
  };

  const handleMarkFrozenTest = async () => {
    if (mockMode) {
      setExportMsg("Frozen test marking requires API connection");
      return;
    }
    if (
      !window.confirm(
        "Mark this entire source as the frozen test set? All segments will be excluded from training forever.",
      )
    ) {
      return;
    }
    setFrozenTestBusy(true);
    try {
      const result = await api.markFrozenTest(session.source.id);
      const refreshed = await api.getSession(session.source.id);
      setSession(refreshed);
      onSessionChange?.(refreshed);
      setExportMsg(`Marked ${result.segment_count} segments as frozen test (split=test).`);
    } catch (e) {
      setExportMsg(String(e));
    } finally {
      setFrozenTestBusy(false);
    }
  };

  const isFrozenTestSource =
    session.segments.length > 0 && session.segments.every((s) => s.split === "test");

  const setReview = async (status: "todo" | "done" | "validated", note?: string) => {
    if (mockMode) return;
    setReviewBusy(true);
    try {
      const updated = await api.setReviewStatus(session.source.id, status, note);
      updateSession((prev) => ({
        ...prev,
        source: {
          ...prev.source,
          review_status: updated.review_status,
          review_note: updated.review_note,
          reviewed_by: updated.reviewed_by,
          reviewed_at: updated.reviewed_at,
        },
        segments:
          status === "validated"
            ? prev.segments.map((s) => ({
                ...s,
                review_comment: null,
                review_comment_by: null,
              }))
            : prev.segments,
      }));
      setExportMsg(
        status === "done"
          ? "Marked as done."
          : status === "validated"
            ? "Validated."
            : "Sent back to to-do.",
      );
    } catch (e) {
      setExportMsg(String(e));
    } finally {
      setReviewBusy(false);
    }
  };

  const saveReviewComment = async (segmentId: number, comment: string | null) => {
    if (mockMode || !isAdmin) return;
    const updated = await api.setSegmentReviewComment(segmentId, comment);
    patchSegment(segmentId, {
      review_comment: updated.review_comment,
      review_comment_by: updated.review_comment_by,
    });
  };

  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center justify-between border-b border-app-border px-4 py-3">
        <div className="flex items-center gap-3">
          {!mockMode && (
            <Link to="/" className="text-sm text-app-text-muted hover:text-app-text">
              ← Sources
            </Link>
          )}
          <div>
            <h1 className="text-lg font-semibold">{session.source.title ?? "Untitled"}</h1>
          <p className="text-xs text-app-text-muted">
            <YoutubeLink
              url={session.source.source_url}
              className="text-indigo-600 hover:underline dark:text-indigo-400"
            >
              {session.source.source_type}
            </YoutubeLink>
            {" · "}
            {mockMode ? "Mock mode" : `Source #${session.source.id}`} ·{" "}
            {session.segments.length} segments
            {` · ${reviewStatus === "todo" ? "to do" : reviewStatus === "done" ? "done" : "validated"}`}
            {isFrozenTestSource ? " · frozen test" : ""}
            {readOnly ? " · read-only" : ""}
            {saving ? " · saving…" : ""}
          </p>
          </div>
        </div>
        <div className="flex flex-wrap justify-end gap-1.5">
          <ThemeToggle />
          {!readOnly && (
            <Button
              variant="muted"
              size="sm"
              onClick={() => void handleBulkNormalize()}
              disabled={normalizing || mockMode}
              title={mockMode ? "Requires API connection" : "Normalize all Kreol/mix segments"}
            >
              Normalize (Lortograf)
            </Button>
          )}
          {reviewStatus === "todo" && canMarkDone && (
            <Button
              size="sm"
              variant="outline"
              tone="green"
              disabled={reviewBusy || mockMode || readOnly}
              onClick={() => void setReview("done")}
            >
              Done
            </Button>
          )}
          {reviewStatus === "done" && (
            <Button
              size="sm"
              variant="muted"
              disabled={reviewBusy || mockMode}
              onClick={() => void setReview("todo")}
            >
              Reopen
            </Button>
          )}
          {isAdmin && reviewStatus === "done" && (
            <Button
              size="sm"
              variant="outline"
              tone="green"
              disabled={reviewBusy || mockMode}
              onClick={() => void setReview("validated")}
            >
              Validate
            </Button>
          )}
          {isAdmin && (reviewStatus === "done" || reviewStatus === "validated") && (
            <Button
              size="sm"
              variant="outline"
              tone="amber"
              disabled={reviewBusy || mockMode}
              onClick={() => {
                const note = window.prompt("Reason for sending back (optional):") ?? undefined;
                void setReview("todo", note || undefined);
              }}
            >
              Send back
            </Button>
          )}
          {isAdmin && (
            <Button
              size="sm"
              variant="muted"
              onClick={() => void handleMarkFrozenTest()}
              disabled={frozenTestBusy || mockMode || isFrozenTestSource}
              title="Exclude all segments from training (benchmark only)"
            >
              Mark frozen test
            </Button>
          )}
          {isAdmin && (
            <Button
              size="sm"
              variant="primary"
              icon={ArrowDownTrayIcon}
              onClick={() => void handleExport()}
            >
              Export validated
            </Button>
          )}
        </div>
      </header>

      {session.source.review_note && reviewStatus === "todo" && (
        <div className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/40 dark:text-amber-200">
          Admin note: {session.source.review_note}
        </div>
      )}

      {flaggedSegments.length > 0 && reviewStatus === "todo" && (
        <div className="border-b border-amber-200 bg-amber-50/70 px-4 py-2 dark:border-amber-900/40 dark:bg-amber-950/30">
          <p className="mb-1 text-xs font-medium text-amber-900 dark:text-amber-200">
            To review ({flaggedSegments.length})
          </p>
          <div className="flex flex-wrap gap-2">
            {flaggedSegments.map((s) => (
              <button
                key={s.id}
                type="button"
                onClick={() => {
                  seekToSegment(s);
                }}
                className="rounded-full border border-amber-300 px-2.5 py-0.5 text-xs font-medium text-amber-900 hover:bg-amber-100 dark:border-amber-800 dark:text-amber-200 dark:hover:bg-amber-900/40"
              >
                {s.start_sec.toFixed(1)}s
              </button>
            ))}
          </div>
        </div>
      )}

      {alerts.length > 0 && (
        <div className="border-b border-app-border px-4 py-3">
          <SystemAlerts alerts={alerts} compact />
        </div>
      )}

      <SpeakersPanel
        speakers={session.speakers}
        segments={session.segments}
        mockMode={mockMode}
        onRename={renameSpeaker}
        onSave={saveSpeaker}
      />

      <div className="border-b border-app-border px-4 py-3">
        <div className="relative">
          <div ref={waveformRef} />
          {selected && audioDuration > 0 && !waveformZoomed && (
            <div className="pointer-events-none absolute inset-0 z-10 overflow-hidden">
              <div
                className="absolute inset-y-0 rounded-sm border-x-2 border-slate-900 bg-slate-900/[0.06] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.85)] transition-[left,width] duration-200 dark:border-white dark:bg-white/10 dark:shadow-[inset_0_0_0_1px_rgba(0,0,0,0.6)]"
                style={{
                  left: `${(selected.start_sec / audioDuration) * 100}%`,
                  width: `${(Math.max(0, selected.end_sec - selected.start_sec) / audioDuration) * 100}%`,
                }}
              >
                <span className="absolute left-0 top-0 h-1.5 w-2 rounded-br-sm bg-slate-900 dark:bg-white" />
                <span className="absolute right-0 top-0 h-1.5 w-2 rounded-bl-sm bg-slate-900 dark:bg-white" />
              </div>
            </div>
          )}
        </div>
        <div ref={timelineRef} className="mt-1" />
        <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-app-text-subtle">
          <label className="flex cursor-pointer items-center gap-1.5 text-app-text-muted">
            <input
              type="checkbox"
              checked={playOnSingleClick}
              onChange={(e) => setPlayOnSingleClick(e.target.checked)}
              className="rounded border-app-border"
            />
            Play on single click
          </label>
          {waveformZoomed && (
            <button
              type="button"
              onClick={zoomToFull}
              className="font-medium text-indigo-600 underline-offset-2 hover:underline dark:text-indigo-400"
            >
              Show full waveform
            </button>
          )}
          <span>
            Space play · {playOnSingleClick ? "Click text to play" : "Double-click to play"} · Esc
            clear selection · ⌘/Ctrl+click toggle · Shift+click range · J/K prev/next
          </span>
        </div>
      </div>

      <div className="grid flex-1 grid-cols-1 gap-0 overflow-hidden lg:grid-cols-2">
        <div className="flex flex-col overflow-hidden border-r border-app-border">
          <div className="flex flex-wrap items-center gap-2 border-b border-app-border p-2 text-xs">
            <label className="flex cursor-pointer items-center gap-1.5 text-app-text-muted">
              <input
                type="checkbox"
                checked={allChecked}
                onChange={toggleAllChecked}
                className="rounded border-app-border"
              />
              Select all
            </label>
            {checkedIds.size > 0 && (
              <>
                <span className="text-app-text-subtle">{checkedIds.size} selected</span>
                <LangSelect
                  value={bulkLang}
                  onChange={setBulkLang}
                  className="app-input px-2 py-1 text-xs"
                />
                <button
                  type="button"
                  disabled={bulkLangBusy || mockMode}
                  onClick={() => void applyBulkLang()}
                  className="app-btn-muted px-2 py-1 text-xs"
                >
                  Set language
                </button>
              </>
            )}
          </div>
          <ul className="overflow-y-auto p-2">
          {session.segments.map((seg, index) => {
            const speaker = speakerMap.get(seg.speaker_id);
            const active = seg.id === selectedId;
            const checked = checkedIds.has(seg.id);
            const isPlayingThis = isAudioPlaying && playingSegmentId === seg.id;
            const ignored = seg.status === "ignored";
            return (
              <li key={seg.id} data-segment-id={seg.id}>
                <div
                  onDoubleClick={() => playSelectedSegment(seg)}
                  className={`mb-1 w-full cursor-pointer rounded-lg p-3 text-left transition ${
                    active ? "bg-app-hover ring-1 ring-indigo-500" : "hover:bg-app-muted"
                  } ${checked ? "ring-1 ring-app-border" : ""} ${ignored ? "opacity-55" : ""}`}
                >
                  <div className="mb-1 flex items-center gap-2 text-xs">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleChecked(seg.id)}
                      onClick={(e) => {
                        e.stopPropagation();
                        selectionAnchorRef.current = index;
                      }}
                      className="rounded border-app-border"
                    />
                    <button
                      type="button"
                      aria-label={isPlayingThis ? "Pause segment" : "Play segment"}
                      onClick={(e) => {
                        e.stopPropagation();
                        toggleSegmentPlayback(seg);
                      }}
                      className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full transition ${
                        isPlayingThis
                          ? "bg-indigo-600 text-white hover:bg-indigo-500"
                          : "border border-app-border text-indigo-600 hover:bg-app-hover dark:text-indigo-400"
                      }`}
                    >
                      {isPlayingThis ? (
                        <PauseIcon className="h-3.5 w-3.5" aria-hidden />
                      ) : (
                        <PlayIcon className="ml-0.5 h-3.5 w-3.5" aria-hidden />
                      )}
                    </button>
                    {!readOnly && (
                      <button
                        type="button"
                        aria-label={ignored ? "Un-ignore segment" : "Ignore segment"}
                        title={ignored ? "Un-ignore" : "Ignore"}
                        onClick={(e) => {
                          e.stopPropagation();
                          void toggleIgnoreSegment(seg);
                        }}
                        className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium transition ${
                          ignored
                            ? "bg-slate-300 text-slate-800 hover:bg-slate-200 dark:bg-slate-600 dark:text-slate-100"
                            : "text-app-text-muted hover:bg-app-muted hover:text-app-text"
                        }`}
                      >
                        {ignored ? "Un-ignore" : "Ignore"}
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={(e) => {
                        if (!handleSelectionClick(seg, index, e)) seekToSegment(seg);
                      }}
                      className="flex flex-1 items-center gap-2 text-left"
                    >
                      <span
                        className="inline-block h-2 w-2 rounded-full"
                        style={{ backgroundColor: speaker?.color }}
                      />
                      <span className="font-medium">{speaker?.display_name ?? speaker?.label}</span>
                      <span className="text-app-text-subtle">
                        {seg.start_sec.toFixed(1)}s – {seg.end_sec.toFixed(1)}s
                      </span>
                      <span className="rounded-full bg-app-muted px-1.5 py-0.5 text-app-text-muted">
                        {SEGMENT_LANG_LABELS[seg.lang]}
                      </span>
                      <span className={`ml-auto ${statusBadgeClass(seg.status)}`}>
                        {seg.status}
                      </span>
                      {seg.review_comment?.trim() && (
                        <span className="rounded-full bg-amber-200 px-1.5 py-0.5 text-amber-900 dark:bg-amber-800 dark:text-amber-100">
                          note
                        </span>
                      )}
                    </button>
                  </div>
                  <p
                    onClick={(e) => {
                      if (handleSelectionClick(seg, index, e)) return;
                      if (playOnSingleClick) playSelectedSegment(seg);
                      else seekToSegment(seg);
                    }}
                    className={`select-none outline-none text-sm hover:text-indigo-600 dark:hover:text-indigo-200 ${
                      ignored ? "text-app-text-muted line-through" : "text-app-text"
                    }`}
                  >
                    {seg.text_corrected ?? seg.text_raw}
                  </p>
                </div>
              </li>
            );
          })}
          </ul>
        </div>

        <div className="overflow-y-auto p-4">
          {selected ? (
            <SegmentEditor
              segment={selected}
              canNormalize={
                canNormalize(selected.lang) && !readOnly && selected.status !== "ignored"
              }
              normalizing={normalizing}
              readOnly={readOnly}
              isAdmin={isAdmin}
              isPlaying={isAudioPlaying && playingSegmentId === selected.id}
              onPlayPause={() => toggleSegmentPlayback(selected)}
              onNormalize={() => void handleSegmentNormalize()}
              segmentPreview={segmentPreview}
              onAcceptNormalize={() => void acceptSegmentNormalize()}
              onRejectNormalize={() => setSegmentPreview(null)}
              onChange={(patch) => {
                if (readOnly) return;
                patchSegment(selected.id, patch);
                setSegmentPreview(null);
              }}
              onSave={(seg) => void persistSegment(seg)}
              onToggleIgnore={() => void toggleIgnoreSegment(selected)}
              onSaveReviewComment={(comment) => void saveReviewComment(selected.id, comment)}
            />
          ) : (
            <p className="text-app-text-muted">Select a segment</p>
          )}
          {exportMsg && (
            <p
              className={`mt-4 whitespace-pre-wrap text-sm ${
                exportMsg.includes("Normalization") || exportMsg.includes("503")
                  ? "app-alert-error"
                  : "text-app-text-muted"
              }`}
            >
              {exportMsg}
            </p>
          )}
        </div>
      </div>

      {bulkModal && (
        <NormalizeModal
          title="Normalize all Kreol/mix segments"
          previews={bulkModal}
          applying={normalizing}
          onApply={() => void applyBulkNormalize()}
          onClose={() => setBulkModal(null)}
        />
      )}
    </div>
  );
}

interface SegmentEditorProps {
  segment: Segment;
  canNormalize: boolean;
  normalizing: boolean;
  readOnly: boolean;
  isAdmin: boolean;
  isPlaying: boolean;
  onPlayPause: () => void;
  onNormalize: () => void;
  segmentPreview: NormalizePreview | null;
  onAcceptNormalize: () => void;
  onRejectNormalize: () => void;
  onChange: (patch: Partial<Segment>) => void;
  onSave: (segment: Segment) => void;
  onToggleIgnore: () => void;
  onSaveReviewComment: (comment: string | null) => void;
}

function SegmentEditor({
  segment,
  canNormalize,
  normalizing,
  readOnly,
  isAdmin,
  isPlaying,
  onPlayPause,
  onNormalize,
  segmentPreview,
  onAcceptNormalize,
  onRejectNormalize,
  onChange,
  onSave,
  onToggleIgnore,
  onSaveReviewComment,
}: SegmentEditorProps) {
  const [commentDraft, setCommentDraft] = useState(segment.review_comment ?? "");
  const [commentBusy, setCommentBusy] = useState(false);
  const [showUnknown, setShowUnknown] = useState(false);
  const draftText = segment.text_corrected ?? segment.text_raw ?? "";
  const hintsEnabled =
    canNormalize && !readOnly && segment.status !== "ignored";
  const livePreview = useLortografPreview(
    segment.id,
    draftText,
    segment.lang,
    hintsEnabled,
  );

  useEffect(() => {
    setCommentDraft(segment.review_comment ?? "");
  }, [segment.id, segment.review_comment]);

  const save = () => {
    if (!readOnly) onSave(segment);
  };

  const applyChange = (change: WordChange) => {
    const next =
      draftText.slice(0, change.start) +
      change.normalized +
      draftText.slice(change.end);
    onChange({ text_corrected: next, status: "corrected" });
  };

  const saveComment = async () => {
    setCommentBusy(true);
    try {
      await onSaveReviewComment(commentDraft.trim() || null);
    } finally {
      setCommentBusy(false);
    }
  };

  const ignored = segment.status === "ignored";
  const fieldsLocked = readOnly || ignored;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs text-app-text-muted">
          {segment.start_sec.toFixed(1)}s – {segment.end_sec.toFixed(1)}s
        </p>
        <div className="flex items-center gap-2">
          {!readOnly && (
            <Button
              size="sm"
              variant={ignored ? "solid" : "secondary"}
              tone="slate"
              onClick={onToggleIgnore}
            >
              {ignored ? "Un-ignore" : "Ignore"}
            </Button>
          )}
          <Button
            size="sm"
            variant="primary"
            icon={isPlaying ? PauseIcon : PlayIcon}
            onClick={onPlayPause}
          >
            {isPlaying ? "Pause" : "Play segment"}
          </Button>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="mb-1 block text-xs text-app-text-muted">Language</label>
          <select
            className="app-input w-full disabled:opacity-60"
            value={segment.lang}
            disabled={fieldsLocked}
            onChange={(e) => onChange({ lang: e.target.value as SegmentLang })}
            onBlur={save}
          >
            {SEGMENT_LANGS.map((l) => (
              <option key={l} value={l}>
                {SEGMENT_LANG_LABELS[l]}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs text-app-text-muted">Status</label>
          <select
            className="app-input w-full disabled:opacity-60"
            value={segment.status}
            disabled={readOnly}
            onChange={(e) => {
              const status = e.target.value as SegmentStatus;
              if (status === "validated" && !segmentHasText(segment)) return;
              onChange({ status });
            }}
            onBlur={save}
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div>
        <label className="mb-1 block text-xs text-app-text-muted">Transcript</label>
        {hintsEnabled ? (
          <LortografHints
            value={draftText}
            disabled={fieldsLocked}
            preview={livePreview}
            showUnknown={showUnknown}
            onShowUnknownChange={setShowUnknown}
            onChange={(e) =>
              onChange({ text_corrected: e.target.value, status: "corrected" })
            }
            onBlur={save}
            onApplyChange={applyChange}
            onApplyAll={onNormalize}
            applying={normalizing}
          />
        ) : (
          <textarea
            className="app-input min-h-40 w-full leading-relaxed disabled:opacity-60"
            value={draftText}
            disabled={fieldsLocked}
            onChange={(e) =>
              onChange({ text_corrected: e.target.value, status: "corrected" })
            }
            onBlur={save}
          />
        )}
        {ignored && (
          <p className="mt-1 text-xs text-app-text-muted">
            Ignored segments are excluded from training export.
          </p>
        )}
      </div>

      {segment.review_comment?.trim() && !isAdmin && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-sm text-amber-950 dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-amber-100">
          <p className="mb-1 text-xs font-medium uppercase tracking-wide">Admin comment</p>
          <p>{segment.review_comment}</p>
          {segment.review_comment_by && (
            <p className="mt-1 text-xs text-amber-800 dark:text-amber-300">
              — {segment.review_comment_by}
            </p>
          )}
        </div>
      )}

      {isAdmin && (
        <div>
          <label className="mb-1 block text-xs text-app-text-muted">Segment comment</label>
          <textarea
            className="app-input min-h-20 w-full text-sm"
            placeholder="Explain what is wrong with this segment…"
            value={commentDraft}
            onChange={(e) => setCommentDraft(e.target.value)}
          />
          <div className="mt-2 flex gap-2">
            <Button
              size="sm"
              variant="solid"
              tone="amber"
              disabled={commentBusy}
              onClick={() => void saveComment()}
            >
              Save
            </Button>
            <Button
              size="sm"
              disabled={commentBusy || !commentDraft}
              onClick={() => {
                setCommentDraft("");
                void (async () => {
                  setCommentBusy(true);
                  try {
                    await onSaveReviewComment(null);
                  } finally {
                    setCommentBusy(false);
                  }
                })();
              }}
            >
              Clear
            </Button>
          </div>
        </div>
      )}

      {segmentPreview && (
        <SegmentNormalizePreview
          preview={segmentPreview}
          onAccept={onAcceptNormalize}
          onReject={onRejectNormalize}
        />
      )}
      {segment.model_version_used && (
        <p className="text-xs text-app-text-subtle">ASR model: {segment.model_version_used}</p>
      )}
    </div>
  );
}
