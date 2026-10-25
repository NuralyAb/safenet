import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "../../api/client";

/** Verify an entity against the licensed registry — turns «нелицензионный» into a verdict. */
export function LicenseCheck() {
  const [q, setQ] = useState("");
  const check = useMutation({ mutationFn: () => api.checkLicense(q.trim()) });

  return (
    <section className="card">
      <div className="card-head">
        <h2>Проверка по реестру лицензий</h2>
        <span className="hint">домен / аккаунт / название оператора</span>
      </div>
      <div className="card-pad stack">
        <div className="input-row">
          <input className="input" value={q} placeholder="напр. profit-x.com или @broker"
                 onChange={(e) => setQ(e.target.value)}
                 onKeyDown={(e) => e.key === "Enter" && q.trim() && check.mutate()} />
          <button className="btn btn-primary" disabled={!q.trim() || check.isPending} onClick={() => check.mutate()}>
            {check.isPending ? <><span className="spinner" /> Проверка…</> : "Проверить"}
          </button>
        </div>
        {check.error && <p className="err small">{(check.error as Error).message}</p>}
        {check.data && (
          check.data.licensed ? (
            <div className="status done">
              <span className="badge threat LOW">в реестре</span>
              Оператор лицензирован (совпадение: <code className="code">{check.data.matched}</code>).
            </div>
          ) : (
            <div className="status error">
              <span className="badge threat CRITICAL">не в реестре</span>
              Не найден в реестре лицензий — при игорном/инвестиционном контенте это признак
              <b> нелицензионной (незаконной)</b> деятельности.
            </div>
          )
        )}
      </div>
    </section>
  );
}
