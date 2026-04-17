"""
Memory manager: Handles long-term memory storage, retrieval, and refinement.
"""

import logging
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta
from typing import List, Dict, Optional

log = logging.getLogger(__name__)


class MemoryManager:
    """Manages long-term user memories and learning."""

    def __init__(self, db_connection):
        self.db = db_connection

    def add_memory(self, memory_text: str, category: str = "general", confidence: float = 0.8) -> int:
        """Add a new memory to the database."""
        cur = self.db.cursor()
        cur.execute("""
            INSERT INTO user_memories (memory_text, category, confidence, created_at, usage_count, last_used)
            VALUES (%s, %s, %s, NOW(), 0, NOW())
            RETURNING id
        """, (memory_text, category, confidence))
        memory_id = cur.fetchone()[0]
        self.db.commit()
        log.info(f"Added memory: {memory_text[:50]}...")
        return memory_id

    def get_memories_by_category(self, category: str, limit: int = 10) -> List[Dict]:
        """Get memories by category, ordered by usage and recency."""
        cur = self.db.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("""
            SELECT id, memory_text, confidence, usage_count, created_at, last_used
            FROM user_memories
            WHERE category = %s
            ORDER BY usage_count DESC, created_at DESC
            LIMIT %s
        """, (category, limit))
        return [dict(row) for row in cur.fetchall()]

    def get_all_memories(self, limit: int = 50) -> List[Dict]:
        """Get all memories, with recent ones and frequently used ones first."""
        cur = self.db.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("""
            SELECT id, memory_text, category, confidence, usage_count, created_at, last_used
            FROM user_memories
            ORDER BY
                (usage_count > 0) DESC,
                (NOW() - last_used < INTERVAL '7 days') DESC,
                created_at DESC
            LIMIT %s
        """, (limit,))
        return [dict(row) for row in cur.fetchall()]

    def get_top_memories(self, limit: int = 10) -> List[str]:
        """Get the most important/used memories as a list of texts."""
        memories = self.get_all_memories(limit)
        return [m['memory_text'] for m in memories]

    def update_memory_usage(self, memory_id: int):
        """Mark a memory as used (increment counter, update timestamp)."""
        cur = self.db.cursor()
        cur.execute("""
            UPDATE user_memories
            SET usage_count = usage_count + 1, last_used = NOW()
            WHERE id = %s
        """, (memory_id,))
        self.db.commit()

    def update_memory_confidence(self, memory_id: int, new_confidence: float):
        """Update the confidence score of a memory (e.g., user corrected it)."""
        cur = self.db.cursor()
        cur.execute("""
            UPDATE user_memories
            SET confidence = %s, last_used = NOW()
            WHERE id = %s
        """, (new_confidence, memory_id))
        self.db.commit()
        log.info(f"Updated memory {memory_id} confidence to {new_confidence}")

    def delete_memory(self, memory_id: int):
        """Delete a memory (user said it was wrong)."""
        cur = self.db.cursor()
        cur.execute("DELETE FROM user_memories WHERE id = %s", (memory_id,))
        self.db.commit()
        log.info(f"Deleted memory {memory_id}")

    def decay_unused_memories(self, days_threshold: int = 30):
        """Mark old, unused memories for potential deletion/archive."""
        cur = self.db.cursor()
        cutoff_date = datetime.now() - timedelta(days=days_threshold)

        # Lower confidence of very old, unused memories
        cur.execute("""
            UPDATE user_memories
            SET confidence = confidence * 0.8
            WHERE last_used < %s AND usage_count = 0
        """, (cutoff_date,))

        self.db.commit()
        log.info("Decayed unused memories")

    def search_memories(self, query: str, limit: int = 10) -> List[Dict]:
        """Search memories by keyword."""
        cur = self.db.cursor(cursor_factory=psycopg2.extras.DictCursor)

        # Simple keyword search (case-insensitive)
        query_pattern = f"%{query.lower()}%"
        cur.execute("""
            SELECT id, memory_text, category, confidence, usage_count, created_at
            FROM user_memories
            WHERE LOWER(memory_text) LIKE %s
            ORDER BY usage_count DESC, created_at DESC
            LIMIT %s
        """, (query_pattern, limit))

        return [dict(row) for row in cur.fetchall()]

    def get_memory_stats(self) -> Dict:
        """Get statistics about stored memories."""
        cur = self.db.cursor(cursor_factory=psycopg2.extras.DictCursor)

        cur.execute("""
            SELECT
                COUNT(*) as total_memories,
                COUNT(DISTINCT category) as unique_categories,
                AVG(confidence) as avg_confidence,
                MAX(last_used) as most_recent_used,
                COUNT(CASE WHEN usage_count > 0 THEN 1 END) as used_count
            FROM user_memories
        """)

        stats = dict(cur.fetchone())
        return stats

    def suggest_memories_for_context(self, keywords: List[str], limit: int = 5) -> List[str]:
        """Suggest memories that match given keywords."""
        all_memories = self.get_all_memories(limit * 2)

        # Score memories by keyword match
        scored = []
        for mem in all_memories:
            mem_text_lower = mem['memory_text'].lower()
            score = sum(
                mem_text_lower.count(kw.lower())
                for kw in keywords
            )
            if score > 0:
                scored.append((score, mem['memory_text']))

        # Sort by score and return top
        scored.sort(reverse=True, key=lambda x: x[0])
        return [text for _, text in scored[:limit]]
