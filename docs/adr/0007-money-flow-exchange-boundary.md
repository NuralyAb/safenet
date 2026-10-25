# ADR-0007 — Money Flow stops at the exchange boundary

**Status:** Accepted · **Date:** 2026-06-23

## Context
Money Flow Intelligence is close to the agency's mandate. We can observe **public on-chain** flow (social mention → wallet → exchange). The link **wallet → bank account** is exactly what the agency has and we don't. Over-claiming a full chain would compete with their systems (hard to procure) and over-promise on data we cannot access.

## Decision
Trace only the **public on-chain** segment `account → wallet → exchange` (`money_flow.py`, chain detection + exchange tagging). The flow graph carries an **explicit boundary marker**: «дальше — кошелёк → банковский счёт … обогащается данными АФМ». The on-chain query sits behind `OnChainClient` (`chain.py`); without a provider key it returns no edges (flow stops at the wallet). The boundary text is asserted in tests and shown in the dashboard.

Position: **a bridge, not the whole chain** — a complement to the agency's systems, not a rival. Easier to procure.

## Consequences
- ✅ Honest scope; no claims about bank-rail data we can't reach.
- ✅ Easier procurement (complement, not competitor).
- ➖ The most "complete" picture only exists after the agency enriches with its own data — by design.

## Alternatives considered
- **Claim full social→wallet→bank tracing** — competes with the buyer's own systems and over-promises; rejected.
