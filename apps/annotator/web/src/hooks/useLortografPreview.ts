import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { NormalizePreview, SegmentLang } from "../types";

export function useLortografPreview(
  segmentId: number | null,
  draftText: string,
  lang: SegmentLang,
  enabled: boolean,
): NormalizePreview | null {
  const [preview, setPreview] = useState<NormalizePreview | null>(null);

  useEffect(() => {
    if (!enabled || segmentId == null || !["kreol", "mix"].includes(lang)) {
      setPreview(null);
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      void api
        .normalizeSegment(segmentId, false, draftText)
        .then((p) => {
          if (!cancelled) setPreview(p);
        })
        .catch(() => {
          if (!cancelled) setPreview(null);
        });
    }, 400);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [segmentId, draftText, lang, enabled]);

  return preview;
}
