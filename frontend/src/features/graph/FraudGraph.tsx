import { useEffect, useMemo, useRef, useState } from "react";
import { DossierIcon, EyeIcon, FitIcon, NetworkIcon, WalletIcon } from "../../components/icons";
import type { GraphData, GraphNode } from "../../api/client";
import { useGraph } from "./useGraph";

const CARD_W = 196;
const CARD_H = 66;
const COL_GAP = 92;
const ROW_GAP = 22;
const PAD = 32;
const COL_STEP = CARD_W + COL_GAP;
const ROW_STEP = CARD_H + ROW_GAP;

type NType = GraphNode["type"];

const TYPE_LABEL: Record<NType, string> = {
  account: "Аккаунт",
  infrastructure: "Инфра",
  wallet: "Кошелёк",
  person: "Личность",
};

function TypeIcon({ type }: { type: NType }) {
  if (type === "wallet") return <WalletIcon size={17} />;
  if (type === "infrastructure") return <NetworkIcon size={17} />;
  if (type === "person") return <EyeIcon size={17} />;
  return <DossierIcon size={17} />;
}

const LEGEND: { type: NType; label: string }[] = [
  { type: "account", label: "Аккаунт" },
  { type: "infrastructure", label: "Инфраструктура" },
  { type: "wallet", label: "Кошелёк" },
  { type: "person", label: "Личность (candidate)" },
];

interface Pt { x: number; y: number; }
interface EdgeGeo { source: string; target: string; d: string; mx: number; my: number; candidate: boolean; label: string; }

/** Layered layout: BFS distance from the seed (or the highest-degree node)
 *  becomes the column. Turns the force-directed "cloud" into a readable map
 *  that flows outward from the target — hubs sit toward the top of each column. */
function useLayout(data: GraphData | undefined, seed: string) {
  return useMemo(() => {
    const nodes = data?.nodes ?? [];
    const edges = data?.edges ?? [];
    if (!nodes.length) return null;

    const adj = new Map<string, Set<string>>();
    const degree = new Map<string, number>();
    nodes.forEach((n) => adj.set(n.id, new Set()));
    edges.forEach((e) => {
      adj.get(e.source)?.add(e.target);
      adj.get(e.target)?.add(e.source);
      degree.set(e.source, (degree.get(e.source) || 0) + 1);
      degree.set(e.target, (degree.get(e.target) || 0) + 1);
    });
    const deg = (id: string) => degree.get(id) || 0;

    const byDegree = [...nodes].sort((a, b) => deg(b.id) - deg(a.id));
    const start = nodes.find((n) => n.id === seed)?.id ?? byDegree[0]?.id ?? nodes[0].id;
    const hubId = byDegree[0]?.id;

    // BFS depth from the start node.
    const depth = new Map<string, number>([[start, 0]]);
    const queue = [start];
    while (queue.length) {
      const cur = queue.shift()!;
      const d = depth.get(cur)!;
      adj.get(cur)?.forEach((nb) => {
        if (!depth.has(nb)) { depth.set(nb, d + 1); queue.push(nb); }
      });
    }
    let maxD = 0;
    depth.forEach((d) => { maxD = Math.max(maxD, d); });
    nodes.forEach((n) => { if (!depth.has(n.id)) depth.set(n.id, maxD + 1); }); // disconnected → last column
    maxD = Math.max(...[...depth.values()]);

    // Bucket nodes per column, hubs first (rendered toward the top).
    const cols: string[][] = Array.from({ length: maxD + 1 }, () => []);
    byDegree.forEach((n) => cols[depth.get(n.id)!].push(n.id));

    const maxRows = Math.max(1, ...cols.map((c) => c.length));
    const stageH = maxRows * ROW_STEP - ROW_GAP + PAD * 2;
    const stageW = PAD * 2 + maxD * COL_STEP + CARD_W;

    const pos = new Map<string, Pt>();
    cols.forEach((col, ci) => {
      const colH = col.length * ROW_STEP - ROW_GAP;
      const y0 = PAD + (stageH - PAD * 2 - colH) / 2;
      col.forEach((id, ri) => pos.set(id, { x: PAD + ci * COL_STEP, y: y0 + ri * ROW_STEP }));
    });

    const edgeGeo: EdgeGeo[] = [];
    edges.forEach((e) => {
      const sp = pos.get(e.source);
      const tp = pos.get(e.target);
      if (!sp || !tp) return;
      const rightward = tp.x >= sp.x;
      const sc: Pt = rightward ? { x: sp.x + CARD_W, y: sp.y + CARD_H / 2 } : { x: sp.x, y: sp.y + CARD_H / 2 };
      const tc: Pt = rightward ? { x: tp.x, y: tp.y + CARD_H / 2 } : { x: tp.x + CARD_W, y: tp.y + CARD_H / 2 };
      const dx = Math.max(30, Math.min(90, Math.abs(tc.x - sc.x) / 2));
      const c1x = rightward ? sc.x + dx : sc.x - dx;
      const c2x = rightward ? tc.x - dx : tc.x + dx;
      edgeGeo.push({
        source: e.source,
        target: e.target,
        d: `M ${sc.x} ${sc.y} C ${c1x} ${sc.y}, ${c2x} ${tc.y}, ${tc.x} ${tc.y}`,
        mx: (sc.x + tc.x) / 2,
        my: (sc.y + tc.y) / 2,
        candidate: e.label.includes("?"),
        label: e.label,
      });
    });

    return { nodes, pos, edgeGeo, deg, stageW, stageH, seedId: start, hubId, adj };
  }, [data, seed]);
}

export function FraudGraph({ seed }: { seed?: string }) {
  const { data } = useGraph(seed ?? "");
  const layout = useLayout(data, seed ?? "");
  const has = (layout?.nodes.length ?? 0) > 0;

  const canvasRef = useRef<HTMLDivElement>(null);
  const [view, setView] = useState({ x: 0, y: 0, scale: 1 });
  const [selected, setSelected] = useState<string | null>(null);
  const panRef = useRef<{ sx: number; sy: number; ox: number; oy: number } | null>(null);
  const [panning, setPanning] = useState(false);

  const fit = useMemo(() => () => {
    const el = canvasRef.current;
    if (!el || !layout) return;
    const r = el.getBoundingClientRect();
    const s = Math.min(r.width / layout.stageW, r.height / layout.stageH, 1.1) * 0.92;
    setView({ scale: s, x: (r.width - layout.stageW * s) / 2, y: (r.height - layout.stageH * s) / 2 });
  }, [layout]);

  // Fit whenever a new subgraph loads.
  useEffect(() => { setSelected(null); const id = requestAnimationFrame(fit); return () => cancelAnimationFrame(id); }, [fit]);

  // Wheel-to-zoom toward the cursor (native listener so we can preventDefault).
  useEffect(() => {
    const el = canvasRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const r = el.getBoundingClientRect();
      const cx = e.clientX - r.left;
      const cy = e.clientY - r.top;
      setView((v) => {
        const next = Math.max(0.35, Math.min(2.2, v.scale * (1 - e.deltaY * 0.0015)));
        const k = next / v.scale;
        return { scale: next, x: cx - (cx - v.x) * k, y: cy - (cy - v.y) * k };
      });
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [has]);

  function onPanStart(e: React.MouseEvent) {
    if ((e.target as HTMLElement).closest(".gnode")) return; // let card clicks through
    panRef.current = { sx: e.clientX, sy: e.clientY, ox: view.x, oy: view.y };
    setPanning(true);
    const onMove = (ev: MouseEvent) => {
      const p = panRef.current;
      if (!p) return;
      setView((v) => ({ ...v, x: p.ox + (ev.clientX - p.sx), y: p.oy + (ev.clientY - p.sy) }));
    };
    const onUp = () => {
      panRef.current = null;
      setPanning(false);
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }

  const zoom = (factor: number) =>
    setView((v) => {
      const el = canvasRef.current;
      const r = el?.getBoundingClientRect();
      const cx = (r?.width ?? 0) / 2;
      const cy = (r?.height ?? 0) / 2;
      const next = Math.max(0.35, Math.min(2.2, v.scale * factor));
      const k = next / v.scale;
      return { scale: next, x: cx - (cx - v.x) * k, y: cy - (cy - v.y) * k };
    });

  const neighbours = useMemo(() => {
    if (!selected || !layout) return null;
    const s = new Set<string>([selected]);
    layout.adj.get(selected)?.forEach((n) => s.add(n));
    return s;
  }, [selected, layout]);

  return (
    <div>
      <div className="graph-wrap">
        <div
          ref={canvasRef}
          className={`graph-canvas${panning ? " panning" : ""}`}
          onMouseDown={onPanStart}
        >
          {layout && (
            <div
              className="graph-stage"
              style={{ width: layout.stageW, height: layout.stageH, transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})` }}
            >
              <svg className="graph-edges" width={layout.stageW} height={layout.stageH}>
                <defs>
                  <marker id="afm-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                    <path d="M0 0 L10 5 L0 10 z" fill="context-stroke" />
                  </marker>
                </defs>
                {layout.edgeGeo.map((e, i) => {
                  const focus = selected != null && (e.source === selected || e.target === selected);
                  const dim = selected != null && !focus;
                  return (
                    <path
                      key={i}
                      d={e.d}
                      markerEnd="url(#afm-arrow)"
                      className={`gedge${e.candidate ? " candidate" : ""}${focus ? " focus" : ""}${dim ? " dim" : ""}`}
                    />
                  );
                })}
              </svg>

              {/* Edge labels — only for the focused neighbourhood, to keep it clean. */}
              {selected != null &&
                layout.edgeGeo
                  .filter((e) => e.source === selected || e.target === selected)
                  .map((e, i) => (
                    <span key={i} className="gedge-label" style={{ left: e.mx, top: e.my }}>{e.label}</span>
                  ))}

              {layout.nodes.map((n) => {
                const p = layout.pos.get(n.id)!;
                const isTarget = n.id === layout.seedId;
                const isHub = n.id === layout.hubId && !isTarget && layout.deg(n.id) > 1;
                const dim = neighbours != null && !neighbours.has(n.id);
                const focus = neighbours != null && neighbours.has(n.id) && n.id !== selected;
                const cls = [
                  "gnode", `gnode-${n.type}`,
                  isTarget ? "target" : "",
                  n.id === selected ? "selected" : "",
                  focus ? "focus" : "",
                  dim ? "dim" : "",
                ].filter(Boolean).join(" ");
                return (
                  <button
                    key={n.id}
                    className={cls}
                    style={{ left: p.x, top: p.y }}
                    title={n.id}
                    onClick={() => setSelected((cur) => (cur === n.id ? null : n.id))}
                  >
                    <span className="gnode-ic"><TypeIcon type={n.type} /></span>
                    <span className="gnode-body">
                      <span className="gnode-id">{n.id}</span>
                      <span className="gnode-meta">
                        <span className="gnode-type">{TYPE_LABEL[n.type]}</span> · {layout.deg(n.id)} св.
                      </span>
                    </span>
                    {isTarget && <span className="gnode-badge">ЦЕЛЬ</span>}
                    {isHub && <span className="gnode-badge hub">HUB</span>}
                  </button>
                );
              })}
            </div>
          )}

          {!has && (
            <div className="graph-empty">
              {seed ? "Нет связей для этого аккаунта" : "Выберите аккаунт, чтобы построить граф"}
            </div>
          )}

          {has && (
            <div className="graph-toolbar">
              <button className="icon-btn" title="Увеличить" onClick={() => zoom(1.2)}>+</button>
              <button className="icon-btn" title="Уменьшить" onClick={() => zoom(1 / 1.2)}>−</button>
              <button className="icon-btn" title="Вписать в экран" onClick={fit}><FitIcon size={15} /></button>
            </div>
          )}
        </div>
      </div>
      <div className="legend">
        {LEGEND.map((l) => (
          <span key={l.type} className="item">
            <span className="swatch" style={{ background: `var(--node-${l.type === "infrastructure" ? "infra" : l.type})` }} />
            {l.label}
          </span>
        ))}
      </div>
    </div>
  );
}
