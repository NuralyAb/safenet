import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertIcon, SearchIcon, ShieldIcon } from "../../components/icons";
import { api } from "../../api/client";
import { useInvestigation } from "./useInvestigation";
import { beginCollection } from "../collection/collectionStore";
import { RiskReport } from "./RiskReport";
import { EvidencePackage } from "./EvidencePackage";

const STATUS_LABEL: Record<string, string> = {
  PENDING: "Запуск расследования…",
  RUNNING: "Расследование выполняется",
  COMPLETED: "Расследование завершено",
  FAILED: "Расследование завершилось ошибкой",
  CANCELED: "Расследование отменено",
  TERMINATED: "Расследование прервано",
  TIMED_OUT: "Превышено время ожидания",
  UNKNOWN: "Статус неизвестен",
};

export function InvestigationPanel({ initialTarget }: { initialTarget?: string }) {
  const accounts = useQuery<string[]>({ queryKey: ["accounts"], queryFn: api.getAccounts });
  const list = accounts.data ?? [];

  const [target, setTarget] = useState(initialTarget ?? "");
  useEffect(() => { if (initialTarget) setTarget(initialTarget); }, [initialTarget]);
  useEffect(() => { if (!target && list.length) setTarget(list[0]); }, [list, target]);

  const qc = useQueryClient();
  const inv = useInvestigation("analyst-1");
  const canSubmit = target.trim().length > 0 && !inv.isStarting;
  const submit = () => canSubmit && inv.start(target.trim());

  // Collect the account's OTHER videos (background) for a fuller investigation.
  const [collectLimit, setCollectLimit] = useState(10);
  const collect = useMutation({
    mutationFn: () => api.collectAccount(target.trim(), collectLimit),
    onSuccess: () => {
      beginCollection(target.trim());   // show the background-progress toast + auto-refresh
      qc.invalidateQueries({ queryKey: ["accounts"] });
    },
  });

  const statusClass = inv.status === "FAILED" || inv.error ? "error"
    : inv.status === "COMPLETED" ? "done" : "running";

  return (
    <>
      <section className="card">
        <div className="card-pad" style={{ display: "grid", gap: 14 }}>
          <div className="field">
            <label className="label" htmlFor="target">Аккаунт из базы</label>
            <div className="input-row">
              <select id="target" className="input" value={target} disabled={!list.length}
                      onChange={(e) => setTarget(e.target.value)}>
                {!list.length && <option value="">— в базе нет аккаунтов —</option>}
                {list.map((a) => <option key={a} value={a}>{a}</option>)}
              </select>
              <button className="btn btn-primary" onClick={submit} disabled={!canSubmit}>
                {inv.isStarting ? <><span className="spinner" /> Запуск</> : <><SearchIcon size={17} /> Расследовать</>}
              </button>
            </div>
            {!list.length ? (
              <p className="muted small" style={{ marginTop: 8 }}>
                База пуста. Аккаунты появляются здесь после «Анализа видео» (кнопка «Следить за
                аккаунтом») или сбора через «Мониторинг». Никаких тестовых данных.
              </p>
            ) : (
              <div className="row" style={{ marginTop: 8, gap: 8 }}>
                <button className="btn btn-ghost btn-sm" disabled={collect.isPending || !target}
                        onClick={() => collect.mutate()}>
                  {collect.isPending ? <><span className="spinner" /> Запуск сбора…</> : "Собрать другие видео аккаунта"}
                </button>
                <label className="muted small" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  лимит видео
                  <input className="input" type="number" min={1} max={50} value={collectLimit}
                         onChange={(e) => setCollectLimit(Math.max(1, Math.min(50, Number(e.target.value) || 1)))}
                         style={{ width: 64, padding: "4px 8px" }} />
                </label>
                {collect.isSuccess && (
                  <span className="muted small">
                    Сбор запущен в фоне (скачивание + анализ роликов канала). Через 1–2 мин обновите
                    расследование — появятся кошельки, связи и материалы.
                  </span>
                )}
                {collect.error && <span className="err small">{(collect.error as Error).message}</span>}
              </div>
            )}
          </div>

          {(inv.workflowId || inv.error) && (
            <div className={`status ${statusClass}`}>
              {inv.error ? <AlertIcon size={16} style={{ color: "var(--critical)" }} />
                : inv.isActive ? <span className="pulse-dot" /> : <span style={{ color: "var(--low)" }}>●</span>}
              <div style={{ display: "grid", gap: 2 }}>
                <strong>{inv.error ? "Не удалось запустить" : STATUS_LABEL[inv.status]}</strong>
                {inv.error
                  ? <span className="muted small">{inv.error}</span>
                  : inv.workflowId && <span className="muted small">workflow <code className="code">{inv.workflowId}</code></span>}
              </div>
              {(inv.report || inv.error) && (
                <button className="btn btn-ghost btn-sm" style={{ marginLeft: "auto" }} onClick={inv.reset}>Сбросить</button>
              )}
            </div>
          )}
        </div>
      </section>

      <section className="card">
        <div className="card-head">
          <ShieldIcon size={18} className="muted" />
          <h2>Отчёт о рисках</h2>
          {inv.report && <span className="hint">explainable · evidence-backed</span>}
        </div>
        <div className="card-pad">
          {inv.report ? (
            <>
              <RiskReport report={inv.report} />
              {inv.workflowId && <EvidencePackage workflowId={inv.workflowId} />}
            </>
          ) : inv.isActive ? (
            <div className="empty">
              <span className="spinner" style={{ width: 24, height: 24 }} />
              <h3>Собираем доказательства…</h3>
              <p>AI-следователь проходит этапы: профиль → отпечаток схемы → сеть → риск → нарратив.</p>
            </div>
          ) : (
            <div className="empty">
              <div className="icon"><ShieldIcon size={26} /></div>
              <h3>Отчёт появится здесь</h3>
              <p>Выберите аккаунт из базы и запустите расследование.</p>
            </div>
          )}
        </div>
      </section>
    </>
  );
}
