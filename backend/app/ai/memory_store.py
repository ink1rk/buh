"""Long-term AI memory with optional ChromaDB + SQLite fallback."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.memory import AIMemory

logger = logging.getLogger(__name__)


class MemoryStore:
    def __init__(self) -> None:
        self._chroma = None
        self._collection = None
        self._init_chroma()

    def _init_chroma(self) -> None:
        settings = get_settings()
        try:
            import chromadb

            client = chromadb.PersistentClient(path=str(settings.chroma_path))
            self._collection = client.get_or_create_collection(
                name="finance_memory",
                metadata={"hnsw:space": "cosine"},
            )
            self._chroma = client
        except Exception as exc:  # noqa: BLE001
            logger.warning("ChromaDB unavailable, using SQLite memory only: %s", exc)
            self._chroma = None
            self._collection = None

    async def remember(
        self,
        db: AsyncSession,
        key: str,
        content: str,
        memory_type: str = "preference",
        importance: float = 0.5,
        tags: str = "",
    ) -> AIMemory:
        mem = AIMemory(
            key=key,
            content=content,
            memory_type=memory_type,
            importance=importance,
            tags=tags,
        )
        db.add(mem)
        await db.flush()

        if self._collection is not None:
            try:
                doc_id = f"mem-{mem.id}"
                self._collection.upsert(
                    ids=[doc_id],
                    documents=[f"{key}: {content}"],
                    metadatas=[{"type": memory_type, "importance": importance}],
                )
                mem.embedding_id = doc_id
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to upsert chroma memory: %s", exc)

        return mem

    async def recall(self, db: AsyncSession, query: str, limit: int = 5) -> list[str]:
        if self._collection is not None:
            try:
                res = self._collection.query(query_texts=[query], n_results=limit)
                docs = res.get("documents") or [[]]
                return [d for d in docs[0] if d]
            except Exception as exc:  # noqa: BLE001
                logger.warning("Chroma query failed: %s", exc)

        result = await db.execute(select(AIMemory).order_by(AIMemory.importance.desc()).limit(limit))
        rows = result.scalars().all()
        q = query.lower()
        scored = sorted(
            rows,
            key=lambda m: (q in m.content.lower() or q in m.key.lower(), m.importance),
            reverse=True,
        )
        return [f"{m.key}: {m.content}" for m in scored[:limit]]

    async def list_all(self, db: AsyncSession) -> list[AIMemory]:
        result = await db.execute(select(AIMemory).order_by(AIMemory.importance.desc()))
        return list(result.scalars().all())


memory_store = MemoryStore()
