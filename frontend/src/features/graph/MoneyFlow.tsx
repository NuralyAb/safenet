import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api, type MoneyFlow as MoneyFlowData } from "../../api/client";
import { SearchIcon } from "../../components/icons";

/** Pure render of the on-chain flow (account → wallet → exchange) + boundary. */
export function MoneyFlowView({ flow }: { flow: MoneyFlowData }) {
  const wallets = flow.nodes.filter((n) => n.type === "wallet");
  const exchanges = flow.nodes.filter((n) => n.type === "exchange");
  const chainOf = (id: string) =>
    flow.edges.find((e) => e.target === id && e.chain)?.chain ?? undefined;

  return (
    <div className="flow fade-in">
      <div className="flow-row">
        <span className="badge" style={{ borderColor: "var(--node-account)" }}>{flow.account}</span>
        <span className="flow-arrow">→</span>
        <div className="flow-group">
          {wallets.length === 0 && <span className="muted">кошельки не найдены</span>}
          {wallets.map((w) => (
            <span key={w.id} className="badge" style={{ borderColor: "var(--node-wallet)" }}>
              {w.id}{chainOf(w.id) ? ` · ${chainOf(w.id)}` : ""}
            </span>
          ))}
        </div>
        {exchanges.length > 0 && (
          <>
            <span className="flow-arrow">→</span>
            <div className="flow-group">
              {exchanges.map((x) => (
                <span key={x.id} className="badge" style={{ borderColor: "var(--node-infra)" }}>
                  биржа · {x.id.slice(0, 10)}…
                </span>
              ))}
            </div>
          </>
        )}
      </div>

      <div className="flow-boundary"><b>Граница:</b> {flow.boundary.note}</div>
    </div>
  );
}

/** Container: enter an account, trace its public on-chain flow. */
export function MoneyFlow() {
  const [account, setAccount] = useState("");
  const trace = useMutation({ mutationFn: (a: string) => api.getMoneyFlow(a) });

  return (
    <div className="card-pad" style={{ display: "grid", gap: 12 }}>
      <div className="input-row">
        <input
          className="input" value={account} spellCheck={false} autoComplete="off"
          onChange={(e) => setAccount(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && account.trim() && trace.mutate(account.trim())}
          placeholder="@account"
        />
        <button className="btn btn-primary" onClick={() => account.trim() && trace.mutate(account.trim())}
                disabled={trace.isPending}>
          {trace.isPending ? <><span className="spinner" /> Трассировка</> : <><SearchIcon size={16} /> Проследить</>}
        </button>
      </div>
      {trace.error && <span className="muted" style={{ fontSize: 12 }}>{(trace.error as Error).message}</span>}
      {trace.data && <MoneyFlowView flow={trace.data} />}
    </div>
  );
}
