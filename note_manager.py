"""
Note manager: Handles note creation, categorization, storage, and retrieval.
"""

import logging
import psycopg2
import psycopg2.extras
from datetime import datetime
from typing import List, Dict, Optional

log = logging.getLogger(__name__)


class NoteManager:
    """Manages user notes with auto-categorization and search."""

    def __init__(self, db_connection):
        self.db = db_connection

    def create_note(
        self,
        content: str,
        category: str = "general",
        importance: int = 0,
        voice_confidence: float = 1.0
    ) -> int:
        """Create a new note."""
        cur = self.db.cursor()
        cur.execute("""
            INSERT INTO notes (content, category, created_at, importance, voice_confidence)
            VALUES (%s, %s, NOW(), %s, %s)
            RETURNING id
        """, (content, category, importance, voice_confidence))
        note_id = cur.fetchone()[0]
        self.db.commit()
        log.info(f"Created note {note_id}: {content[:50]}...")
        return note_id

    def add_tags_to_note(self, note_id: int, tags: List[str], auto_generated: bool = True):
        """Add tags to a note."""
        cur = self.db.cursor()
        for tag in tags:
            cur.execute("""
                INSERT INTO note_tags (note_id, tag, auto_generated)
                VALUES (%s, %s, %s)
            """, (note_id, tag.lower(), auto_generated))
        self.db.commit()

    def get_note(self, note_id: int) -> Optional[Dict]:
        """Get a single note by ID."""
        cur = self.db.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("""
            SELECT id, content, category, created_at, importance, last_accessed, voice_confidence
            FROM notes
            WHERE id = %s
        """, (note_id,))
        return dict(cur.fetchone()) if cur.fetchone() else None

    def get_note_with_tags(self, note_id: int) -> Optional[Dict]:
        """Get a note with its tags."""
        note = self.get_note(note_id)
        if not note:
            return None

        cur = self.db.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("""
            SELECT tag FROM note_tags WHERE note_id = %s
        """, (note_id,))
        note['tags'] = [row['tag'] for row in cur.fetchall()]
        return note

    def get_notes_by_category(self, category: str, limit: int = 50) -> List[Dict]:
        """Get all notes in a category, sorted by recency."""
        cur = self.db.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("""
            SELECT id, content, category, created_at, importance, last_accessed
            FROM notes
            WHERE category = %s
            ORDER BY created_at DESC
            LIMIT %s
        """, (category, limit))
        return [dict(row) for row in cur.fetchall()]

    def get_all_notes(self, limit: int = 100, sort_by: str = "recent") -> List[Dict]:
        """Get all notes, optionally sorted by importance, recency, or category."""
        cur = self.db.cursor(cursor_factory=psycopg2.extras.DictCursor)

        if sort_by == "important":
            order = "importance DESC, created_at DESC"
        elif sort_by == "category":
            order = "category ASC, created_at DESC"
        else:  # recent
            order = "created_at DESC"

        cur.execute(f"""
            SELECT id, content, category, created_at, importance, last_accessed
            FROM notes
            ORDER BY {order}
            LIMIT %s
        """, (limit,))
        return [dict(row) for row in cur.fetchall()]

    def search_notes(self, query: str, limit: int = 50) -> List[Dict]:
        """Search notes by content (case-insensitive keyword match)."""
        cur = self.db.cursor(cursor_factory=psycopg2.extras.DictCursor)
        query_pattern = f"%{query.lower()}%"

        cur.execute("""
            SELECT id, content, category, created_at, importance
            FROM notes
            WHERE LOWER(content) LIKE %s
            ORDER BY created_at DESC
            LIMIT %s
        """, (query_pattern, limit))

        return [dict(row) for row in cur.fetchall()]

    def search_by_tags(self, tags: List[str], limit: int = 50) -> List[Dict]:
        """Search notes by tags."""
        cur = self.db.cursor(cursor_factory=psycopg2.extras.DictCursor)
        tags_lower = [t.lower() for t in tags]

        cur.execute("""
            SELECT DISTINCT n.id, n.content, n.category, n.created_at, n.importance
            FROM notes n
            INNER JOIN note_tags nt ON n.id = nt.note_id
            WHERE nt.tag = ANY(%s)
            ORDER BY n.created_at DESC
            LIMIT %s
        """, (tags_lower, limit))

        return [dict(row) for row in cur.fetchall()]

    def update_note(self, note_id: int, content: str = None, category: str = None, importance: int = None):
        """Update note content and metadata."""
        updates = []
        params = []

        if content is not None:
            updates.append("content = %s")
            params.append(content)
        if category is not None:
            updates.append("category = %s")
            params.append(category)
        if importance is not None:
            updates.append("importance = %s")
            params.append(importance)

        if not updates:
            return

        params.append(note_id)
        cur = self.db.cursor()
        cur.execute(f"""
            UPDATE notes
            SET {', '.join(updates)}, last_accessed = NOW()
            WHERE id = %s
        """, params)
        self.db.commit()
        log.info(f"Updated note {note_id}")

    def access_note(self, note_id: int):
        """Mark a note as accessed (update timestamp)."""
        cur = self.db.cursor()
        cur.execute("""
            UPDATE notes
            SET last_accessed = NOW()
            WHERE id = %s
        """, (note_id,))
        self.db.commit()

    def delete_note(self, note_id: int):
        """Delete a note and its tags."""
        cur = self.db.cursor()
        # Tags are deleted via CASCADE
        cur.execute("DELETE FROM notes WHERE id = %s", (note_id,))
        self.db.commit()
        log.info(f"Deleted note {note_id}")

    def get_categories(self) -> List[str]:
        """Get all unique note categories."""
        cur = self.db.cursor()
        cur.execute("SELECT DISTINCT category FROM notes ORDER BY category")
        return [row[0] for row in cur.fetchall()]

    def get_notes_statistics(self) -> Dict:
        """Get statistics about notes."""
        cur = self.db.cursor(cursor_factory=psycopg2.extras.DictCursor)

        cur.execute("""
            SELECT
                COUNT(*) as total_notes,
                COUNT(DISTINCT category) as unique_categories,
                MAX(created_at) as most_recent,
                AVG(LENGTH(content)) as avg_content_length
            FROM notes
        """)

        return dict(cur.fetchone())

    def auto_categorize(self, content: str) -> str:
        """Simple rule-based categorization (can be enhanced with Claude)."""
        content_lower = content.lower()

        # Simple keyword-based categorization
        if any(word in content_lower for word in ["shopping", "buy", "need", "get", "milk", "eggs"]):
            return "shopping"
        elif any(word in content_lower for word in ["work", "project", "assignment", "deadline", "task"]):
            return "work"
        elif any(word in content_lower for word in ["birthday", "anniversary", "remind", "call", "mom", "dad"]):
            return "personal"
        elif any(word in content_lower for word in ["idea", "thought", "interesting", "learned", "research"]):
            return "ideas"
        elif any(word in content_lower for word in ["health", "workout", "exercise", "diet", "sleep"]):
            return "health"
        else:
            return "general"

    def export_notes_text(self, notes: List[Dict] = None) -> str:
        """Export notes as formatted text."""
        if notes is None:
            notes = self.get_all_notes(limit=1000)

        lines = ["# All Notes\n"]

        for note in notes:
            lines.append(f"## {note['category'].title()}")
            lines.append(f"*Created: {note['created_at'].strftime('%Y-%m-%d')}*\n")
            lines.append(note['content'])
            lines.append("")

        return "\n".join(lines)
