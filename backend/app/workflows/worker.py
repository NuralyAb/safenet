"""Temporal worker hosting the AI Investigator workflow + activities.

Run as its own process/container:
    python -m app.workflows.worker
"""
from __future__ import annotations

import asyncio
import logging

from temporalio.client import Client
from temporalio.worker import Worker

from app.core.config import settings
from app.workflows import activities
from app.workflows.investigator import AIInvestigatorWorkflow

log = logging.getLogger("afm.investigator")


async def _connect(attempts: int = 60, delay: float = 2.0) -> Client:
    """Temporal (auto-setup) is slow to start — retry until it accepts connections."""
    last_err: Exception | None = None
    for i in range(attempts):
        try:
            return await Client.connect(settings.temporal_host, namespace=settings.temporal_namespace)
        except Exception as exc:  # noqa: BLE001 — connection refused while Temporal boots
            last_err = exc
            log.warning("Temporal not ready (%s/%s): %s", i + 1, attempts, exc)
            await asyncio.sleep(delay)
    raise RuntimeError(f"Temporal never became reachable: {last_err}")


async def main() -> None:
    client = await _connect()
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[AIInvestigatorWorkflow],
        activities=[
            activities.collect_profile,
            activities.match_fingerprints,
            activities.build_network,
            activities.compute_risk,
            activities.persist_assessment,
            activities.compose_narrative,
        ],
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
