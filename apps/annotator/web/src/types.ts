export type SourceType = "youtube" | "upload";
export type SourceStatus =
  | "pending"
  | "processing"
  | "ready"
  | "failed"
  | "cancelled"
  | "downloaded";
export type SegmentLang = "kreol" | "fr" | "en" | "mix";
export type ReviewStatus = "todo" | "done" | "validated";
export type SourcesTab = "downloaded" | ReviewStatus;

export const SEGMENT_LANGS: SegmentLang[] = ["kreol", "fr", "en", "mix"];

export const SEGMENT_LANG_LABELS: Record<SegmentLang, string> = {
  kreol: "Kreol",
  fr: "French",
  en: "English",
  mix: "Mix (auto)",
};

export const REVIEW_TABS: { id: ReviewStatus; label: string }[] = [
  { id: "todo", label: "To do" },
  { id: "done", label: "Done" },
  { id: "validated", label: "Validated" },
];

export const ADMIN_TABS: { id: SourcesTab; label: string }[] = [
  { id: "downloaded", label: "Downloaded" },
  ...REVIEW_TABS,
];

export type SegmentStatus = "raw" | "corrected" | "validated" | "ignored";
export type SegmentSplit = "train" | "test";

export interface Category {
  id: number;
  slug: string;
  label: string;
}

export interface Speaker {
  id: number;
  source_id: number;
  label: string;
  display_name: string | null;
  color: string;
}

export interface Segment {
  id: number;
  source_id: number;
  speaker_id: number;
  start_sec: number;
  end_sec: number;
  audio_path: string | null;
  text_raw: string | null;
  text_corrected: string | null;
  lang: SegmentLang;
  status: SegmentStatus;
  split: SegmentSplit;
  model_version_used: string | null;
  annotator: string | null;
  review_comment?: string | null;
  review_comment_by?: string | null;
}

export interface Source {
  id: number;
  source_type: SourceType;
  source_url: string | null;
  original_filename: string | null;
  title: string | null;
  duration_sec: number | null;
  license_notes: string | null;
  default_lang: SegmentLang;
  audio_path: string | null;
  status: SourceStatus;
  error: string | null;
  created_at: string;
  review_status?: ReviewStatus;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  review_note?: string | null;
  assigned_to_user_id?: number | null;
  assigned_to_email?: string | null;
  category?: Category | null;
  jobs?: Job[];
}

export interface Job {
  id: number;
  source_id: number;
  job_type: "ingest" | "transcribe";
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  progress: number;
  error: string | null;
}

export interface SystemAlert {
  id: string;
  severity: "error" | "warning" | "info";
  message: string;
  hint?: string | null;
}

export interface EditorSession {
  source: Source;
  speakers: Speaker[];
  segments: Segment[];
  audio_url: string;
  alerts?: SystemAlert[];
  pipeline_meta?: SourceListItem["pipeline_meta"];
}

export interface WaveformPeaks {
  version: number;
  duration: number;
  peaks: number[][];
}

export interface PipelinePhase {
  id: string;
  label: string;
  status: "pending" | "running" | "completed" | "failed" | "skipped" | "cancelled";
  progress: number | null;
  detail: string | null;
}

export interface SourcePipeline {
  overall_progress: number;
  current_label: string;
  phases: PipelinePhase[];
  can_cancel: boolean;
  can_delete: boolean;
  error: string | null;
  queue_position: number | null;
  restart_note: string;
  diarization_status?: string | null;
  diarization_error?: string | null;
  speaker_count?: number | null;
}

export interface SourceListItem {
  id: number;
  source_type: SourceType;
  title: string | null;
  original_filename: string | null;
  duration_sec: number | null;
  net_audio_sec?: number;
  status: SourceStatus;
  error: string | null;
  created_at: string;
  pipeline: SourcePipeline;
  pipeline_meta?: {
    diarization_status?: string;
    diarization_error?: string | null;
    speaker_count?: number;
    asr_detected_lang?: string | null;
  } | null;
  alerts?: SystemAlert[];
  review_status: ReviewStatus;
  review_note?: string | null;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  partial: boolean;
  touched_count: number;
  segment_count: number;
  comment_count: number;
  can_mark_done: boolean;
  category?: Category | null;
  source_url?: string | null;
  assigned_to_user_id?: number | null;
  assigned_to_email?: string | null;
}

export interface ReviewHours {
  todo: number;
  done: number;
  validated: number;
  downloaded: number;
  downloaded_by_category: Record<string, number>;
}

export interface SourceListResponse {
  sources: SourceListItem[];
  hours: ReviewHours;
}

export interface CatalogSampleResult {
  source_ids: number[];
  seconds_by_category: Record<string, number>;
  total_seconds: number;
}

export interface ModelVersion {
  id: number;
  name: string;
  hf_repo: string | null;
  is_current: boolean;
  metrics_json: Record<string, unknown> | null;
}

export interface WordChange {
  original: string;
  normalized: string;
  start: number;
  end: number;
}

export interface NormalizePreview {
  segment_id: number;
  original: string;
  proposed: string;
  changed: boolean;
  changes: WordChange[];
  unknown_tokens: string[];
}

export interface BulkNormalizeResult {
  previews: NormalizePreview[];
  applied_count: number;
}

export interface ExportCheckResult {
  validated_count: number;
  needs_normalization_count: number;
  segment_ids: number[];
}

export type LexiconKind = "official" | "alias" | "skip";
export type LexiconOrigin = "pdf" | "manual" | "corpus";
export type SearchMode = "word" | "substring" | "regex";

export interface SegmentFilterParams {
  source_id?: number | null;
  category_id?: number | null;
  lang?: SegmentLang[];
  status?: SegmentStatus[];
  review_status?: ReviewStatus[];
  split?: SegmentSplit[];
  include_validated_sources?: boolean;
}

export interface LexiconEntry {
  id: number;
  word: string;
  kind: LexiconKind;
  canonical: string | null;
  origin: LexiconOrigin;
  note: string | null;
  created_at?: string | null;
}

export interface LexiconSuggestion {
  word: string;
  count: number;
}

export interface AuditRule {
  id: string;
  label: string;
}

export interface AuditRow {
  segment_id: number;
  source_id: number;
  source_title: string | null;
  review_status: ReviewStatus;
  status: SegmentStatus;
  lang: SegmentLang;
  start_sec: number;
  end_sec: number;
  duration_sec: number;
  text: string;
  kept: boolean;
  chars_per_sec?: number | null;
  char_count?: number | null;
}

export interface MatchSpan {
  start: number;
  end: number;
}

export interface SearchHit {
  segment_id: number;
  source_id: number;
  source_title: string | null;
  review_status: ReviewStatus;
  status: SegmentStatus;
  lang?: SegmentLang | null;
  text: string;
  matches: MatchSpan[];
}

export interface WordStat {
  word: string;
  count: number;
  segment_count: number;
  lang_counts: Record<string, number>;
  lexicon_status: string;
  canonical: string | null;
  cluster_key: string;
}

export interface WordCluster {
  cluster_key: string;
  total_count: number;
  words: WordStat[];
}

export interface ReplacePreviewRow {
  segment_id: number;
  source_id: number;
  source_title: string | null;
  review_status: ReviewStatus;
  status: SegmentStatus;
  text_before: string;
  text_after: string;
  matches: MatchSpan[];
}

export interface ReplaceApplyResult {
  batch_id: string;
  applied: number;
  skipped: { segment_id: number; reason: string; locked_by?: string }[];
}

export interface RevisionBatch {
  batch_id: string;
  created_at: string;
  count: number;
  query: string | null;
  replacement: string | null;
  created_by_email: string | null;
}

export interface RollbackResult {
  batch_id: string;
  restored: number;
  skipped: { segment_id: number; reason: string }[];
}

export type UserRole = "admin" | "operator";

export interface User {
  id: number;
  email: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  deleted_at?: string | null;
  hourly_rate_mur?: number;
  in_progress_audio_sec?: number;
  in_progress_hours?: number;
  in_progress_mur?: number;
  done_audio_sec?: number;
  done_hours?: number;
  done_mur?: number;
  validated_audio_sec?: number;
  validated_hours?: number;
  owed_mur?: number;
  can_rollback?: boolean;
  last_event_kind?: string | null;
  last_event_at?: string | null;
  last_period_kind?: string | null;
  last_period_at?: string | null;
}

export interface UserDeleteResult {
  mode: "hard" | "soft";
  user: User | null;
}

export interface UserTimeEvent {
  id: number;
  user_id: number;
  kind: string;
  bucket: string | null;
  audio_sec: number;
  source_id: number | null;
  related_event_id: number | null;
  created_by_user_id: number | null;
  created_at: string;
}

export interface PaymentPeriod {
  id: number;
  user_id: number;
  reset_event_id: number;
  audio_sec: number;
  hourly_rate_mur: number;
  amount_mur: number;
  period_started_at: string | null;
  closed_at: string;
  created_by_user_id: number | null;
  note: string | null;
  rolled_back_at: string | null;
  created_at: string;
}

export function formatHours(seconds: number): string {
  const totalMin = Math.round(seconds / 60);
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  if (h <= 0) return `${m} m`;
  if (m === 0) return `${h} h`;
  return `${h} h ${m}`;
}

export function formatMur(amount: number): string {
  return `Rs ${amount.toFixed(2)}`;
}

/** True when ASR steps are not skipped — i.e. promoted out of catalog. */
export function hasActiveTranscribe(source: SourceListItem): boolean {
  const phases = source.pipeline?.phases ?? [];
  const asr = phases.find((p) => p.id === "asr");
  if (!asr) return source.status !== "downloaded";
  return asr.status !== "skipped";
}
