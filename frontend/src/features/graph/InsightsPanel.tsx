import { useInsights } from "./useInsights";

/** Turns the graph from a picture into analysis: organized-network size + ringleaders. */
export function InsightsPanel() {
  const { data, isError } = useInsights();
  if (isError || !data) return null;

  const top = data.communities[0];
  const ringleaders = data.ringleaders.slice(0, 3);

  if (!top && ringleaders.length === 0) return null;

  return (
    <div className="insights">
      {top && (
        <div className="insight">
          <b style={{ color: "var(--critical)" }}>{top.size}</b> объектов в крупнейшей
          организованной сети
        </div>
      )}
      {ringleaders.length > 0 && (
        <div className="insight">
          <span className="muted" style={{ fontSize: 12 }}>Центральные узлы (организаторы):</span>
          {ringleaders.map((r) => (
            <span key={r.id} className="badge" title={`centrality ${r.score}`}>{r.id}</span>
          ))}
        </div>
      )}
    </div>
  );
}
