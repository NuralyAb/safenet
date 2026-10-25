import { useState } from "react";
import { AlertIcon, BoltIcon, DossierIcon, EyeIcon, FilmIcon, GridIcon, MoonIcon, NetworkIcon, RadarIcon, SearchIcon, SettingsIcon, SunIcon } from "./components/icons";
import { LogoMark } from "./components/Logo";
import { useAuth } from "./lib/auth";
import { useTheme } from "./lib/theme";
import { LoginPanel } from "./features/auth/LoginPanel";
import { DashboardView } from "./features/dashboard/DashboardView";
import { InvestigationPanel } from "./features/investigation/InvestigationPanel";
import { LicenseCheck } from "./features/investigation/LicenseCheck";
import { TriageView } from "./features/triage/TriageView";
import { MaterialsView } from "./features/triage/MaterialsView";
import { TargetDossierView } from "./features/dossier/TargetDossierView";
import { ScamRadarView } from "./features/radar/ScamRadarView";
import { LiveScanView } from "./features/radar/LiveScanView";
import { HunterView } from "./features/hunter/HunterView";
import { WatchlistView } from "./features/watchlist/WatchlistView";
import { GraphView } from "./features/graph/GraphView";
import { ActionsView } from "./features/actions/ActionsView";
import { SettingsView } from "./features/settings/SettingsView";
import { ChatWidget } from "./features/assistant/ChatWidget";
import { CheckView } from "./features/safenet/CheckView";
import { MetricsView } from "./features/safenet/MetricsView";
import { TopProgress } from "./components/TopProgress";
import { NotificationToasts } from "./features/notifications/NotificationToasts";
import { useCollectionAutoRefresh } from "./features/collection/collectionStore";

type View = "dashboard" | "check" | "hunter" | "investigation" | "dossier" | "radar" | "scan" | "analyze" | "materials" | "triage" | "watchlist" | "graph" | "flow" | "metrics" | "actions" | "settings";

type NavGroup = "Обзор" | "Проверка" | "Источники" | "Очередь" | "Расследование" | "Качество" | "Система";

const NAV: {
  id: View;
  label: string;
  group: NavGroup;
  icon: (p: { size?: number }) => JSX.Element;
  title: string;
  desc: string;
  hot?: boolean;
}[] = [
  {
    id: "dashboard", label: "Обзор", group: "Обзор", icon: GridIcon,
    title: "SafeNet KZ — обзор",
    desc: "Сводка по трём трекам: платные розыгрыши, скрытая реклама онлайн-казино, финансовые пирамиды. Система показывает признаки возможного нарушения и уровень риска — законность проверяет специалист.",
  },
  {
    id: "check", label: "Проверка контента", group: "Проверка", icon: SearchIcon, hot: true,
    title: "Проверка контента",
    desc: "Пост, скриншот, транскрипт эфира, видео или целая группа (экспорт Telegram/WhatsApp). Русский, казахский, транслит и сленг; обфускация (к@зино, К А З И Н О, эмодзи) снимается автоматически. Для каждого признака — дословная цитата и вклад в балл.",
  },
  {
    id: "hunter", label: "Хантер", group: "Источники", icon: RadarIcon,
    title: "Хантер — автономный поиск",
    desc: "Агент сам формирует поисковые запросы по признакам трёх треков, сканирует YouTube/TikTok/Instagram и адаптируется: следующий раунд строится по найденным паттернам (каналы, домены, промокоды).",
  },
  {
    id: "radar", label: "Радар", group: "Источники", icon: RadarIcon,
    title: "Радар — поиск по ключевым словам",
    desc: "Поиск новых публикаций по ключевым словам и хэштегам. Найденное проходит весь конвейер и попадает в очередь материалов с риск-оценкой.",
  },
  {
    id: "scan", label: "Live-скан", group: "Источники", icon: RadarIcon,
    title: "Live-скан ленты",
    desc: "Демонстрация работы на потоке: материалы анализируются на лету, а отчёт собирается в реальном времени.",
  },
  {
    id: "watchlist", label: "Мониторинг", group: "Источники", icon: EyeIcon,
    title: "Постоянный мониторинг",
    desc: "Аккаунты, каналы и ключевые слова под наблюдением. Планировщик периодически собирает новые публикации и оценивает их.",
  },
  {
    id: "materials", label: "Материалы", group: "Очередь", icon: FilmIcon,
    title: "Очередь на ручную проверку",
    desc: "Все проверенные материалы с треком, уровнем риска и признаками. Сортировка: риск × охват. Специалист принимает решение: передать специалисту, наблюдать или отметить ложное срабатывание.",
  },
  {
    id: "triage", label: "Аккаунты", group: "Очередь", icon: AlertIcon,
    title: "Аккаунты на проверку",
    desc: "Объекты (аккаунты) по убыванию риска. Решение аналитика сохраняется и не сбрасывается при повторной оценке.",
  },
  {
    id: "dossier", label: "Досье", group: "Расследование", icon: DossierIcon,
    title: "Досье аккаунта",
    desc: "Все материалы аккаунта, общий паттерн признаков, идентификаторы (Kaspi-номера, карты, промокоды, каналы, домены) и связанные аккаунты.",
  },
  {
    id: "graph", label: "Граф связей", group: "Расследование", icon: NetworkIcon,
    title: "Граф связей: аккаунты, каналы, карты, домены как единая сеть",
    desc: "Аккаунты, которые собирают деньги на один Kaspi-номер, раздают один промокод или ведут в один канал, объединяются в сеть. Алгоритмы выделяют сообщества и центральные узлы — вероятных организаторов.",
  },
  {
    id: "investigation", label: "Расследование", group: "Расследование", icon: SearchIcon,
    title: "Расследование аккаунта",
    desc: "Сводная оценка аккаунта по собранным материалам, связи и совпадения схем; балл детерминированный, LLM только пишет пояснение по фактам.",
  },
  {
    id: "metrics", label: "Метрики и методика", group: "Качество", icon: BoltIcon,
    title: "Качество: метрики и методика",
    desc: "Precision, recall и доля ложных срабатываний на размеченных выборках (включая независимую слепую), срезы по языкам и обфускации, матрица ошибок. Ниже — все признаки, веса и правила расчёта риска.",
  },
  {
    id: "actions", label: "Действия", group: "Система", icon: BoltIcon,
    title: "Действия аналитика",
    desc: "Подтверждение связей «один человек» (human-in-the-loop) и пересборка кластеров схем.",
  },
  {
    id: "settings", label: "Настройки", group: "Система", icon: SettingsIcon,
    title: "Настройки",
    desc: "AI-провайдер (внешний API — только синтетика, local — self-hosted, mock — офлайн), LLM-помощник для поиска признаков, мониторинг, пороги алертов.",
  },
];

const NAV_GROUPS: NavGroup[] = ["Обзор", "Проверка", "Источники", "Очередь", "Расследование", "Качество", "Система"];

export function App() {
  const { isAuthed, role, logout } = useAuth();
  const { theme, toggle } = useTheme();
  const [view, setView] = useState<View>("dashboard");
  const [pendingAccount, setPendingAccount] = useState<string | undefined>();
  useCollectionAutoRefresh();   // refetch accounts/materials while a collection runs

  const investigateAccount = (account: string) => {
    setPendingAccount(account);
    setView("investigation");
  };
  const openDossier = (account: string) => {
    setPendingAccount(account);
    setView("dossier");
  };

  if (!isAuthed) return <LoginPanel />;

  const current = NAV.find((n) => n.id === view) ?? NAV[0];

  return (
    <div className="app-shell">
      <TopProgress />
      <NotificationToasts onOpen={openDossier} />
      <aside className="sidebar">
        <button className="brand" onClick={() => setView("dashboard")} title="На главную" aria-label="На главную">
          <LogoMark className="brand-mark" size={27} />
          <div>
            <div className="title">SafeNet KZ</div>
            <div className="subtitle">Цифровой щит</div>
          </div>
        </button>

        {NAV_GROUPS.map((group) => (
          <nav className="nav" key={group} aria-label={group}>
            <div className="nav-group-label">{group}</div>
            {NAV.filter((n) => n.group === group).map((n) => {
              const Icon = n.icon;
              const active = view === n.id;
              return (
                <button key={n.id} className={`nav-item${active ? " active" : ""}${n.hot ? " hot" : ""}`}
                        aria-current={active ? "page" : undefined}
                        onClick={() => setView(n.id)}>
                  <Icon size={17} />
                  <span>{n.label}</span>
                </button>
              );
            })}
          </nav>
        ))}

        <div className="sidebar-foot">
          <span className="role"><span className="pulse-dot" />{role}</span>
          <div className="spacer" />
          <button className="icon-btn" onClick={toggle}
                  aria-label={theme === "dark" ? "Светлая тема" : "Тёмная тема"}
                  title={theme === "dark" ? "Светлая тема" : "Тёмная тема"}>
            {theme === "dark" ? <SunIcon size={16} /> : <MoonIcon size={16} />}
          </button>
          <button className="btn btn-ghost btn-sm" onClick={logout}>Выйти</button>
        </div>
      </aside>

      <main className="main">
        <header className="view-head">
          <h1>{current.title}</h1>
          <p className="view-desc">{current.desc}</p>
        </header>

        {view === "dashboard" && <DashboardView onNavigate={(v) => setView(v as View)} />}
        {view === "investigation" && <><InvestigationPanel initialTarget={pendingAccount} /><LicenseCheck /></>}
        {view === "dossier" && <TargetDossierView initialTarget={pendingAccount} onInvestigate={investigateAccount} />}
        {view === "hunter" && <HunterView onInvestigate={openDossier} />}
        {view === "radar" && <ScamRadarView onInvestigate={openDossier} />}
        {view === "scan" && <LiveScanView onInvestigate={openDossier} />}
        {(view === "check" || view === "analyze") && <CheckView onOpenDossier={openDossier} />}
        {view === "materials" && <MaterialsView onInvestigate={openDossier} />}
        {view === "metrics" && <MetricsView />}
        {view === "triage" && <TriageView />}
        {view === "watchlist" && <WatchlistView />}
        {view === "graph" && <GraphView />}
        {view === "actions" && <ActionsView />}
        {view === "settings" && <SettingsView />}
      </main>

      <ChatWidget onAction={(a) => { if (a.target) setPendingAccount(a.target); setView(a.view as View); }} />
    </div>
  );
}
