import type { SegmentLang } from "../types";
import { SEGMENT_LANG_LABELS, SEGMENT_LANGS } from "../types";
import { LanguageIcon } from "@heroicons/react/20/solid";
import { PillSelect } from "./ui";

export function LangSelect({
  value,
  onChange,
  id,
  className,
  pill = false,
}: {
  value: SegmentLang;
  onChange: (lang: SegmentLang) => void;
  id?: string;
  className?: string;
  pill?: boolean;
}) {
  if (pill) {
    return (
      <PillSelect
        icon={LanguageIcon}
        label="Language"
        value={value}
        placeholder="Language"
        options={SEGMENT_LANGS.map((lang) => ({
          value: lang,
          label: SEGMENT_LANG_LABELS[lang],
        }))}
        onChange={(v) => {
          if (v) onChange(v as SegmentLang);
        }}
        className={className}
      />
    );
  }

  return (
    <select
      id={id}
      value={value}
      onChange={(e) => onChange(e.target.value as SegmentLang)}
      className={className ?? "app-input"}
    >
      {SEGMENT_LANGS.map((lang) => (
        <option key={lang} value={lang}>
          {SEGMENT_LANG_LABELS[lang]}
        </option>
      ))}
    </select>
  );
}
