import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "../../api/client";

/** Supervisor actions: confirm a Same-Person identity link, rebuild scam schemes.
 *  Both require the `supervisor` role — an `analyst` token gets 403 (shown inline). */
export function ActionsView() {
  const [a, setA] = useState("@fast_profit");
  const [b, setB] = useState("@invest_money");

  const confirm = useMutation({ mutationFn: () => api.confirmSamePerson(a.trim(), b.trim()) });
  const rebuild = useMutation({ mutationFn: () => api.rebuildSchemas() });

  return (
    <div className="stack">
      <section className="card">
        <div className="card-head">
          <h2>Подтвердить «Один человек» (Same-Person)</h2>
          <span className="hint">human-in-the-loop · роль supervisor</span>
        </div>
        <div className="card-pad stack">
          <p className="muted small">
            Биометрия (лицо/голос) даёт лишь <b>кандидата</b>. Связь становится фактом в графе
            только после подтверждения аналитиком — здесь это действие фиксируется в audit-журнале.
          </p>
          <div className="grid-2">
            <div className="field">
              <label className="label" htmlFor="acc-a">Аккаунт A</label>
              <input id="acc-a" className="input" value={a} onChange={(e) => setA(e.target.value)} />
            </div>
            <div className="field">
              <label className="label" htmlFor="acc-b">Аккаунт B</label>
              <input id="acc-b" className="input" value={b} onChange={(e) => setB(e.target.value)} />
            </div>
          </div>
          <div className="row">
            <button className="btn btn-primary" disabled={confirm.isPending || !a.trim() || !b.trim()}
                    onClick={() => confirm.mutate()}>
              {confirm.isPending ? <><span className="spinner" /> Подтверждение…</> : "Подтвердить связь"}
            </button>
            {confirm.data?.confirmed && <span className="ok">Связь подтверждена ({confirm.data.by})</span>}
            {confirm.error && <span className="err">{(confirm.error as Error).message}</span>}
          </div>
        </div>
      </section>

      <section className="card">
        <div className="card-head">
          <h2>Пересобрать схемы (ScamSchema)</h2>
          <span className="hint">кластеризация отпечатков · роль supervisor</span>
        </div>
        <div className="card-pad stack">
          <p className="muted small">
            Берёт все отпечатки из Qdrant, объединяет похожие/связанные общими идентификаторами в
            <b> кластеры-схемы</b> и записывает их в граф (узлы ScamSchema). Тяжёлая операция.
          </p>
          <div className="row">
            <button className="btn btn-primary" disabled={rebuild.isPending} onClick={() => rebuild.mutate()}>
              {rebuild.isPending ? <><span className="spinner" /> Пересборка…</> : "Пересобрать схемы"}
            </button>
            {rebuild.data && <span className="ok">Готово: схем найдено {rebuild.data.count}</span>}
            {rebuild.error && <span className="err">{(rebuild.error as Error).message}</span>}
          </div>
          {rebuild.data && rebuild.data.schemas.length > 0 && (
            <ul className="plain-list">
              {rebuild.data.schemas.map((s) => (
                <li key={s.schema_id}>
                  <code className="code">{s.schema_id}</code> · {s.size} объектов: {s.members.join(", ")}
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>
    </div>
  );
}
