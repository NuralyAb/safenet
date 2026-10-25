import { useMutation } from "@tanstack/react-query";
import { api } from "../../api/client";

function downloadMarkdown(name: string, md: string) {
  const blob = new Blob([md], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

/** «Сформировать справку» — binds the AI output to chain of custody (evidence package). */
export function EvidencePackage({ workflowId }: { workflowId: string }) {
  const gen = useMutation({ mutationFn: () => api.getEvidencePackage(workflowId) });

  return (
    <div className="evpkg">
      <button className="btn btn-ghost btn-sm" onClick={() => gen.mutate()} disabled={gen.isPending}>
        {gen.isPending ? <><span className="spinner" /> Формирование…</> : "Сформировать справку"}
      </button>

      {gen.error && (
        <span className="muted" style={{ fontSize: 12 }}>{(gen.error as Error).message}</span>
      )}

      {gen.data && (
        <div className="evpkg-out fade-in">
          <div className="row" style={{ alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <span className="muted" style={{ fontSize: 12 }}>Хеш-манифест:</span>
            <code className="code" title={gen.data.package.manifest_sha256}>
              {gen.data.package.manifest_sha256.slice(0, 16)}…
            </code>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => downloadMarkdown(`spravka-${gen.data!.package.object || "object"}.md`, gen.data!.markdown)}
            >
              Скачать .md
            </button>
          </div>
          <pre className="evpkg-md">{gen.data.markdown}</pre>
        </div>
      )}
    </div>
  );
}
