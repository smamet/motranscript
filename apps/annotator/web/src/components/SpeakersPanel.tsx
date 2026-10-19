import type { Segment, Speaker } from "../types";

export function SpeakersPanel({
  speakers,
  segments,
  onRename,
  onSave,
}: {
  speakers: Speaker[];
  segments: Segment[];
  mockMode?: boolean;
  onRename: (speakerId: number, displayName: string) => void;
  onSave: (speakerId: number) => void;
}) {
  if (speakers.length === 0) return null;

  const counts = new Map<number, number>();
  for (const seg of segments) {
    counts.set(seg.speaker_id, (counts.get(seg.speaker_id) ?? 0) + 1);
  }

  return (
    <section className="border-b border-app-border px-4 py-3">
      <h2 className="mb-2 text-xs font-medium uppercase tracking-wide text-app-text-subtle">Speakers</h2>
      <ul className="flex flex-wrap gap-2">
        {speakers.map((speaker) => (
          <li
            key={speaker.id}
            className="flex min-w-[12rem] flex-1 items-center gap-2 rounded-md border border-app-border bg-app-muted px-3 py-2"
          >
            <span
              className="h-3 w-3 shrink-0 rounded-full"
              style={{ backgroundColor: speaker.color }}
              title={speaker.label}
            />
            <div className="min-w-0 flex-1">
              <p className="truncate text-[10px] text-app-text-subtle">{speaker.label}</p>
              <input
                className="app-input w-full px-2 py-1"
                value={speaker.display_name ?? ""}
                placeholder={speaker.label}
                onChange={(e) => onRename(speaker.id, e.target.value)}
                onBlur={() => onSave(speaker.id)}
              />
            </div>
            <span className="shrink-0 text-xs text-app-text-subtle">
              {counts.get(speaker.id) ?? 0} seg
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
