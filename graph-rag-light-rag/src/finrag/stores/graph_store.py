"""Neo4jGraphStore + FakeGraphStore: two implementations of the same `GraphStore` Protocol.

Schema (see PLAN.md 4.3):
    (:Entity  {name, type, description})
    (:Chunk   {id, company, section, text})
    (:Entity)-[:RELATED {description, keywords, strength}]->(:Entity)
    (:Entity)-[:MENTIONED_IN]->(:Chunk)

Entity names are normalized (.strip().upper()) by `extract.py` before they ever reach
this module, so every upsert here can assume `name` is already a stable merge key.

Embeddings are NOT stored here -- they live in Chroma (see `stores/vector_store.py`).
This module only ever talks Cypher / plain dicts.
"""

from typing import Protocol

from finrag.config import settings
from finrag.models import Chunk, Entity, Relation

# On a merge collision (the same entity/relation extracted from two different chunks)
# we concatenate the two descriptions with this separator and cap the result. LightRAG
# proper re-summarizes the merged description with an LLM call; concat-with-cap is the
# cheap version of that (PLAN.md stretch goal 1: "entity-description summarization").
_DESCRIPTION_SEP = "\n---\n"
_DESCRIPTION_CAP = 2000


class GraphStore(Protocol):
    """The interface both Neo4jGraphStore and FakeGraphStore implement.

    Kept intentionally tiny: five operations are enough to build the graph (upsert*,
    link_mention) and to serve both graph retrievers (neighborhood, chunks_for_entities).
    """

    def upsert_entity(self, e: Entity) -> None: ...

    def upsert_relation(self, r: Relation) -> None: ...

    def link_mention(self, entity_name: str, chunk: Chunk) -> None: ...

    def neighborhood(self, names: list[str], hops: int = 1) -> tuple[list[Entity], list[Relation]]: ...

    def chunks_for_entities(self, names: list[str], limit: int) -> list[Chunk]: ...


class Neo4jGraphStore:
    """Real graph store, backed by a Neo4j 5 Community instance via the official driver.

    The driver is created lazily (on first use, not in `__init__`) so simply importing
    or instantiating this class never requires a running database -- only calling a
    method does. That mirrors the lazy-singleton pattern already used in llm.py.
    """

    def __init__(self) -> None:
        self._driver = None

    def _session(self):
        if self._driver is None:
            from neo4j import GraphDatabase

            self._driver = GraphDatabase.driver(
                settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
            )
        return self._driver.session()

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    def ensure_constraints(self) -> None:
        """Uniqueness constraints double as indexes -- every MERGE in this file keys on
        Entity.name or Chunk.id, so these make every upsert an O(log n) lookup instead
        of a label scan. `IF NOT EXISTS` makes this safe to call on every startup.
        """
        with self._session() as session:
            session.run(
                "CREATE CONSTRAINT entity_name_unique IF NOT EXISTS "
                "FOR (e:Entity) REQUIRE e.name IS UNIQUE"
            )
            session.run(
                "CREATE CONSTRAINT chunk_id_unique IF NOT EXISTS "
                "FOR (c:Chunk) REQUIRE c.id IS UNIQUE"
            )

    def clear(self) -> None:
        # Wipes every node and relationship. Only meant for tests and full rebuilds --
        # there is no undo. `DETACH DELETE` removes a node's relationships along with it,
        # which plain `DELETE` would refuse to do while edges still reference the node.
        with self._session() as session:
            session.run("MATCH (n) DETACH DELETE n")

    def upsert_entity(self, e: Entity) -> None:
        query = """
        // Merge on name: the first time we see this entity, create it with the
        // extracted type + description. On every later sighting (same entity, a
        // different chunk), append the new description and cap the total length so
        // a very common entity (e.g. "APPLE") doesn't grow without bound.
        MERGE (e:Entity {name: $name})
        ON CREATE SET
            e.type = $type,
            e.description = $description
        ON MATCH SET
            e.description = substring(e.description + $sep + $description, 0, $cap)
        """
        with self._session() as session:
            session.run(
                query,
                name=e.name,
                type=e.type,
                description=e.description,
                sep=_DESCRIPTION_SEP,
                cap=_DESCRIPTION_CAP,
            )

    def upsert_relation(self, r: Relation) -> None:
        query = """
        // Both endpoints must already exist (build_graph upserts all of a chunk's
        // entities before its relations). Directed exactly as extracted: source -> target,
        // no separate handling for the reverse edge -- keeping this simple is a deliberate
        // PLAN.md choice, not an oversight.
        MATCH (s:Entity {name: $source})
        MATCH (t:Entity {name: $target})
        MERGE (s)-[rel:RELATED]->(t)
        ON CREATE SET
            rel.description = $description,
            rel.keywords = $keywords,
            rel.strength = $strength
        ON MATCH SET
            rel.description = substring(rel.description + $sep + $description, 0, $cap),
            rel.keywords = rel.keywords + [k IN $keywords WHERE NOT k IN rel.keywords],
            rel.strength = CASE WHEN $strength > rel.strength THEN $strength ELSE rel.strength END
        """
        with self._session() as session:
            session.run(
                query,
                source=r.source,
                target=r.target,
                description=r.description,
                keywords=r.keywords,
                strength=r.strength,
                sep=_DESCRIPTION_SEP,
                cap=_DESCRIPTION_CAP,
            )

    def link_mention(self, entity_name: str, chunk: Chunk) -> None:
        query = """
        // Chunk fields are set once, at creation, since chunk ids (and therefore their
        // text) are stable across re-runs of the pipeline.
        MERGE (c:Chunk {id: $chunk_id})
        ON CREATE SET c.company = $company, c.section = $section, c.text = $text
        WITH c
        // The entity must already have been upserted (build_graph's call order
        // guarantees this). If it hasn't, this MATCH finds nothing and the mention is
        // silently skipped -- a sign the caller used this store out of order.
        MATCH (e:Entity {name: $entity_name})
        MERGE (e)-[:MENTIONED_IN]->(c)
        """
        with self._session() as session:
            session.run(
                query,
                chunk_id=chunk.id,
                company=chunk.company,
                section=chunk.section,
                text=chunk.text,
                entity_name=entity_name,
            )

    def neighborhood(self, names: list[str], hops: int = 1) -> tuple[list[Entity], list[Relation]]:
        # Neo4j does not allow a query parameter inside the `*min..max` range of a
        # variable-length pattern, so `hops` (an int from our own config/callers, never
        # user text) is interpolated directly into the query string.
        hops = max(1, hops)
        query = f"""
        // Walk from each seed entity out to {hops} RELATED edges, in either direction.
        // `*0..{hops}` includes the zero-length path (the seed node by itself), so a
        // seed with no relations at all still comes back instead of vanishing.
        MATCH path = (seed:Entity)-[:RELATED*0..{hops}]-(:Entity)
        WHERE seed.name IN $names
        RETURN nodes(path) AS ns, relationships(path) AS rs
        """
        entities: dict[str, Entity] = {}
        relations: dict[tuple[str, str], Relation] = {}
        with self._session() as session:
            for record in session.run(query, names=names):
                for n in record["ns"]:
                    entities[n["name"]] = Entity(
                        name=n["name"], type=n["type"], description=n["description"]
                    )
                for r in record["rs"]:
                    key = (r.start_node["name"], r.end_node["name"])
                    relations[key] = Relation(
                        source=r.start_node["name"],
                        target=r.end_node["name"],
                        description=r["description"],
                        keywords=list(r["keywords"]),
                        strength=r["strength"],
                    )
        return list(entities.values()), list(relations.values())

    def chunks_for_entities(self, names: list[str], limit: int) -> list[Chunk]:
        query = """
        // Every chunk any of the given entities was mentioned in, deduped by DISTINCT
        // (an entity can be mentioned in the same chunk more than once via different
        // relations) and capped at `limit`.
        MATCH (e:Entity)-[:MENTIONED_IN]->(c:Chunk)
        WHERE e.name IN $names
        RETURN DISTINCT c
        LIMIT $limit
        """
        with self._session() as session:
            return [
                Chunk(id=r["c"]["id"], company=r["c"]["company"], section=r["c"]["section"], text=r["c"]["text"])
                for r in session.run(query, names=names, limit=limit)
            ]


class FakeGraphStore:
    """In-memory GraphStore for offline tests and any environment without Docker.

    Plain dicts/lists instead of a real graph engine; `neighborhood` does a manual BFS
    over an adjacency map built from the current relation set. Structural typing (the
    `GraphStore` Protocol) is the only thing tying this to `Neo4jGraphStore` -- there is
    no shared base class.
    """

    def __init__(self) -> None:
        self._entities: dict[str, Entity] = {}
        self._relations: dict[tuple[str, str], Relation] = {}
        self._chunks: dict[str, Chunk] = {}
        self._mentions: dict[str, list[str]] = {}  # entity name -> chunk ids, in link order

    def upsert_entity(self, e: Entity) -> None:
        existing = self._entities.get(e.name)
        if existing is None:
            self._entities[e.name] = e
        else:
            merged = (existing.description + _DESCRIPTION_SEP + e.description)[:_DESCRIPTION_CAP]
            self._entities[e.name] = Entity(name=e.name, type=existing.type, description=merged)

    def upsert_relation(self, r: Relation) -> None:
        key = (r.source, r.target)
        existing = self._relations.get(key)
        if existing is None:
            self._relations[key] = r
        else:
            merged_desc = (existing.description + _DESCRIPTION_SEP + r.description)[:_DESCRIPTION_CAP]
            merged_keywords = existing.keywords + [k for k in r.keywords if k not in existing.keywords]
            self._relations[key] = Relation(
                source=r.source,
                target=r.target,
                description=merged_desc,
                keywords=merged_keywords,
                strength=max(existing.strength, r.strength),
            )

    def link_mention(self, entity_name: str, chunk: Chunk) -> None:
        self._chunks[chunk.id] = chunk
        seen = self._mentions.setdefault(entity_name, [])
        if chunk.id not in seen:
            seen.append(chunk.id)

    def neighborhood(self, names: list[str], hops: int = 1) -> tuple[list[Entity], list[Relation]]:
        adjacency: dict[str, set[str]] = {}
        for source, target in self._relations:
            adjacency.setdefault(source, set()).add(target)
            adjacency.setdefault(target, set()).add(source)

        visited = {n for n in names if n in self._entities}
        frontier = set(visited)
        for _ in range(hops):
            frontier = {neighbor for n in frontier for neighbor in adjacency.get(n, set())} - visited
            if not frontier:
                break
            visited |= frontier

        entities = [self._entities[n] for n in visited]
        relations = [r for (s, t), r in self._relations.items() if s in visited and t in visited]
        return entities, relations

    def chunks_for_entities(self, names: list[str], limit: int) -> list[Chunk]:
        chunk_ids: list[str] = []
        for name in names:
            for cid in self._mentions.get(name, []):
                if cid not in chunk_ids:
                    chunk_ids.append(cid)
        return [self._chunks[cid] for cid in chunk_ids[:limit]]

    def ensure_constraints(self) -> None:
        pass  # dicts keyed by name/id are already "constrained" -- nothing to do

    def clear(self) -> None:
        self._entities.clear()
        self._relations.clear()
        self._chunks.clear()
        self._mentions.clear()
