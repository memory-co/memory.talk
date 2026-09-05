"""IBIS 边(issue.md §6):五种类型,related 无向、其余有向;同一(类型, 对端)不重复。"""
from __future__ import annotations

from models.issue import Issue, IssueLink


def add_link(issue: Issue, link: IssueLink) -> bool:
    if any(l.type == link.type and l.target == link.target for l in issue.links):
        return False
    issue.links.append(link)
    return True
