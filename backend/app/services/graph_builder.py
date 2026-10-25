"""Fraud Graph Builder (Neo4j + GDS).

Writes typed nodes/edges with provenance, then runs Graph Data Science to turn
the graph from a picture into analysis:
  - Louvain/Leiden community detection  -> "organized network of N objects"
  - betweenness centrality              -> ringleader / shared-wallet choke points

Every edge carries confidence, source and evidence_id for the evidence chain.
SAME_PERSON edges are CANDIDATES (confirmed=false) until an analyst approves them.
"""
from __future__ import annotations

from dataclasses import dataclass


# Cypher constraints — run once on startup (Phase 0 migration)
SCHEMA_CYPHER = [
    "CREATE CONSTRAINT account_id IF NOT EXISTS FOR (a:Account) REQUIRE a.id IS UNIQUE",
    "CREATE CONSTRAINT content_id IF NOT EXISTS FOR (c:Content) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT infra_id IF NOT EXISTS FOR (i:Infrastructure) REQUIRE i.id IS UNIQUE",
    "CREATE CONSTRAINT schema_id IF NOT EXISTS FOR (s:ScamSchema) REQUIRE s.id IS UNIQUE",
]


def communities_from_rows(rows: list[dict]) -> list[dict]:
    """Group GDS Louvain rows [{name, community}] -> communities sorted by size."""
    groups: dict = {}
    for r in rows:
        groups.setdefault(r["community"], []).append(r["name"])
    out = [
        {"community_id": cid, "members": sorted(members), "size": len(members)}
        for cid, members in groups.items()
    ]
    return sorted(out, key=lambda c: c["size"], reverse=True)


def ringleaders_from_rows(rows: list[dict], top: int = 5) -> list[dict]:
    """Sort GDS centrality rows [{name, score}] -> top brokers (choke points)."""
    scored = [{"id": r["name"], "score": round(float(r["score"]), 3)} for r in rows]
    return sorted(scored, key=lambda x: x["score"], reverse=True)[:top]


@dataclass
class Edge:
    src_label: str
    src_id: str
    rel: str
    dst_label: str
    dst_id: str
    props: dict   # must include: confidence, source, evidence_id, ts


class GraphBuilder:
    def __init__(self, driver):  # neo4j.Driver
        self.driver = driver

    def init_schema(self) -> None:
        with self.driver.session() as s:
            for stmt in SCHEMA_CYPHER:
                s.run(stmt)

    def upsert_edge(self, e: Edge) -> None:
        cypher = (
            f"MERGE (a:{e.src_label} {{id:$src}}) "
            f"MERGE (b:{e.dst_label} {{id:$dst}}) "
            f"MERGE (a)-[r:{e.rel}]->(b) SET r += $props"
        )
        with self.driver.session() as s:
            s.run(cypher, src=e.src_id, dst=e.dst_id, props=e.props)

    def network_summary(self, seed_id: str):
        """Expand 1-2 hops from a seed -> counts by node type (NetworkSummary)."""
        from app.services.investigation import network_summary_from_row

        cypher = (
            "MATCH (a {id:$seed})-[*1..2]-(n) "
            "WITH collect(DISTINCT n) AS ns "
            "RETURN size(ns) AS related, "
            "  size([x IN ns WHERE x:Account]) AS accounts, "
            "  size([x IN ns WHERE x.id STARTS WITH 'tg:']) AS telegram, "
            "  size([x IN ns WHERE x.id STARTS WITH 'wallet:']) AS wallets, "
            "  size([x IN ns WHERE x.id STARTS WITH 'http']) AS websites"
        )
        with self.driver.session() as s:
            rec = s.run(cypher, seed=seed_id).single()
            return network_summary_from_row(dict(rec) if rec else {})

    def shared_identifier_accounts(self, seed_id: str):
        """Accounts that share a hard identifier (wallet/telegram) with the seed.

        This is the no-embedding 'repeating scheme' signal: the same wallet across
        accounts is a certain link. Returns list[SchemeMatch].
        """
        from app.services.investigation import scheme_matches_from_rows

        cypher = (
            "MATCH (a {id:$seed})-[:MENTIONS]->(i:Infrastructure)<-[:MENTIONS]-(b:Account) "
            "WHERE b.id <> a.id "
            "RETURN b.id AS author, collect(DISTINCT i.id) AS shared"
        )
        with self.driver.session() as s:
            rows = [{"author": r["author"], "shared": r["shared"]} for r in s.run(cypher, seed=seed_id)]
        return scheme_matches_from_rows(rows)

    def link_identifiers(self, account: str, *, telegram=(), wallets=(), domains=(), phones=(),
                         cards=(), promo_codes=(), short_links=(), source: str = "pipeline") -> None:
        """Write account -MENTIONS-> infrastructure edges (populates the Fraud Graph).

        SafeNet KZ adds the identifiers that tie KZ schemes together: a Kaspi phone /
        card number (masked), a promo code, a shortened link shared by several accounts.
        """
        if not account:
            return
        prov = {"confidence": 1.0, "source": source, "evidence_id": "", "ts": ""}
        edges = (
            [(f"wallet:{w}") for w in wallets]
            + [(f"tg:{t.lower()}") for t in telegram]
            + [(f"http:{d.lower()}") for d in domains]
            + [(f"phone:{p}") for p in phones]
            + [(f"card:{c}") for c in cards]
            + [(f"promo:{c.upper()}") for c in promo_codes]
            + [(f"url:{u.lower()}") for u in short_links]
        )
        for infra_id in edges:
            self.upsert_edge(Edge("Account", account, "MENTIONS", "Infrastructure", infra_id, dict(prov)))

    def connected_accounts(self) -> list[str]:
        """Account ids that actually have at least one edge in the graph.

        The Materials/Hunter feeds list every author we've ever scored; only a few
        of those are wired into the Fraud Graph. The graph picker should offer only
        accounts that will actually render a network — not a wall of empty handles.
        """
        cypher = (
            "MATCH (a:Account)--() RETURN DISTINCT a.id AS id ORDER BY id"
        )
        with self.driver.session() as session:
            return [r["id"] for r in session.run(cypher)]

    def wallets_for(self, account: str) -> list[str]:
        """Wallet addresses an account mentions (for money-flow tracing)."""
        cypher = (
            "MATCH (a:Account {id: $id})-[:MENTIONS]->(i:Infrastructure) "
            "WHERE i.id STARTS WITH 'wallet:' RETURN i.id AS w"
        )
        with self.driver.session() as session:
            return [r["w"].split("wallet:", 1)[1] for r in session.run(cypher, id=account)]

    def confirm_same_person(self, account_a: str, account_b: str, analyst_id: str) -> None:
        """Analyst-confirmed identity link -> the ONLY path to a confirmed SAME_PERSON edge."""
        cypher = (
            "MERGE (a:Account {id: $a}) MERGE (b:Account {id: $b}) "
            "MERGE (a)-[r:SAME_PERSON]->(b) "
            "SET r.confirmed = true, r.confirmed_by = $by, r.source = 'analyst'"
        )
        with self.driver.session() as session:
            session.run(cypher, a=account_a, b=account_b, by=analyst_id)

    def write_scam_schemas(self, assignments: list[dict]) -> list[dict]:
        """Persist clusters as ScamSchema nodes + MATCHES_SCHEMA edges from content."""
        cypher = (
            "MERGE (s:ScamSchema {id: $sid}) SET s.size = $size "
            "WITH s UNWIND $members AS cid "
            "MERGE (c:Content {id: cid}) "
            "MERGE (c)-[r:MATCHES_SCHEMA]->(s) SET r.source = 'clustering'"
        )
        with self.driver.session() as session:
            for a in assignments:
                session.run(cypher, sid=a["schema_id"], size=a["size"], members=a["members"])
        return assignments

    def subgraph(self, seed_id: str) -> dict:
        """1-2 hop subgraph around a seed -> {nodes, edges} for the dashboard."""
        from app.services.investigation import subgraph_from_edge_rows

        cypher = (
            "MATCH p=({id:$seed})-[*1..2]-() "
            "UNWIND relationships(p) AS rel "
            "WITH DISTINCT rel "
            "RETURN startNode(rel).id AS source, endNode(rel).id AS target, "
            "  type(rel) AS label, rel.confidence AS confidence, "
            "  rel.evidence_id AS evidence_id, rel.confirmed AS confirmed, "
            "  labels(startNode(rel)) AS source_labels, labels(endNode(rel)) AS target_labels"
        )
        with self.driver.session() as s:
            rows = [dict(r) for r in s.run(cypher, seed=seed_id)]
        return subgraph_from_edge_rows(rows)

    _GDS_GRAPH = "afmGraph"

    def _project(self, session) -> None:
        """(Re)project the whole graph for GDS. Idempotent: drop then project."""
        session.run("CALL gds.graph.drop($g, false) YIELD graphName", g=self._GDS_GRAPH)
        session.run("CALL gds.graph.project($g, '*', {LINK: {type: '*', orientation: 'UNDIRECTED'}})",
                    g=self._GDS_GRAPH)

    def detect_communities(self) -> list[dict]:
        """GDS Louvain -> communities (the 'organized network of N objects' signal)."""
        with self.driver.session() as s:
            self._project(s)
            rows = [
                {"name": r["name"], "community": r["community"]}
                for r in s.run(
                    "CALL gds.louvain.stream($g) YIELD nodeId, communityId "
                    "RETURN gds.util.asNode(nodeId).id AS name, communityId AS community",
                    g=self._GDS_GRAPH,
                )
            ]
        return communities_from_rows(rows)

    def ringleader_candidates(self, top: int = 5) -> list[dict]:
        """GDS betweenness centrality -> nodes brokering the most paths (ringleaders)."""
        with self.driver.session() as s:
            self._project(s)
            rows = [
                {"name": r["name"], "score": r["score"]}
                for r in s.run(
                    "CALL gds.betweenness.stream($g) YIELD nodeId, score "
                    "RETURN gds.util.asNode(nodeId).id AS name, score",
                    g=self._GDS_GRAPH,
                )
            ]
        return ringleaders_from_rows(rows, top=top)
