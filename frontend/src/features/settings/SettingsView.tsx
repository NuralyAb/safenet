import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type AppSettingItem } from "../../api/client";

type Val = number | string | boolean;

export function SettingsView() {
  const qc = useQueryClient();
  const q = useQuery<{ settings: AppSettingItem[] }>({
    queryKey: ["settings"],
    queryFn: api.getSettings,
  });
  const [edits, setEdits] = useState<Record<string, Val>>({});
  const save = useMutation({
    mutationFn: () => api.updateSettings(edits),
    onSuccess: () => { setEdits({}); qc.invalidateQueries({ queryKey: ["settings"] }); },
  });

  const items = q.data?.settings ?? [];
  const groups = useMemo(() => {
    const m = new Map<string, AppSettingItem[]>();
    for (const it of items) (m.get(it.group) ?? m.set(it.group, []).get(it.group)!).push(it);
    return [...m.entries()];
  }, [items]);

  const current = (it: AppSettingItem): Val => (it.key in edits ? edits[it.key] : (it.value as Val));
  const setVal = (key: string, v: Val) => setEdits((e) => ({ ...e, [key]: v }));
  const dirty = Object.keys(edits).length;

  return (
    <section className="card">
      <div className="card-head">
        <h2>Настройки</h2>
        <span className="hint">применяются на лету · сохранение требует роли supervisor</span>
      </div>
      <div className="card-pad">
        {q.isLoading ? (
          <div className="empty"><span className="spinner" /></div>
        ) : (
          <>
            {groups.map(([group, rows]) => (
              <div key={group} className="settings-group">
                <h3 className="settings-group-title">{group}</h3>
                <div className="settings-grid">
                  {rows.map((it) => (
                    <div key={it.key} className="setting-row">
                      <div className="setting-meta">
                        <label htmlFor={it.key}>
                          {it.label}
                          {!it.is_default && !(it.key in edits) && <span className="tag-changed">изменено</span>}
                          {it.key in edits && <span className="tag-dirty">● не сохранено</span>}
                        </label>
                        {it.help && <p className="muted small">{it.help}</p>}
                        <code className="code mono">{it.key}</code>
                      </div>
                      <div className="setting-control">
                        {it.type === "bool" ? (
                          <label className="switch">
                            <input type="checkbox" checked={Boolean(current(it))}
                                   onChange={(e) => setVal(it.key, e.target.checked)} />
                            <span>{Boolean(current(it)) ? "вкл" : "выкл"}</span>
                          </label>
                        ) : it.options ? (
                          <select className="input" value={String(current(it))}
                                  onChange={(e) => setVal(it.key, e.target.value)}>
                            {it.options.map((o) => <option key={o} value={o}>{o}</option>)}
                          </select>
                        ) : it.type === "str" ? (
                          <input className="input" value={String(current(it))}
                                 onChange={(e) => setVal(it.key, e.target.value)} />
                        ) : (
                          <input className="input" type="number"
                                 min={it.min ?? undefined} max={it.max ?? undefined}
                                 step={it.type === "float" ? "0.1" : "1"}
                                 value={Number(current(it))}
                                 onChange={(e) => setVal(it.key, it.type === "float"
                                   ? Number(e.target.value) : Math.trunc(Number(e.target.value)))} />
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}

            <div className="settings-foot">
              <button className="btn btn-primary" disabled={!dirty || save.isPending} onClick={() => save.mutate()}>
                {save.isPending ? <><span className="spinner" /> Сохранение…</> : `Сохранить${dirty ? ` (${dirty})` : ""}`}
              </button>
              {dirty > 0 && (
                <button className="btn btn-ghost" disabled={save.isPending} onClick={() => setEdits({})}>
                  Отменить
                </button>
              )}
              {save.isSuccess && <span className="ok small">Сохранено</span>}
              {save.error && <span className="err small">{(save.error as Error).message}</span>}
            </div>
          </>
        )}
      </div>
    </section>
  );
}
