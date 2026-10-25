import { useMutation, useQuery } from "@tanstack/react-query";
import { api, TERMINAL_STATUSES, type WorkflowStatus } from "../../api/client";
import { setInvestigationId, useInvestigationId } from "./investigationStore";

/**
 * Drives the investigation lifecycle: POST to start, then poll GET every 2s
 * until the Temporal workflow reaches a terminal state. The active id lives in a
 * module store so it survives tab switches.
 */
export function useInvestigation(requestedBy: string) {
  const workflowId = useInvestigationId();

  const start = useMutation({
    mutationFn: (target: string) => api.openInvestigation(target, requestedBy),
    onSuccess: (data) => setInvestigationId(data.workflow_id),
  });

  const poll = useQuery({
    queryKey: ["investigation", workflowId],
    queryFn: () => api.getInvestigation(workflowId!),
    enabled: !!workflowId,
    refetchInterval: (q) => {
      const status = q.state.data?.status as WorkflowStatus | undefined;
      return status && TERMINAL_STATUSES.includes(status) ? false : 2000;
    },
  });

  const status: WorkflowStatus | "PENDING" = start.isPending
    ? "PENDING"
    : poll.data?.status ?? (workflowId ? "RUNNING" : "PENDING");

  const error = start.error ?? poll.error;

  function reset() {
    setInvestigationId(null);
    start.reset();
  }

  return {
    start: (t: string) => start.mutate(t),
    reset,
    workflowId,
    status,
    report: poll.data?.report ?? null,
    isStarting: start.isPending,
    isActive: !!workflowId && !TERMINAL_STATUSES.includes(status as WorkflowStatus),
    error: error instanceof Error ? error.message : null,
  };
}
