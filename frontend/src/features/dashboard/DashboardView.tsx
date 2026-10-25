import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, TRACK_RU, type ContentTriageItem, type GraphInsights, type SafeNetSummary, type WatchTarget } from "../../api/client";
import { AlertIcon, EyeIcon, FilmIcon, NetworkIcon, WalletIcon } from "../../components/icons";

type View = string;
const LEVELS = ["HIGH", "MEDIUM", "LOW"] as const;
const LEVEL_LABEL: Record<string, string> = { HIGH: "высокий", MEDIUM: "средний", LOW: "низкий" };
const TRACKS = ["lottery", "casino", "pyramid"] as const;
const TRACK_DESC: Record<string, string> = {
  lottery: "платное участие, рандомайзер, продажа номеров",
  casino: "нативная реклама, промокоды, зеркала, стримы",
  pyramid: "нереалистичный доход, рефералы, кураторы",
};

function fmt(n: number): string {
  if (!n) return "0";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

export function DashboardView({ onNavigate }: { onNavigate?: (v: View) => void }) {
  const materials = useQuery<ContentTriageItem[]>({ queryKey: ["content-triage"], queryFn: api.getContentTriage });
  const accounts = useQuery<string[]>({ queryKey: ["accounts"], queryFn: api.getAccounts });
  const watch = useQuery<WatchTarget[]>({ queryKey: ["watchlist"], queryFn: api.getWatchlist });
  const insights = useQuery<GraphInsights>({ queryKey: ["graph-insights"], queryFn: api.getInsights });
  const summary = useQuery<SafeNetSummary>({ queryKey: ["safenet-summary"], queryFn: api.getSafeNetSummary });
  const qc = useQueryClient();
  const refresh = () => ["content-triage", "safenet-summary", "accounts", "graph-insights", "graph-accounts"]
    .forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
  const seed = useMutation({ mutationFn: () => api.demoSeed(true), onSuccess: refresh });
  const rescore = useMutation({ mutationFn: api.rescore, onSuccess: refresh });

  const m = materials.data ?? [];
  const lvl = (x: ContentTriageItem) => (x.threat_level === "CRITICAL" ? "HIGH" : x.threat_level);
  const byLevel: Record<string, number> = Object.fromEntries(LEVELS.map((l) => [l, m.filter((x) => lvl(x) === l).length]));
  const highCrit = byLevel.HIGH || 0;
  const byTrack = summary.data?.by_track ?? {};
  const pending = m.filter((x) => x.disposition === "pending").length;
  const totalReach = m.reduce((s, x) => s + (x.reach?.views || 0), 0);
  const watchActive = (watch.data ?? []).filter((w) => w.active).length;
  const ringleaders = insights.data?.ringleaders?.length ?? 0;
  const communities = insights.data?.communities?.length ?? 0;

  const bySource: Record<string, number> = {};
  m.forEach((x) => { const s = x.source || "—"; bySource[s] = (bySource[s] || 0) + 1; });
  const sources = Object.entries(bySource).sort((a, b) => b[1] - a[1]);
  const top = [...m].sort((a, b) => (b.priority || 0) - (a.priority || 0)).slice(0, 6);
  const maxLevel = Math.max(1, ...LEVELS.map((l) => byLevel[l] || 0));
  const maxSrc = Math.max(1, ...sources.map(([, n]) => n));

  const KPIS = [
    { k: "materials", label: "Материалов", value: m.length, sub: `${pending} ожидают`, icon: FilmIcon, to: "materials" },
    { k: "risk", label: "Высокий риск", value: highCrit, sub: "к приоритетной проверке", icon: AlertIcon, to: "materials", alert: highCrit > 0 },
    { k: "reach", label: "Суммарный охват", value: fmt(totalReach), sub: "просмотров по материалам", icon: EyeIcon, to: "materials" },
    { k: "accounts", label: "Аккаунтов", value: accounts.data?.length ?? 0, sub: "в базе", icon: NetworkIcon, to: "investigation" },
    { k: "watch", label: "Под наблюдением", value: watchActive, sub: "целей мониторинга", icon: EyeIcon, to: "watchlist" },
    { k: "ring", label: "Организаторы / сообщества", value: `${ringleaders}/${communities}`, sub: "центр. узлы / кластеры", icon: WalletIcon, to: "graph" },
  ];

  const loading = materials.isLoading && accounts.isLoading;

  return (
    <div className="stack">
      {/* SafeNet KZ tracks */}
      <div className="sn-track-tiles">
        {TRACKS.map((t) => {
          const c = byTrack[t] ?? {};
          const high = (c.HIGH || 0) + (c.CRITICAL || 0);
          return (
            <button key={t} className={`sn-tile sn-track-${t}`} onClick={() => onNavigate?.("materials")}>
              <div className="sn-tile-title">{TRACK_RU[t]}</div>
              <div className="sn-tile-nums"><b>{high}</b> высокий · <b>{c.MEDIUM || 0}</b> средний · {c.LOW || 0} низкий</div>
              <div className="muted small">{TRACK_DESC[t]}</div>
            </button>
          );
        })}
        <div className="sn-tile sn-tile-actions">
          <div className="sn-tile-title">Демо-данные</div>
          <div className="muted small">Синтетические аккаунты, сети и группы по трём трекам</div>
          <div className="row" style={{ gap: 6, flexWrap: "wrap", marginTop: 6 }}>
            <button className="btn btn-primary btn-sm" disabled={seed.isPending} onClick={() => seed.mutate()}>
              {seed.isPending ? "Загрузка…" : "Загрузить демо"}
            </button>
            <button className="btn btn-ghost btn-sm" disabled={rescore.isPending} onClick={() => rescore.mutate()}
                    title="Пересчитать все материалы текущей методикой">
              {rescore.isPending ? "…" : "Пересчитать риск"}
            </button>
          </div>
          {seed.data && <div className="ok small">Загружено: {seed.data.posts} постов, {seed.data.chats.length} группы</div>}
          {rescore.data && <div className="ok small">Пересчитано: {rescore.data.rescored}</div>}
        </div>
      </div>

      {/* KPI cards */}
      <div className="dash-kpis">
        {KPIS.map((c) => {
          const Icon = c.icon;
          return (
            <button key={c.k} className={`kpi${c.alert ? " alert" : ""}`} onClick={() => onNavigate?.(c.to)}>
              <div className="kpi-top"><span className="kpi-label">{c.label}</span><Icon size={16} /></div>
              <div className="kpi-value">{loading ? "…" : c.value}</div>
              <div className="kpi-sub">{c.sub}</div>
            </button>
          );
        })}
      </div>

      <div className="dash-cols">
        {/* Threat distribution */}
        <section className="card">
          <div className="card-head"><h2>Распределение риска</h2><span className="hint">материалы по уровню угрозы</span></div>
          <div className="card-pad stack">
            {m.length === 0 ? (
              <div className="empty"><p>Пока нет материалов. Проверьте пост/скриншот/группу или загрузите демо.</p></div>
            ) : LEVELS.map((l) => (
              <div key={l} className="bar-row">
                <span className={`bar-tag badge threat ${l}`}>{LEVEL_LABEL[l]}</span>
                <div className="bar-track"><div className={`bar-fill lvl-${l}`} style={{ width: `${((byLevel[l] || 0) / maxLevel) * 100}%` }} /></div>
                <span className="bar-n">{byLevel[l] || 0}</span>
              </div>
            ))}
          </div>
        </section>

        {/* Sources */}
        <section className="card">
          <div className="card-head"><h2>Источники</h2><span className="hint">откуда собран контент</span></div>
          <div className="card-pad stack">
            {sources.length === 0 ? (
              <div className="empty"><p>Нет данных по источникам.</p></div>
            ) : sources.map(([s, n]) => (
              <div key={s} className="bar-row">
                <span className="bar-tag src">{s}</span>
                <div className="bar-track"><div className="bar-fill src-fill" style={{ width: `${(n / maxSrc) * 100}%` }} /></div>
                <span className="bar-n">{n}</span>
              </div>
            ))}
          </div>
        </section>
      </div>

      {/* Top materials by priority */}
      <section className="card">
        <div className="card-head">
          <h2>Топ материалов по приоритету</h2>
          <span className="hint">риск × охват</span>
        </div>
        <div className="card-pad">
          {top.length === 0 ? (
            <div className="empty"><h3>Очередь пуста</h3><p>Проверьте материал — самые опасные и охватные всплывут сюда.</p></div>
          ) : (
            <table className="table">
              <thead><tr><th>Материал</th><th>Трек</th><th>Риск</th><th>Охват</th><th>Приоритет</th></tr></thead>
              <tbody>
                {top.map((t) => (
                  <tr key={t.id} className="clickable" onClick={() => onNavigate?.("materials")}>
                    <td><b>{t.author || t.content_id.slice(0, 10)}</b> <span className="muted small">{t.source}</span></td>
                    <td className="small">{TRACK_RU[t.track ?? ""]}</td>
                    <td><span className={`badge threat ${t.threat_level}`}>{t.score}</span></td>
                    <td className="muted small">👁 {fmt(t.reach?.views ?? 0)}</td>
                    <td><b>{t.priority}</b></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>
    </div>
  );
}
