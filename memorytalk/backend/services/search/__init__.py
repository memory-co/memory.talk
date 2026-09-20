"""SearchService:综合搜索。它自己不搜,只是把同一个 q 交给每个 service 的 search(),把各家的命中汇总成一份。
加一种可搜的东西 = 那个 service 实现 search(q, limit) -> list[SearchHit],再在这里登记一行。"""
from __future__ import annotations

from memorytalk.backend.models.search import SearchHit, SearchResult
from memorytalk.backend.services.metas import MetasService
from memorytalk.backend.services.users import UserService
from memorytalk.backend.services.work import WorkService


class SearchService:
    def __init__(self, works: WorkService, metas: MetasService, users: UserService) -> None:
        self.sources = [works, metas, users]        # 顺序 = 结果里的分组顺序

    def search(self, q: str, limit: int = 20) -> SearchResult:
        q = q.strip()
        hits: list[SearchHit] = []
        counts: dict[str, int] = {}
        if not q:
            return SearchResult(query=q)
        for src in self.sources:
            found = src.search(q, limit)
            for h in found:
                counts[h.kind] = counts.get(h.kind, 0) + 1
            hits += found[:limit]
        return SearchResult(query=q, hits=hits, counts=counts)
