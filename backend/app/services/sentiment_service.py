# backend/app/services/sentiment_service.py
"""Semantic retrieval of tweet summaries for Pro Deep Analysis context injection."""
from __future__ import annotations

import os

from openai import OpenAI
from sqlalchemy import text
from sqlalchemy.orm import Session

_openai = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))


def _embed(query: str) -> list[float]:
    resp = _openai.embeddings.create(model="text-embedding-3-small", input=[query])
    return resp.data[0].embedding


def get_tweet_context(
    db: Session,
    query: str,
    days: int = 30,
    limit: int = 10,
) -> list[str]:
    """
    Return up to `limit` tweet summaries semantically closest to `query`
    within the last `days` days. Returns [] if tweet_summaries is empty.
    """
    days = max(1, days)
    query_vec = _embed(query)
    embedding_str = "[" + ",".join(str(v) for v in query_vec) + "]"

    rows = db.execute(
        text("""
            SELECT summary FROM tweet_summaries
            WHERE tweet_date >= NOW() - (:days || ' days')::INTERVAL
              AND embedding IS NOT NULL
            ORDER BY embedding <-> CAST(:vec AS vector)
            LIMIT :limit
        """),
        {"days": str(days), "vec": embedding_str, "limit": limit},
    ).fetchall()

    return [r[0] for r in rows]


def format_for_prompt(summaries: list[str]) -> str:
    """Format summaries as a bulleted block for LLM prompt injection."""
    if not summaries:
        return ""
    lines = "\n".join(f"- {s}" for s in summaries)
    return f"Relevant recent social context (X/Twitter):\n{lines}"
