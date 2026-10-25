import { useQuery } from "@tanstack/react-query";
import { api, TRACK_RU, type Insights } from "../../api/client";

const pct = (x: number | null) => (x === null ? "—" : `${Math.round(100 * x)}%`);

/** «Схемы быстро меняют форму»: new wording to add + which signs analysts reject. */
export function InsightsView() {
  const q = useQuery<Insights>({ queryKey: ["safenet-insights"], queryFn: api.getInsights2 });
  const e = q.data?.emerging;
  const f = q.data?.feedback;

  return (
    <div className="stack">
      {q.isLoading && <div className="empty"><span className="spinner" /></div>}
      {q.error && <p className="err small">{(q.error as Error).message}</p>}

      {e && (
        <section className="card">
          <div className="card-head">
            <h2>Новые формулировки — кандидаты в словарь</h2>
            <span className="hint">часто в помеченных ({e.flagged_materials}), редко в чистых ({e.clean_materials}), не покрыты правилами</span>
          </div>
          <div className="card-pad stack">
            <p className="small muted">
              Слова, которые встречаются у разных аккаунтов в материалах со средним и высоким риском, но которых нет
              ни в одном признаке и которые не использованы как доказательство: новые бренды, сленг, краш-игры.
              Аналитик решает, какие из них добавить в методику. Так система догоняет схемы, меняющие форму.
            </p>
            {e.terms.length === 0 ? <p className="muted small">Пока недостаточно помеченных материалов.</p> : (
              <table className="table">
                <thead><tr><th>Слово</th><th>Трек</th><th>Помеч. / чистых</th><th>Аккаунтов</th><th>Пример</th></tr></thead>
                <tbody>{e.terms.map((t) => (
                  <tr key={t.term}>
                    <td><b>{t.term}</b></td><td className="small">{TRACK_RU[t.track] ?? "—"}</td>
                    <td>{t.flagged_materials} / {t.clean_materials}</td><td>{t.accounts}</td>
                    <td className="muted small">{t.example}</td>
                  </tr>
                ))}</tbody>
              </table>
            )}
          </div>
        </section>
      )}

      {f && (
        <section className="card">
          <div className="card-head">
            <h2>Качество признаков по решениям аналитиков</h2>
            <span className="hint">решений: {f.decisions} · подтверждено {f.confirmed} · ложных {f.dismissed} · точность в работе {pct(f.precision)}</span>
          </div>
          <div className="card-pad">
            {f.signals.length === 0 ? (
              <p className="muted small">Решений ещё нет. Кнопки «Передать специалисту / Наблюдать / Ложное срабатывание»
                в очереди материалов наполняют эту таблицу: видно, какой признак чаще всего даёт ложные срабатывания.</p>
            ) : (
              <table className="table">
                <thead><tr><th>Признак</th><th>Решений</th><th>Подтверждено</th><th>Ложных</th><th>Точность</th></tr></thead>
                <tbody>{f.signals.map((s) => (
                  <tr key={s.signal}>
                    <td><b>{s.label}</b></td><td>{s.decisions}</td><td>{s.confirmed}</td>
                    <td>{s.dismissed}</td>
                    <td><span className={`badge threat ${s.precision !== null && s.precision < 0.7 ? "HIGH" : "LOW"}`}>{pct(s.precision)}</span></td>
                  </tr>
                ))}</tbody>
              </table>
            )}
          </div>
        </section>
      )}
    </div>
  );
}
