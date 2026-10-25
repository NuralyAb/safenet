import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type AnalysisResult, type ChatAnalysis } from "../../api/client";
import { HighlightedText, IdentifierList, RiskExplain } from "./RiskExplain";
import { ChatResult } from "./ChatResult";
import { BulkCheck } from "./BulkCheck";
import { printReport } from "./printReport";

type Mode = "text" | "image" | "url" | "video" | "chat" | "bulk";

const MODES: { id: Mode; label: string; hint: string }[] = [
  { id: "text", label: "Текст", hint: "пост, подпись, транскрипт эфира, сообщение" },
  { id: "image", label: "Скриншот", hint: "картинка с текстом: OCR + визуальные маркеры" },
  { id: "chat", label: "Группа / чат", hint: "экспорт Telegram (result.json) или WhatsApp (.txt)" },
  { id: "url", label: "Видео по ссылке", hint: "YouTube / TikTok / Instagram" },
  { id: "video", label: "Видеофайл", hint: "речь + кадры + текст на экране" },
  { id: "bulk", label: "Массовая проверка", hint: "тысячи постов из CSV / JSONL / TXT за секунды" },
];

const KINDS = [
  { id: "post", label: "пост" }, { id: "stream", label: "транскрипт эфира" },
  { id: "chat", label: "сообщение чата" }, { id: "ocr", label: "текст с картинки" },
];
const SOURCES = ["instagram", "tiktok", "telegram", "whatsapp", "youtube", "text"];

const EXAMPLES: { label: string; kind: string; text: string; expect: string }[] = [
  { label: "Платный розыгрыш", kind: "post", expect: "высокий",
    text: "🎁 РОЗЫГРЫШ iPhone 16! Номер = 1000 тг, всего 150 номеров. Оплата на Kaspi +7 747 123 45 67. Как только раскупят — крутим рандомайзер в прямом эфире" },
  { label: "Ұтыс (қаз.)", kind: "post", expect: "высокий",
    text: "Ұтыс ойыны! Қатысу ақылы — 500 тг, Kaspi-ге аударыңыз. Жеңімпазды тікелей эфирде кездейсоқ анықтаймыз. 20 орын қалды!" },
  { label: "Скрытое казино (обфускация)", kind: "post", expect: "высокий",
    text: "Как я поднял 300к за вечер 🎰 к@зино с выводом на каспи, промокод WIN500, ссылка в шапке" },
  { label: "Пирамида (рус+каз)", kind: "post", expect: "высокий",
    text: "Вложи 5к — получи 15к! Бүгін ғана, 3 орын қалды. Kaspi-ге аудар, пригласи друга — 10% с его вклада" },
  { label: "Транслит", kind: "post", expect: "средний/высокий",
    text: "Vlozhi 10 000 tg, cherez nedelyu poluchish 25 000 tg! Garantiya, pishi v lichku" },
  { label: "Эфир (стрим)", kind: "stream", expect: "высокий",
    text: "[стрим] ну что пацаны закидываю пятьдесят тысяч на слоты кто хочет со мной ссылка в описании промокод AZAMAT" },
  { label: "✓ Бесплатный конкурс", kind: "post", expect: "низкий",
    text: "РОЗЫГРЫШ! 🎁 Дарим сертификат на 20 000 тг. Условия: подписка, лайк, отметь подругу. Участие бесплатное, итоги в пятницу через рандомайзер" },
  { label: "✓ Банковский депозит", kind: "post", expect: "низкий",
    text: "Halyk: депозит «Онлайн» до 15% годовых. Вклады гарантированы КФГД" },
  { label: "✓ Новость о пирамиде", kind: "post", expect: "низкий",
    text: "Полиция Шымкента задержала организаторов финансовой пирамиды: обещали 30% в месяц. Не переводите деньги незнакомцам" },
];

export function CheckView({ onOpenDossier }: { onOpenDossier?: (account: string) => void }) {
  const qc = useQueryClient();
  const [mode, setMode] = useState<Mode>("text");
  const [text, setText] = useState("");
  const [kind, setKind] = useState("post");
  const [author, setAuthor] = useState("");
  const [source, setSource] = useState("instagram");
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [chatText, setChatText] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const demoChats = useQuery({ queryKey: ["demo-chats"], queryFn: api.getDemoChats });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["content-triage"] });
    qc.invalidateQueries({ queryKey: ["safenet-summary"] });
    qc.invalidateQueries({ queryKey: ["accounts"] });
  };

  const run = useMutation<AnalysisResult>({
    mutationFn: () => {
      if (mode === "text") return api.analyzeText({ text, kind, author, source });
      if (mode === "url") return api.analyzeUrl(url.trim());
      return api.analyzeFile(file as File, "", author);
    },
    onSuccess: invalidate,
  });
  const chat = useMutation<ChatAnalysis, Error, { demo?: string }>({
    mutationFn: ({ demo }) => api.analyzeChat(demo ? { demo } : file ? { file } : { text: chatText }),
    onSuccess: invalidate,
  });

  const switchMode = (m: Mode) => { setMode(m); setFile(null); run.reset(); chat.reset(); if (fileRef.current) fileRef.current.value = ""; };
  const canRun = mode === "text" ? text.trim().length > 0
    : mode === "url" ? url.trim().length > 0
    : mode === "chat" ? (file !== null || chatText.trim().length > 0)
    : file !== null;
  const pending = run.isPending || chat.isPending;
  const r = run.data;
  const error = (run.error || chat.error) as Error | null;

  return (
    <div className="stack">
      <section className="card">
        <div className="card-head">
          <h2>Проверить материал</h2>
          <span className="hint">{MODES.find((m) => m.id === mode)?.hint}</span>
        </div>
        <div className="card-pad stack">
          <div className="tabs">
            {MODES.map((m) => (
              <button key={m.id} className={`tab${mode === m.id ? " active" : ""}`} onClick={() => switchMode(m.id)}>{m.label}</button>
            ))}
          </div>

          {mode === "text" && (
            <>
              <textarea className="input sn-textarea" rows={5} value={text}
                        placeholder="Вставьте текст поста, подписи, транскрипт эфира или сообщение (русский, казахский, транслит)…"
                        onChange={(e) => setText(e.target.value)} />
              <div className="row" style={{ gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                <select className="input sn-select" value={kind} onChange={(e) => setKind(e.target.value)}>
                  {KINDS.map((k) => <option key={k.id} value={k.id}>{k.label}</option>)}
                </select>
                <select className="input sn-select" value={source} onChange={(e) => setSource(e.target.value)}>
                  {SOURCES.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
                <input className="input sn-author" value={author} placeholder="аккаунт / канал (необязательно)"
                       onChange={(e) => setAuthor(e.target.value)} />
                <button className="btn btn-primary" disabled={!canRun || pending} onClick={() => run.mutate()}>
                  {run.isPending ? <><span className="spinner" /> Анализ…</> : "Проверить"}
                </button>
              </div>
              <div>
                <div className="eyebrow" style={{ marginBottom: 6 }}>Примеры (синтетические)</div>
                <div className="chip-row">
                  {EXAMPLES.map((e) => (
                    <button key={e.label} className="chip" title={`ожидаемый уровень: ${e.expect}`}
                            onClick={() => { setText(e.text); setKind(e.kind); run.reset(); }}>{e.label}</button>
                  ))}
                </div>
              </div>
            </>
          )}

          {mode === "url" && (
            <div className="input-row">
              <input className="input" value={url} placeholder="https://www.youtube.com/watch?v=…  или ссылка TikTok/Instagram"
                     onChange={(e) => setUrl(e.target.value)} onKeyDown={(e) => e.key === "Enter" && canRun && run.mutate()} />
              <button className="btn btn-primary" disabled={!canRun || pending} onClick={() => run.mutate()}>
                {run.isPending ? <><span className="spinner" /> Анализ…</> : "Анализировать"}
              </button>
            </div>
          )}

          {(mode === "image" || mode === "video") && (
            <div className="input-row">
              <input ref={fileRef} type="file" className="input" accept={mode === "image" ? "image/*" : "video/*"}
                     onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
              <input className="input sn-author" value={author} placeholder="аккаунт (необязательно)"
                     onChange={(e) => setAuthor(e.target.value)} />
              <button className="btn btn-primary" disabled={!canRun || pending} onClick={() => run.mutate()}>
                {run.isPending ? <><span className="spinner" /> Анализ…</> : "Анализировать"}
              </button>
            </div>
          )}

          {mode === "chat" && (
            <div className="stack">
              <div className="input-row">
                <input ref={fileRef} type="file" className="input" accept=".json,.txt,application/json,text/plain"
                       onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
                <button className="btn btn-primary" disabled={!canRun || pending} onClick={() => chat.mutate({})}>
                  {chat.isPending ? <><span className="spinner" /> Анализ группы…</> : "Анализировать группу"}
                </button>
              </div>
              <textarea className="input sn-textarea" rows={4} value={chatText}
                        placeholder={"…или вставьте переписку построчно:\n[Куратор]: вложи 10 000 — через неделю 20 000\n[Айгерим]: выплата пришла 🙏"}
                        onChange={(e) => setChatText(e.target.value)} />
              <div>
                <div className="eyebrow" style={{ marginBottom: 6 }}>Демо-группы (синтетические)</div>
                <div className="chip-row">
                  {(demoChats.data ?? []).map((d) => (
                    <button key={d.id} className="chip" disabled={pending} onClick={() => chat.mutate({ demo: d.id })}>{d.title}</button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {mode === "bulk" && <BulkCheck />}

          {pending && mode !== "text" && (
            <p className="muted small">
              {mode === "chat" ? "Разбор сообщений → признаки → шаблоны и роли участников → риск группы."
                : "Извлечение текста (речь / OCR / визуальные теги) → признаки → детерминированный риск. До минуты."}
            </p>
          )}
          {error && <p className="err small">{error.message}</p>}
        </div>
      </section>

      {r && mode !== "chat" && (
        <section className="card fade-in">
          <div className="card-head">
            <h2>Результат</h2>
            <span className="hint">SHA-256 {r.sha256?.slice(0, 12)}… · сохранено в очередь материалов
              <button className="btn btn-ghost btn-sm" style={{ marginLeft: 10 }}
                      onClick={() => printReport(r.risk, { title: r.author || "материал", source: r.source, sha256: r.sha256,
                                                          text: r.text, identifiers: r.identifiers })}>
                Справка (печать / PDF)
              </button></span>
          </div>
          <div className="card-pad stack">
            <RiskExplain risk={r.risk} contentRiskId={r.content_risk_id} />
            {r.text && (
              <div>
                <div className="eyebrow" style={{ marginBottom: 6 }}>Текст материала · признаки подсвечены</div>
                <HighlightedText text={r.text} risk={r.risk} />
              </div>
            )}
            <IdentifierList ids={r.identifiers} />
            {r.author && onOpenDossier && (
              <div><button className="btn btn-ghost btn-sm" onClick={() => onOpenDossier(r.author)}>Досье аккаунта {r.author} →</button></div>
            )}
            {r.tags?.length > 0 && (
              <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
                <span className="eyebrow">Визуальные теги</span>{r.tags.map((t) => <span key={t} className="badge">{t}</span>)}
              </div>
            )}
            <details>
              <summary className="muted small">Исходный распознанный текст (подпись + речь + экран)</summary>
              <pre className="evpkg-md">{r.text || "—"}</pre>
            </details>
          </div>
        </section>
      )}

      {chat.data && mode === "chat" && <ChatResult r={chat.data} />}
    </div>
  );
}
