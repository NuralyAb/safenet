import { useQuery } from "@tanstack/react-query";
import { api, type GraphInsights } from "../../api/client";

/** GDS analytics (communities + ringleaders). retry off — GDS may legitimately error. */
export function useInsights() {
  return useQuery<GraphInsights>({
    queryKey: ["graph", "insights"],
    queryFn: api.getInsights,
    retry: false,
    staleTime: 60_000,
  });
}
