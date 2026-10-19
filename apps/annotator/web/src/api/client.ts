import type {
  AuditRow,
  AuditRule,
  BulkNormalizeResult,
  CatalogSampleResult,
  Category,
  EditorSession,
  ExportCheckResult,
  LexiconEntry,
  LexiconKind,
  LexiconOrigin,
  LexiconSuggestion,
  ModelVersion,
  NormalizePreview,
  ReplaceApplyResult,
  ReplacePreviewRow,
  ReviewStatus,
  RevisionBatch,
  RollbackResult,
  SearchHit,
  SearchMode,
  Segment,
  SegmentFilterParams,
  SegmentLang,
  SegmentStatus,
  Source,
  SourceListResponse,
  Speaker,
  SystemAlert,
  User,
  UserDeleteResult,
  UserRole,
  UserTimeEvent,
  PaymentPeriod,
  WaveformPeaks,
  WordCluster,
  WordStat,
} from "../types";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function readErrorMessage(res: Response): Promise<string> {
  const text = await res.text();
  try {
    const body = JSON.parse(text) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) {
      return body.detail
        .map((item) =>
          typeof item === "object" && item && "msg" in item
            ? String((item as { msg: string }).msg)
            : JSON.stringify(item),
        )
        .join("; ");
    }
  } catch {
    /* keep raw body */
  }
  return text || res.statusText;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timeoutMs = 15_000;
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  let res: Response;
  try {
    res = await fetch(path, {
      ...init,
      credentials: "include",
      signal: init?.signal ?? controller.signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(0, `Request timed out: ${path}`);
    }
    throw err;
  } finally {
    window.clearTimeout(timer);
  }
  if (res.status === 401 && !path.startsWith("/api/auth/")) {
    if (window.location.pathname !== "/login") {
      window.location.assign("/login");
    }
    throw new ApiError(401, "Not authenticated");
  }
  if (!res.ok) {
    throw new ApiError(res.status, await readErrorMessage(res));
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}

export const api = {
  login: (email: string, password: string) =>
    request<User>("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    }),

  logout: () => request<{ ok: boolean }>("/api/auth/logout", { method: "POST" }),

  me: () => request<User>("/api/auth/me"),

  listUsers: () => request<User[]>("/api/users"),

  createUser: (data: { email: string; password: string; role: UserRole }) =>
    request<User>("/api/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),

  updateUser: (
    id: number,
    data: Partial<{
      email: string;
      role: UserRole;
      is_active: boolean;
      password: string;
      hourly_rate_mur: number;
    }>,
  ) =>
    request<User>(`/api/users/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),

  deleteUser: (id: number) =>
    request<UserDeleteResult>(`/api/users/${id}`, { method: "DELETE" }),

  restoreUser: (id: number) =>
    request<User>(`/api/users/${id}/restore`, { method: "POST" }),

  listUserTimeEvents: (id: number) =>
    request<UserTimeEvent[]>(`/api/users/${id}/time-events`),

  listPaymentPeriods: (id: number) =>
    request<PaymentPeriod[]>(`/api/users/${id}/payment-periods`),

  resetUserTime: (id: number, note?: string) =>
    request<User>(`/api/users/${id}/time-reset`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ note: note || null }),
    }),

  rollbackUserTime: (id: number) =>
    request<User>(`/api/users/${id}/time-rollback`, { method: "POST" }),

  listSources: (assignedTo?: string) => {
    const q =
      assignedTo != null && assignedTo !== ""
        ? `?assigned_to=${encodeURIComponent(assignedTo)}`
        : "";
    return request<SourceListResponse>(`/api/sources${q}`);
  },

  listCategories: () => request<Category[]>("/api/categories"),

  createCategory: (slug: string, label: string) =>
    request<Category>("/api/categories", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slug, label }),
    }),

  setSourceCategory: (sourceId: number, category_id: number | null) =>
    request<Source>(`/api/sources/${sourceId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ category_id }),
    }),

  setSourceAssignment: (sourceId: number, assigned_to_user_id: number | null) =>
    request<Source>(`/api/sources/${sourceId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ assigned_to_user_id }),
    }),

  claimSource: (sourceId: number, userId: number) =>
    request<Source>(`/api/sources/${sourceId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ assigned_to_user_id: userId }),
    }),

  promoteSources: (source_ids: number[]) =>
    request<Source[]>("/api/sources/promote", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source_ids }),
    }),

  catalogSample: (data: {
    target_hours: number;
    weights: Record<string, number>;
    source_ids?: number[];
  }) =>
    request<CatalogSampleResult>("/api/sources/catalog-sample", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),

  setReviewStatus: (sourceId: number, status: ReviewStatus, note?: string) =>
    request<Source>(`/api/sources/${sourceId}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status, note: note || null }),
    }),

  setSegmentReviewComment: (segmentId: number, comment: string | null) =>
    request<Segment>(`/api/segments/${segmentId}/review-comment`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ comment }),
    }),

  cancelSource: (sourceId: number) =>
    request<Source>(`/api/sources/${sourceId}/cancel`, { method: "POST" }),

  deleteSource: (sourceId: number) =>
    request<void>(`/api/sources/${sourceId}`, { method: "DELETE" }),

  retranscribeSource: (sourceId: number) =>
    request<Source>(`/api/sources/${sourceId}/retranscribe`, { method: "POST" }),

  resumeSource: (sourceId: number) =>
    request<Source>(`/api/sources/${sourceId}/resume`, { method: "POST" }),

  createYouTube: (
    youtube_url: string,
    options?: { title?: string; license_notes?: string; default_lang?: SegmentLang },
  ) =>
    request<Source>("/api/sources/youtube", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        youtube_url,
        title: options?.title,
        license_notes: options?.license_notes,
        default_lang: options?.default_lang ?? "mix",
      }),
    }),

  uploadFile: async (
    file: File,
    options?: { title?: string; license_notes?: string; default_lang?: SegmentLang },
  ) => {
    const form = new FormData();
    form.append("file", file);
    if (options?.title) form.append("title", options.title);
    if (options?.license_notes) form.append("license_notes", options.license_notes);
    form.append("default_lang", options?.default_lang ?? "mix");
    return request<Source>("/api/sources/upload", { method: "POST", body: form });
  },

  getSession: (sourceId: number) =>
    request<EditorSession>(`/api/sources/${sourceId}/session`),

  getPeaks: (sourceId: number) =>
    request<WaveformPeaks>(`/api/sources/${sourceId}/peaks`),

  updateSegment: (
    id: number,
    data: Partial<{
      text_corrected: string;
      lang: SegmentLang;
      status: SegmentStatus;
      annotator: string;
    }>,
  ) =>
    request<Segment>(`/api/segments/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),

  bulkUpdateSegmentLang: (sourceId: number, segmentIds: number[], lang: SegmentLang) =>
    request<Segment[]>(`/api/sources/${sourceId}/segments/lang`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ segment_ids: segmentIds, lang }),
    }),

  updateSpeaker: (id: number, data: Partial<{ display_name: string; color: string }>) =>
    request<Speaker>(`/api/speakers/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),

  exportSource: (sourceId: number) =>
    request<{
      jsonl_path: string;
      wav_count: number;
      segment_count: number;
      normalization_warnings: string[];
    }>(`/api/sources/${sourceId}/export`, { method: "POST" }),

  exportCheck: (sourceId: number) =>
    request<ExportCheckResult>(`/api/sources/${sourceId}/export-check`),

  normalizeSegment: (segmentId: number, apply: boolean, text?: string) =>
    request<NormalizePreview>(`/api/segments/${segmentId}/normalize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ apply, ...(text !== undefined ? { text } : {}) }),
    }),

  normalizeSource: (sourceId: number, apply: boolean) =>
    request<BulkNormalizeResult>(`/api/sources/${sourceId}/normalize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ apply }),
    }),

  getConfig: () =>
    request<{
      whisper_model: string;
      enable_diarization: boolean;
      hf_token_configured: boolean;
      diarization_ready: boolean;
      worker_alive: boolean;
      worker_last_seen: string | null;
      alerts: SystemAlert[];
    }>("/api/config"),

  listModels: () => request<ModelVersion[]>("/api/models"),

  activateModel: (name: string) =>
    request<ModelVersion>("/api/models/current", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }),

  registerModel: (name: string, hf_repo: string, make_current = true) =>
    request<ModelVersion>("/api/models", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, hf_repo, make_current }),
    }),

  markFrozenTest: (sourceId: number) =>
    request<{ source_id: number; segment_count: number }>(
      `/api/sources/${sourceId}/mark-frozen-test`,
      { method: "POST" },
    ),

  exportAll: () =>
    request<{ jsonl_path: string; wav_count: number; segment_count: number }>(
      "/api/export/all",
      { method: "POST" },
    ),

  // --- Cleanup / lexicon ---

  cleanupAuditRules: () => request<AuditRule[]>("/api/cleanup/audit/rules"),

  cleanupAudit: (
    params: SegmentFilterParams & {
      rule?: string;
      max_sec?: number;
      min_chars_per_sec?: number;
      include_kept?: boolean;
    } = {},
  ) => {
    const q = new URLSearchParams();
    appendFilterParams(q, params);
    if (params.rule) q.set("rule", params.rule);
    if (params.max_sec != null) q.set("max_sec", String(params.max_sec));
    if (params.min_chars_per_sec != null) {
      q.set("min_chars_per_sec", String(params.min_chars_per_sec));
    }
    if (params.include_kept) q.set("include_kept", "true");
    return request<AuditRow[]>(`/api/cleanup/audit?${q}`);
  },

  cleanupKeep: (rule_id: string, segment_ids: number[]) =>
    request<{ count: number }>("/api/cleanup/audit/keep", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rule_id, segment_ids }),
    }),

  cleanupUnkeep: (rule_id: string, segment_ids: number[]) =>
    request<{ count: number }>("/api/cleanup/audit/keep", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rule_id, segment_ids }),
    }),

  cleanupIgnore: (segment_ids: number[]) =>
    request<{ count: number }>("/api/cleanup/segments/ignore", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ segment_ids }),
    }),

  cleanupVocabulary: (
    params: SegmentFilterParams & {
      min_count?: number;
      lexicon_status?: string;
      q?: string;
    } = {},
  ) => {
    const q = new URLSearchParams();
    appendFilterParams(q, params);
    if (params.min_count != null) q.set("min_count", String(params.min_count));
    if (params.lexicon_status) q.set("lexicon_status", params.lexicon_status);
    if (params.q) q.set("q", params.q);
    return request<WordStat[]>(`/api/cleanup/vocabulary?${q}`);
  },

  cleanupVocabularyClusters: (
    params: SegmentFilterParams & { min_size?: number } = {},
  ) => {
    const q = new URLSearchParams();
    appendFilterParams(q, params);
    if (params.min_size != null) q.set("min_size", String(params.min_size));
    return request<WordCluster[]>(`/api/cleanup/vocabulary/clusters?${q}`);
  },

  cleanupWordOccurrences: (
    word: string,
    params: SegmentFilterParams & { limit?: number } = {},
  ) => {
    const q = new URLSearchParams();
    appendFilterParams(q, params);
    if (params.limit != null) q.set("limit", String(params.limit));
    return request<SearchHit[]>(
      `/api/cleanup/vocabulary/${encodeURIComponent(word)}/occurrences?${q}`,
    );
  },

  cleanupSearch: (
    body: SegmentFilterParams & {
      query: string;
      mode?: SearchMode;
      case_sensitive?: boolean;
      limit?: number;
    },
  ) =>
    request<SearchHit[]>("/api/cleanup/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(filterBody(body)),
    }),

  cleanupReplacePreview: (
    body: SegmentFilterParams & {
      query: string;
      replacement: string;
      mode?: SearchMode;
      case_sensitive?: boolean;
      limit?: number;
    },
  ) =>
    request<ReplacePreviewRow[]>("/api/cleanup/replace/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(filterBody(body)),
    }),

  cleanupReplaceApply: (body: {
    query: string;
    replacement: string;
    mode?: SearchMode;
    case_sensitive?: boolean;
    items: {
      segment_id: number;
      text_before?: string;
      match_indexes?: number[];
    }[];
  }) =>
    request<ReplaceApplyResult>("/api/cleanup/replace/apply", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  cleanupRevisionBatches: () =>
    request<RevisionBatch[]>("/api/cleanup/revisions/batches"),

  cleanupRollback: (batchId: string) =>
    request<RollbackResult>(
      `/api/cleanup/revisions/batches/${batchId}/rollback`,
      { method: "POST" },
    ),

  lexiconList: (params: {
    kind?: LexiconKind;
    origin?: LexiconOrigin;
    q?: string;
    limit?: number;
    offset?: number;
  } = {}) => {
    const q = new URLSearchParams();
    if (params.kind) q.set("kind", params.kind);
    if (params.origin) q.set("origin", params.origin);
    if (params.q) q.set("q", params.q);
    if (params.limit != null) q.set("limit", String(params.limit));
    if (params.offset != null) q.set("offset", String(params.offset));
    return request<LexiconEntry[]>(`/api/lexicon/entries?${q}`);
  },

  lexiconCreate: (body: {
    word: string;
    kind: LexiconKind;
    canonical?: string | null;
    origin?: LexiconOrigin;
    note?: string | null;
  }) =>
    request<LexiconEntry>("/api/lexicon/entries", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  lexiconUpdate: (
    id: number,
    body: Partial<{
      word: string;
      kind: LexiconKind;
      canonical: string | null;
      origin: LexiconOrigin;
      note: string | null;
    }>,
  ) =>
    request<LexiconEntry>(`/api/lexicon/entries/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  lexiconDelete: (id: number) =>
    request<void>(`/api/lexicon/entries/${id}`, { method: "DELETE" }),

  lexiconImport: (text: string, origin: LexiconOrigin = "manual") =>
    request<{ added: number; updated: number }>("/api/lexicon/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, origin }),
    }),

  lexiconExport: async () => {
    const res = await fetch("/api/lexicon/export", { credentials: "include" });
    if (!res.ok) throw new ApiError(res.status, await res.text());
    return res.text();
  },

  lexiconSuggestions: (min_count = 3) =>
    request<LexiconSuggestion[]>(
      `/api/lexicon/suggestions?min_count=${min_count}`,
    ),
};

function appendFilterParams(q: URLSearchParams, params: SegmentFilterParams) {
  if (params.source_id != null) q.set("source_id", String(params.source_id));
  if (params.category_id != null) q.set("category_id", String(params.category_id));
  for (const v of params.lang ?? []) q.append("lang", v);
  for (const v of params.status ?? []) q.append("status", v);
  for (const v of params.review_status ?? []) q.append("review_status", v);
  for (const v of params.split ?? []) q.append("split", v);
  if (params.include_validated_sources) q.set("include_validated_sources", "true");
}

function filterBody<T extends SegmentFilterParams>(body: T): T & Record<string, unknown> {
  const out = { ...body } as T & Record<string, unknown>;
  if (out.source_id == null) delete out.source_id;
  if (out.category_id == null) delete out.category_id;
  return out;
}
