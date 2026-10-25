import { clearSession, getRefreshToken, getToken, setAccessToken } from "../lib/auth";

const BASE = "/api/v1";

/** Temporal workflow lifecycle, as returned by GET /investigations/{id}. */
export type WorkflowStatus =
  | "RUNNING"
  | "COMPLETED"
  | "FAILED"
  | "CANCELED"
  | "TERMINATED"
  | "TIMED_OUT"
  | "UNKNOWN";

/** SafeNet KZ uses three levels; CRITICAL only appears on rows scored by the old engine. */
export type ThreatLevel = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export const LEVEL_RU: Record<string, string> = {
  LOW: "низкий", MEDIUM: "средний", HIGH: "высокий", CRITICAL: "высокий",
};

export type Track = "lottery" | "casino" | "pyramid" | "";

export const TRACK_RU: Record<string, string> = {
  lottery: "Платный розыгрыш",
  casino: "Скрытое казино",
  pyramid: "Финансовая пирамида",
  "": "Без трека",
  none: "Без трека",
};

export const SOURCE_RU: Record<string, string> = {
  text: "текст поста", caption: "подпись", transcript: "речь (транскрипт)", ocr: "текст на изображении",
  stream: "транскрипт эфира", chat: "сообщение чата", llm: "семантический анализ (LLM)",
  vision: "визуальные теги", group: "анализ группы", model: "обучаемая модель",
};

export const VIEW_RU: Record<string, string> = {
  deobf: "скрыто подменой символов", collapsed: "скрыто разрядкой букв",
  translit: "написано транслитом", emoji: "закодировано эмодзи", numwords: "числа прописью",
};

export const LANG_RU: Record<string, string> = {
  ru: "русский", kk: "казахский", mixed: "рус+каз", translit: "транслит", unknown: "—", "": "—",
};

export interface SignalQuote {
  text: string;
  source: string;
  view: string;
}

/** One detected «признак» with verbatim evidence. */
export interface SafeNetSignal {
  signal: string;
  label: string;
  track: string;
  strength: number;
  note: string;
  quotes: SignalQuote[];
}

/** A line of the explainable breakdown (signal contribution or a gate/mitigation adjustment). */
export interface BreakdownLine {
  factor: string;
  label?: string;
  track?: string;
  kind?: "signal" | "adjustment";
  weight?: number;
  strength?: number;
  contribution: number;
  note?: string;
  detail?: string;
  evidence_ids?: string[];
  quotes?: SignalQuote[];
  without?: number;          // overall score if this sign were absent («что если»)
  level_without?: ThreatLevel;
}

export interface SafeNetRisk {
  score: number;
  threat_level: ThreatLevel;
  level_ru?: string;
  breakdown: BreakdownLine[];
  recommendation: string;
  track?: Track;
  track_label?: string;
  tracks?: Record<string, { score: number; threat_level: ThreatLevel; label: string }>;
  signals?: SafeNetSignal[];
  multi_track?: string[];
  language?: string;
  disclaimer?: string;
}

export interface ChatAnalysis {
  group: string;
  platform: string;
  messages: number;
  authors: number;
  risk: SafeNetRisk;
  members: { author: string; messages: number; risky_messages: number; money_signals: number; payout_reviews: number; role: string }[];
  top_messages: { index: number; author: string; ts: string; text: string; score: number; level: ThreatLevel; track: string; signals: string[] }[];
  flagged_messages: number;
  templates: { size: number; authors: string[]; example: string }[];
  identifiers: Record<string, string[]>;
  languages: Record<string, number>;
  organizer: string;
  curators: string[];
  sha256?: string;
  content_risk_id?: number;
}

export interface MetricBlock {
  precision: number | null;
  recall: number | null;
  f1: number | null;
  fpr: number | null;
}

export interface MetricsReport {
  dataset: string;
  title: string;
  mode?: string;
  training_set?: boolean;
  available: { id: string; title: string }[];
  n: number;
  positives: number;
  negatives: number;
  hard_negatives: number;
  threshold: number;
  binary: MetricBlock & { tp: number; fp: number; fn: number; tn: number; accuracy: number | null };
  per_track: Record<string, MetricBlock & { support: number; tp: number; predicted: number; false_positives_on_clean: number }>;
  hard_negative_fpr: number | null;
  high_level: { recall: number | null; fpr: number | null };
  recall_by_language: Record<string, { n: number; recall: number | null }>;
  fpr_by_language: Record<string, { n: number; fpr: number | null }>;
  recall_by_obfuscation: Record<string, { n: number; recall: number | null }>;
  recall_by_kind: Record<string, { n: number; recall: number | null }>;
  confusion: Record<string, Record<string, number>>;
  errors: { id: string; type: string; track: string; pred_track: string; score: number; level: string; text: string; signals: string[]; category: string }[];
  throughput: { items: number; seconds: number; items_per_second: number | null; ms_per_item: number | null };
}

export interface Methodology {
  tracks: Record<string, string>;
  signals: { id: string; track: string; label: string; weight: number; role: string; description: string; patterns: number }[];
  weights: Record<string, Record<string, number>>;
  levels: { HIGH: number; MEDIUM: number };
  flag_threshold: number;
  extra: Record<string, string>;
  disclaimer: string;
  gates: string[];
}

export interface Campaign {
  id: string;
  accounts: { account: string; source: string; materials: number; max_score: number }[];
  materials: number;
  flagged: number;
  total_views: number;
  max_score: number;
  avg_score: number;
  track: string;
  tracks: Record<string, number>;
  platforms: string[];
  shared: { kind: string; value: string; accounts: string[] }[];
  first_seen: string | null;
  last_seen: string | null;
  top_materials: { content_risk_id: number; author: string; score: number; threat_level: ThreatLevel; text: string }[];
  priority: number;
}

export interface BulkResult {
  rows: number;
  flagged: number;
  persisted: number;
  seconds: number;
  items_per_second: number | null;
  by_level: Record<string, number>;
  by_track: Record<string, number>;
  languages: Record<string, number>;
  top: { row: number; author: string; score: number; threat_level: ThreatLevel; track: string; text: string; signals: string[] }[];
}

export interface Insights {
  emerging: {
    flagged_materials: number;
    clean_materials: number;
    terms: { term: string; flagged_materials: number; clean_materials: number; accounts: number; lift: number; track: string; example: string }[];
  };
  feedback: {
    decisions: number; confirmed: number; dismissed: number; precision: number | null;
    signals: { signal: string; label: string; decisions: number; confirmed: number; dismissed: number; precision: number | null }[];
  };
}

export interface SafeNetSummary {
  by_track: Record<string, Record<string, number>>;
  pending_review: number;
}

export interface Report {
  target: string;
  category: string;
  risk_score: number; // 0–100
  threat_level: ThreatLevel;
  findings: string[];
  links: { accounts: number; sites: number; wallets: number };
}

export interface InvestigationReport {
  workflow_id: string;
  status: WorkflowStatus;
  report: Report | null;
}

export interface InvestigationCreated {
  workflow_id: string;
  target: string;
  status: string;
}

export interface GraphNode {
  id: string;
  type: "account" | "infrastructure" | "wallet" | "person";
}
export interface GraphEdge {
  source: string;
  target: string;
  label: string;
}
export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface GraphInsights {
  communities: { community_id: number; members: string[]; size: number }[];
  ringleaders: { id: string; score: number }[];
}

export interface EvidencePackageResult {
  package: { manifest_sha256: string; object: string; [k: string]: unknown };
  markdown: string;
}

export interface Reach {
  views: number;
  likes: number;
  comments: number;
  shares: number;
}

export interface AnalysisResult {
  sha256: string;
  author: string;
  source: string;
  kind?: string;
  track?: Track;
  language?: string;
  caption?: string;
  text: string;
  transcript?: string;
  ocr_text?: string;
  tags: string[];
  claims: Record<string, boolean>;
  identifiers: {
    telegram: string[]; wallets: string[]; domains: string[];
    phones?: string[]; cards?: string[]; promo_codes?: string[]; short_links?: string[];
  };
  risk: SafeNetRisk;
  reach: Reach;
  priority: number;
  scheme_matches: { content_id: string; score: number; shared: string[] }[];
  content_risk_id?: number;
}

export interface TriageItem {
  id: number;
  target: string;
  score: number;
  threat_level: ThreatLevel;
  recommendation: string;
  disposition: string;
  disposition_by: string | null;
}

export interface RiskFactor {
  factor: string;
  weight?: number;
  strength?: number;
  contribution?: number;
  evidence_ids?: string[];
  note?: string;
}

/** Per-video material in the prioritisation queue (risk-scored content). */
export interface ContentTriageItem {
  id: number;
  content_id: string;
  author: string;
  source: string;
  url: string;
  score: number;
  threat_level: ThreatLevel;
  breakdown: BreakdownLine[];
  recommendation: string;
  reach: Reach;
  priority: number;
  disposition: string;
  disposition_by: string | null;
  track?: string;
  lang?: string;
  caption?: string;
  transcript?: string;
  ocr_text?: string;
  tags?: string[];
}

export interface WatchTarget {
  id: number;
  source: string;
  kind: "account" | "keyword";
  value: string;
  active: boolean;
  last_run_at: string | null;
  interval_seconds: number | null;            // null = uses global default
  effective_interval_seconds: number;         // resolved cadence applied
  video_limit: number | null;                 // null = uses global default
  next_run_at: string | null;
}

/** One runtime-configurable knob from the settings registry. */
export interface AppSettingItem {
  group: string;
  key: string;
  type: "int" | "float" | "bool" | "str";
  label: string;
  help: string;
  min: number | null;
  max: number | null;
  options: string[] | null;
  value: number | string | boolean;
  is_default: boolean;
}

/** A 'new video for a monitored account' alert, surfaced as a toast. */
export interface WatchlistNotification {
  id: number;
  content_id: string;
  author: string;
  source: string;
  url: string;
  score: number | null;
  threat_level: ThreatLevel | null;
  reason: "watched" | "high_risk";
  created_at: string | null;
  read_at: string | null;
}

/** Auto-collection schedule for the watchlist (continuous monitoring). */
export interface MonitoringSchedule {
  enabled: boolean;
  interval_seconds: number;
  last_sweep: number;   // epoch seconds, 0 = never
  next_sweep: number;   // epoch seconds, 0 = disabled
}

export type FlowNodeType = "account" | "wallet" | "exchange" | "counterparty";
export interface MoneyFlow {
  account: string;
  nodes: { id: string; type: FlowNodeType }[];
  edges: { source: string; target: string; label: string; chain?: string | null; exchange?: string }[];
  boundary: { reached: string; note: string };
}

/** Hard identifiers extracted per video (Telegram channels, wallets, phones, domains). */
export interface VideoIdentifiers {
  telegram: string[];
  wallets: string[];
  phones: string[];
  domains: string[];
}

export interface DossierVideo {
  content_id: string;
  url: string;
  source: string;
  score: number | null;
  threat_level: ThreatLevel | null;
  priority: number;
  disposition: string;
  reach: Partial<Reach>;
  identifiers: VideoIdentifiers;
  caption?: string;
  transcript: string;
  ocr_text: string;
  tags: string[];
}

export type IdentifierKind = "telegram" | "wallet" | "phone" | "domain";
export interface DossierIdentifier {
  kind: IdentifierKind;
  value: string;
  count: number;          // in how many of the account's videos it appears
  videos: string[];       // content_ids
}

export interface DossierPattern {
  factor: string;
  label?: string;
  videos: number;         // how many videos exhibit this risk factor
  avg_contribution: number;
}

export interface DossierLinkedAccount {
  author: string;
  shared: string[];       // shared hard identifiers (the «same scheme» signal)
}

/** RDAP/WHOIS enrichment for a domain the account advertises. */
export interface DomainWhois {
  domain: string;
  registrar: string | null;
  registered: string | null;
  expires: string | null;
  updated: string | null;
  nameservers: string[];
  status: string[];
  age_days: number | null;
}

/** Full portrait of one target — videos, aggregated identifiers, pattern, links. */
export interface Dossier {
  account: string;
  source: string;
  overall: {
    score: number;
    threat_level: ThreatLevel;
    breakdown: RiskFactor[];
    recommendation: string;
    disposition: string;
  } | null;
  totals: {
    videos: number;
    scored: number;
    avg_score: number | null;
    max_score: number | null;
    total_views: number;
  };
  videos: DossierVideo[];
  identifiers: DossierIdentifier[];
  pattern: DossierPattern[];
  linked_accounts: DossierLinkedAccount[];
  whois: DomainWhois[];
  campaign: DossierCampaign;
}

/** «От видео к сети» — свёртка аккаунта и связанных в одну кампанию с приоритетом. */
export interface DossierCampaign {
  posts: number;
  accounts: number;
  wallets: number;
  telegram: number;
  domains: number;
  phones: number;
  shared_identifiers: string[];
  ringleader: string;
  max_risk: number;
  threat_level: ThreatLevel;
  is_network: boolean;
}

export interface LoginResult {
  access_token: string;
  refresh_token: string;
  token_type: string;
  role: string;
}

/** Try to mint a new access token from the stored refresh token. Returns success. */
async function tryRefresh(): Promise<boolean> {
  const refresh_token = getRefreshToken();
  if (!refresh_token) return false;
  const res = await fetch(`${BASE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token }),
  });
  if (!res.ok) return false;
  const body = (await res.json()) as { access_token: string };
  setAccessToken(body.access_token);
  return true;
}

function authHeaders(extra?: HeadersInit): HeadersInit {
  const token = getToken();
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...extra,
  };
}

async function http<T>(path: string, init?: RequestInit, _retried = false): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: authHeaders(init?.headers),
  });
  if (res.status === 401 && !_retried) {
    // access token likely expired -> refresh once and retry, else drop to login
    if (await tryRefresh()) return http<T>(path, init, true);
    clearSession();
  } else if (res.status === 401) {
    clearSession();
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      /* non-JSON error body — keep the status line */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

/** multipart/form-data POST (file uploads) — the browser sets the boundary header. */
async function multipart<T>(path: string, fd: FormData): Promise<T> {
  const token = getToken();
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: fd,
  });
  if (res.status === 401) clearSession();
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try { const b = await res.json(); if (b?.detail) detail = String(b.detail); } catch { /* keep */ }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const TERMINAL_STATUSES: WorkflowStatus[] = [
  "COMPLETED",
  "FAILED",
  "CANCELED",
  "TERMINATED",
  "TIMED_OUT",
];

export const api = {
  // OAuth2 password flow (form-encoded); TOTP is passed via the client_secret field.
  login: async (username: string, password: string, totp: string): Promise<LoginResult> => {
    const res = await fetch(`${BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ username, password, client_secret: totp }),
    });
    if (!res.ok) {
      let detail = "Invalid credentials";
      try {
        const body = await res.json();
        if (body?.detail) detail = String(body.detail);
      } catch {
        /* keep default */
      }
      throw new Error(detail);
    }
    return res.json() as Promise<LoginResult>;
  },
  openInvestigation: (target: string, requestedBy: string) =>
    http<InvestigationCreated>("/investigations", {
      method: "POST",
      body: JSON.stringify({ target, requested_by: requestedBy }),
    }),
  getInvestigation: (workflowId: string) =>
    http<InvestigationReport>(`/investigations/${encodeURIComponent(workflowId)}`),
  getGraph: (seed: string) => http<GraphData>(`/graph/${encodeURIComponent(seed)}`),
  getInsights: () => http<GraphInsights>("/graph/insights"),
  getEvidencePackage: (workflowId: string) =>
    http<EvidencePackageResult>(`/investigations/${encodeURIComponent(workflowId)}/evidence-package`),
  getMoneyFlow: (account: string) =>
    http<MoneyFlow>(`/graph/money-flow/${encodeURIComponent(account)}`),
  rebuildSchemas: () =>
    http<{ schemas: { schema_id: string; members: string[]; size: number }[]; count: number }>(
      "/graph/schemas/rebuild", { method: "POST" }
    ),
  confirmSamePerson: (account_a: string, account_b: string) =>
    http<{ confirmed: boolean; by: string }>("/graph/same-person", {
      method: "POST",
      body: JSON.stringify({ account_a, account_b }),
    }),
  analyzeUrl: (url: string) =>
    http<AnalysisResult>("/analyze/url", { method: "POST", body: JSON.stringify({ url }) }),
  analyzeFile: (file: File, caption = "", author = ""): Promise<AnalysisResult> => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("caption", caption);
    fd.append("author", author);
    return multipart<AnalysisResult>("/analyze/file", fd);
  },
  analyzeText: (body: { text: string; kind?: string; author?: string; source?: string; url?: string }) =>
    http<AnalysisResult>("/analyze/text", { method: "POST", body: JSON.stringify(body) }),
  analyzeChat: (opts: { file?: File; text?: string; demo?: string }) => {
    const fd = new FormData();
    if (opts.file) fd.append("file", opts.file);
    if (opts.text) fd.append("text", opts.text);
    if (opts.demo) fd.append("demo", opts.demo);
    return multipart<ChatAnalysis>("/analyze/chat", fd);
  },
  getMetrics: (dataset = "blind2", model = true) =>
    http<MetricsReport>(`/safenet/metrics?dataset=${encodeURIComponent(dataset)}&model=${model}`),
  getMethodology: () => http<Methodology>("/safenet/methodology"),
  getSafeNetSummary: () => http<SafeNetSummary>("/safenet/summary"),
  getCampaigns: () => http<Campaign[]>("/safenet/campaigns"),
  getInsights2: () => http<Insights>("/safenet/insights"),
  bulkCheck: (opts: { file?: File; demo?: number; persist?: boolean }) => {
    const fd = new FormData();
    if (opts.file) fd.append("file", opts.file);
    if (opts.demo) fd.append("demo", String(opts.demo));
    fd.append("persist", String(opts.persist ?? true));
    return multipart<BulkResult>("/safenet/bulk", fd);
  },
  getDemoChats: () => http<{ id: string; file: string; title: string }[]>("/safenet/demo-chats"),
  demoSeed: (reset = false) =>
    http<{ posts: number; flagged: number; chats: { name: string; score: number; track: string }[]; graph: boolean }>(
      `/safenet/demo-seed?reset=${reset}`, { method: "POST" }),
  rescore: () => http<{ rescored: number; total: number }>("/safenet/rescore", { method: "POST" }),
  getAccounts: () => http<string[]>("/accounts"),
  getGraphAccounts: () => http<string[]>("/graph/accounts"),
  getDossier: (account: string) =>
    http<Dossier>(`/accounts/${encodeURIComponent(account)}/dossier`),
  discover: (query: string, source = "youtube", limit?: number) =>
    http<{ started: boolean; query: string; source: string; limit: number | string }>(
      "/accounts/discover",
      { method: "POST", body: JSON.stringify({ query, source, ...(limit ? { limit } : {}) }) }
    ),
  collectAccount: (account: string, limit?: number) =>
    http<{ started: boolean; account: string; source: string; limit: number | string }>(
      "/accounts/collect",
      { method: "POST", body: JSON.stringify({ account, ...(limit ? { limit } : {}) }) }
    ),
  checkLicense: (q: string) =>
    http<{ licensed: boolean; matched: string | null; source: string }>(
      `/license/check?q=${encodeURIComponent(q)}`
    ),
  getTriage: () => http<TriageItem[]>("/triage"),
  setDisposition: (id: number, disposition: string) =>
    http<TriageItem>(`/triage/${id}/disposition`, { method: "POST", body: JSON.stringify({ disposition }) }),
  getContentTriage: () => http<ContentTriageItem[]>("/triage/content"),
  setContentDisposition: (id: number, disposition: string) =>
    http<ContentTriageItem>(`/triage/content/${id}/disposition`, {
      method: "POST",
      body: JSON.stringify({ disposition }),
    }),
  getSettings: () => http<{ settings: AppSettingItem[] }>("/settings"),
  updateSettings: (updates: Record<string, number | string | boolean>) =>
    http<{ settings: AppSettingItem[] }>("/settings", { method: "PUT", body: JSON.stringify({ updates }) }),
  getSchedule: () => http<MonitoringSchedule>("/watchlist/schedule"),
  setSchedule: (body: { enabled?: boolean; interval_seconds?: number }) =>
    http<MonitoringSchedule>("/watchlist/schedule", { method: "PUT", body: JSON.stringify(body) }),
  startAutoCollect: () =>
    http<MonitoringSchedule & { dispatched: number }>("/watchlist/schedule/start", { method: "POST" }),
  stopAutoCollect: () =>
    http<MonitoringSchedule & { dispatched: number }>("/watchlist/schedule/stop", { method: "POST" }),
  getNotifications: (unreadOnly = true) =>
    http<WatchlistNotification[]>(`/watchlist/notifications?unread_only=${unreadOnly}`),
  readNotification: (id: number) =>
    http<WatchlistNotification>(`/watchlist/notifications/${id}/read`, { method: "POST" }),
  readAllNotifications: () =>
    http<{ marked_read: number }>("/watchlist/notifications/read-all", { method: "POST" }),
  getWatchlist: () => http<WatchTarget[]>("/watchlist"),
  addWatch: (source: string, kind: "account" | "keyword", value: string,
             opts?: { interval_seconds?: number | null; video_limit?: number | null }) =>
    http<WatchTarget>("/watchlist", {
      method: "POST",
      body: JSON.stringify({ source, kind, value, ...opts }),
    }),
  patchWatch: (id: number, body: {
    interval_seconds?: number | null; video_limit?: number | null; active?: boolean;
    clear_interval?: boolean; clear_limit?: boolean;
  }) => http<WatchTarget>(`/watchlist/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  removeWatch: (id: number) =>
    http<{ removed: number }>(`/watchlist/${id}`, { method: "DELETE" }),
  chat: (message: string, history: { role: string; content: string }[]) =>
    http<{ reply: string; action?: { type: string; view: string; target?: string } }>("/chat", {
      method: "POST",
      body: JSON.stringify({ message, history }),
    }),
  hunt: (opts: { sources?: string[]; count?: number; adapt?: boolean } = {}) =>
    http<{ started: boolean; sources: string[]; queries: string[]; count: number; adapted: boolean }>("/hunt", {
      method: "POST",
      body: JSON.stringify({ count: 6, ...opts }),
    }),
};
