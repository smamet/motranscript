import { PlayIcon, StopIcon } from "@heroicons/react/20/solid";
import { useEffect, useRef, useState } from "react";
import { Button } from "../ui";

export function SegmentClipPlayer({ segmentId }: { segmentId: number }) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    return () => {
      audioRef.current?.pause();
    };
  }, [segmentId]);

  async function toggle() {
    if (playing && audioRef.current) {
      audioRef.current.pause();
      setPlaying(false);
      return;
    }
    const audio = new Audio(`/api/segments/${segmentId}/audio`);
    audioRef.current = audio;
    audio.onended = () => setPlaying(false);
    audio.onerror = () => setPlaying(false);
    try {
      await audio.play();
      setPlaying(true);
    } catch {
      setPlaying(false);
    }
  }

  return (
    <Button
      size="sm"
      variant="muted"
      onClick={() => void toggle()}
      title={playing ? "Stop" : "Play clip"}
    >
      {playing ? (
        <StopIcon className="h-4 w-4" />
      ) : (
        <PlayIcon className="h-4 w-4" />
      )}
    </Button>
  );
}
