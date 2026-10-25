import { Suspense, lazy, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { InsightsPanel } from "./InsightsPanel";

const FraudGraph = lazy(() =>
  import("./FraudGraph").then((m) => ({ default: m.FraudGraph }))
);

export function GraphView() {
  const accounts = useQuery<string[]>({ queryKey: ["graph-accounts"], queryFn: api.getGraphAccounts });
  const list = accounts.data ?? [];
  const [seed, setSeed] = useState("");
  useEffect(() => { if (!seed && list.length) setSeed(list[0]); }, [list, seed]);

  return (
    <section className="card">
      <div className="card-head">
        <h2>Граф мошеннической сети</h2>
        <span className="hint">Neo4j · сообщества + центральность</span>
      </div>
      <div className="card-pad">
        <div className="field" style={{ maxWidth: 320, marginBottom: 14 }}>
          <label className="label" htmlFor="graph-seed">Аккаунт</label>
          <select id="graph-seed" className="input" value={seed} disabled={!list.length}
                  onChange={(e) => setSeed(e.target.value)}>
            {!list.length && <option value="">— в базе нет аккаунтов —</option>}
            {list.map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
        </div>

        <InsightsPanel />
        <Suspense fallback={<div className="empty"><span className="spinner" /></div>}>
          <FraudGraph seed={seed} />
        </Suspense>

        <p className="muted small" style={{ marginTop: 14 }}>
          Узлы — аккаунты, инфраструктура (кошельки/Telegram), личности. Пунктирные связи
          <b> SAME_PERSON?</b> — кандидаты, подтверждаются аналитиком в разделе «Действия».
          Каждое ребро несёт provenance (confidence, source, evidence_id).
        </p>
      </div>
    </section>
  );
}
