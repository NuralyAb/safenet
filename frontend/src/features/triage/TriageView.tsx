import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type TriageItem } from "../../api/client";

const DISPO_LABEL: Record<string, string> = {
  pending: "ожидает", escalated: "эскалирована", dismissed: "отклонена", watching: "наблюдение",
};
const ACTIONS = [
  { id: "escalated", label: "Эскалировать" },
  { id: "watching", label: "В наблюдение" },
  { id: "dismissed", label: "Отклонить" },
];

export function TriageView() {
  const qc = useQueryClient();
  const list = useQuery<TriageItem[]>({ queryKey: ["triage"], queryFn: api.getTriage });
  const set = useMutation({
    mutationFn: ({ id, d }: { id: number; d: string }) => api.setDisposition(id, d),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["triage"] }),
  });

  const items = list.data ?? [];

  return (
    <section className="card">
      <div className="card-head">
        <h2>Объекты на проверку</h2>
        <span className="hint">по убыванию риска · {items.filter((t) => t.disposition === "pending").length} ожидают</span>
      </div>
      <div className="card-pad">
        {list.isLoading ? (
          <div className="empty"><span className="spinner" /></div>
        ) : items.length === 0 ? (
          <div className="empty"><h3>Очередь пуста</h3><p>Запустите расследование — объект попадёт сюда с оценкой риска.</p></div>
        ) : (
          <table className="table">
            <thead>
              <tr><th>Объект</th><th>Риск</th><th>Рекомендация</th><th>Диспозиция</th><th>Действие</th></tr>
            </thead>
            <tbody>
              {items.map((t) => (
                <tr key={t.id} className={t.disposition === "dismissed" ? "row-off" : ""}>
                  <td><b>{t.target}</b></td>
                  <td><span className={`badge threat ${t.threat_level}`}>{t.score} · {t.threat_level}</span></td>
                  <td className="muted small">{t.recommendation}</td>
                  <td>
                    {DISPO_LABEL[t.disposition] ?? t.disposition}
                    {t.disposition_by && <span className="muted small"> ({t.disposition_by})</span>}
                  </td>
                  <td>
                    <div className="row" style={{ gap: 6 }}>
                      {ACTIONS.map((a) => (
                        <button key={a.id} className="btn btn-ghost btn-sm" disabled={set.isPending || t.disposition === a.id}
                                onClick={() => set.mutate({ id: t.id, d: a.id })}>
                          {a.label}
                        </button>
                      ))}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}
