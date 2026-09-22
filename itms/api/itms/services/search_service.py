from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import delete, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from itms.domain.search import SearchDocument
from itms.models.cmdb import SearchIndex

#: Заголовок и точные идентификаторы весомее описания: поиск по серийнику
#: не должен тонуть в тексте документов.
_TSV_SQL = text(
    """
    setweight(to_tsvector('russian', coalesce(:ts_title, '')), 'A') ||
    setweight(to_tsvector('simple',  coalesce(:ts_keywords, '')), 'A') ||
    setweight(to_tsvector('russian', coalesce(:ts_subtitle, '')), 'B') ||
    setweight(to_tsvector('russian', coalesce(:ts_body, '')), 'C')
    """
)

_WORD_RE = re.compile(r"[\w.:@/-]+", re.UNICODE)


def build_tsquery(query: str) -> str:
    """Готовит запрос с префиксным поиском по последнему слову (подсказки на лету)."""
    words = _WORD_RE.findall(query.lower())
    if not words:
        return ""
    escaped = [w.replace("'", "''") for w in words]
    parts = [f"{w}:*" for w in escaped]
    return " & ".join(parts)


async def index_entity(
    session: AsyncSession, entity_id: uuid.UUID, doc: SearchDocument
) -> None:
    params = {
        "ts_title": doc.title,
        "ts_subtitle": doc.subtitle,
        "ts_body": doc.body,
        "ts_keywords": doc.keywords,
    }
    tsv = _TSV_SQL.bindparams(**params)
    stmt = (
        insert(SearchIndex)
        .values(
            entity_type=doc.entity_type,
            entity_id=entity_id,
            title=doc.title,
            subtitle=doc.subtitle,
            body=doc.body,
            keywords=doc.keywords,
            tsv=tsv,
        )
        .on_conflict_do_update(
            index_elements=[SearchIndex.entity_type, SearchIndex.entity_id],
            set_={
                "title": doc.title,
                "subtitle": doc.subtitle,
                "body": doc.body,
                "keywords": doc.keywords,
                "tsv": tsv,
                "updated_at": text("now()"),
            },
        )
    )
    await session.execute(stmt)


async def remove_entity(session: AsyncSession, entity_type: str, entity_id: uuid.UUID) -> None:
    await session.execute(
        delete(SearchIndex).where(
            SearchIndex.entity_type == entity_type, SearchIndex.entity_id == entity_id
        )
    )


@dataclass(frozen=True, slots=True)
class SearchHit:
    entity_type: str
    entity_id: uuid.UUID
    title: str
    subtitle: str | None
    snippet: str | None
    rank: float


_SEARCH_SQL = """
SELECT entity_type, entity_id, title, subtitle,
       ts_headline('russian', coalesce(body, subtitle, title),
                   to_tsquery('russian', :tsq),
                   'MaxWords=18, MinWords=6, ShortWord=2, MaxFragments=1') AS snippet,
       GREATEST(
         ts_rank_cd(tsv, to_tsquery('russian', :tsq)),
         similarity(title, :raw) * 0.6,
         CASE WHEN keywords ILIKE :like THEN 0.5 ELSE 0 END
       ) AS rank
FROM search_index
WHERE (tsv @@ to_tsquery('russian', :tsq)
       OR keywords ILIKE :like
       OR title ILIKE :like)
  AND (cast(:types AS text) IS NULL OR entity_type = ANY(string_to_array(:types, ',')))
ORDER BY rank DESC, title
LIMIT :limit OFFSET :offset
"""


async def search(
    session: AsyncSession,
    query: str,
    *,
    entity_types: list[str] | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[SearchHit]:
    tsq = build_tsquery(query)
    if not tsq:
        return []
    rows = await session.execute(
        text(_SEARCH_SQL),
        {
            "tsq": tsq,
            "raw": query,
            "like": f"%{query.lower()}%",
            "types": ",".join(entity_types) if entity_types else None,
            "limit": limit,
            "offset": offset,
        },
    )
    return [
        SearchHit(
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            title=row.title,
            subtitle=row.subtitle,
            snippet=row.snippet,
            rank=float(row.rank or 0),
        )
        for row in rows
    ]


async def count_by_type(session: AsyncSession, query: str) -> dict[str, int]:
    tsq = build_tsquery(query)
    if not tsq:
        return {}
    rows = await session.execute(
        text(
            """
            SELECT entity_type, count(*) AS n
            FROM search_index
            WHERE tsv @@ to_tsquery('russian', :tsq)
               OR keywords ILIKE :like OR title ILIKE :like
            GROUP BY entity_type
            """
        ),
        {"tsq": tsq, "like": f"%{query.lower()}%"},
    )
    return {row.entity_type: int(row.n) for row in rows}
