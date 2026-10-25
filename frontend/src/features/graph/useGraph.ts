import { useQuery } from "@tanstack/react-query";
import { api, type GraphData } from "../../api/client";

/** Fetch the fraud subgraph around a seed from Neo4j (via /api/v1/graph/{seed}). */
export function useGraph(seed: string) {
  return useQuery<GraphData>({
    queryKey: ["graph", seed],
    queryFn: () => api.getGraph(seed),
    enabled: Boolean(seed),
  });
}
