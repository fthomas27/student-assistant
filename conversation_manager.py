"""
Conversation manager: Handles multi-turn context and Claude API integration for Jarvis.
"""

import os
import json
import logging
import psycopg2
import psycopg2.extras
from datetime import datetime
from typing import Optional, Dict, List, Any
import anthropic

log = logging.getLogger(__name__)


class ConversationManager:
    """Manages conversation state and Claude API interactions."""

    def __init__(self, db_connection):
        self.db = db_connection
        self.client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        self.model = "claude-sonnet-4-6"
        self.current_conversation_id: Optional[int] = None
        self.current_exchanges = 0

    def start_conversation(self) -> int:
        """Start a new conversation session."""
        cur = self.db.cursor()
        cur.execute("""
            INSERT INTO conversations (created_at, total_exchanges)
            VALUES (NOW(), 0)
            RETURNING id
        """)
        conv_id = cur.fetchone()[0]
        self.db.commit()
        self.current_conversation_id = conv_id
        self.current_exchanges = 0
        log.info(f"Started conversation {conv_id}")
        return conv_id

    def get_current_conversation_id(self) -> Optional[int]:
        """Get the current conversation ID."""
        return self.current_conversation_id

    def get_conversation_history(self, conversation_id: int, limit: int = 10) -> List[Dict]:
        """Get conversation history as a list of message dicts."""
        cur = self.db.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("""
            SELECT role, content, created_at
            FROM messages
            WHERE conversation_id = %s
            ORDER BY created_at DESC
            LIMIT %s
        """, (conversation_id, limit))
        rows = cur.fetchall()
        # Reverse to chronological order
        return [dict(r) for r in reversed(rows)]

    def add_message(self, conversation_id: int, role: str, content: str, confidence: float = 1.0):
        """Add a message to the conversation."""
        cur = self.db.cursor()
        cur.execute("""
            INSERT INTO messages (conversation_id, role, content, confidence_score, created_at)
            VALUES (%s, %s, %s, %s, NOW())
        """, (conversation_id, role, content, confidence))
        self.db.commit()

    def build_context_for_claude(self, conversation_id: int, user_memories: List[str] = None) -> str:
        """Build context string for Claude with conversation history and memories."""
        history = self.get_conversation_history(conversation_id, limit=10)

        # Format conversation history
        context_lines = ["Recent conversation history:"]
        if history:
            for msg in history:
                role = msg['role'].upper()
                content = msg['content'][:200]  # Truncate long messages
                context_lines.append(f"{role}: {content}")
        else:
            context_lines.append("(No previous messages)")

        # Add user memories if available
        if user_memories:
            context_lines.append("\nUser facts and preferences:")
            for mem in user_memories:
                context_lines.append(f"- {mem}")

        return "\n".join(context_lines)

    def get_jarvis_response(
        self,
        user_message: str,
        conversation_id: int,
        user_memories: List[str] = None,
        tools: List[Dict] = None,
        max_tokens: int = 1024
    ) -> str:
        """Get a response from Claude with Jarvis personality."""
        # Get conversation history
        history = self.get_conversation_history(conversation_id, limit=10)

        # Build context
        context = self.build_context_for_claude(conversation_id, user_memories)

        # System prompt for Jarvis personality
        system_prompt = """You are Jarvis, a sophisticated and helpful personal AI assistant.
Your personality is:
- Professional but warm and friendly
- British accent in speech (even though this is text, maintain that tone)
- Helpful, proactive, and thoughtful
- Occasionally witty, but never forced or annoying
- Respectful of the user's time and preferences
- Good at remembering context from previous conversations

You run smart home devices via Home Assistant, manage tasks and calendar, and keep detailed notes.
You should be concise in responses (aim for 2-3 sentences for quick queries).
For complex queries, ask if the user wants extended details or offer to dive deeper.
Always be truthful and admit when you don't know something."""

        # Format messages for Claude
        messages = []

        # Add conversation history
        for msg in history:
            messages.append({
                "role": msg['role'],
                "content": msg['content']
            })

        # Add current user message
        messages.append({
            "role": "user",
            "content": user_message
        })

        # Call Claude API
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=messages,
                tools=tools if tools else None
            )

            # Extract text response
            assistant_message = ""
            for block in response.content:
                if hasattr(block, 'text'):
                    assistant_message = block.text
                    break

            # Add messages to database
            self.add_message(conversation_id, "user", user_message)
            self.add_message(conversation_id, "assistant", assistant_message)

            # Update exchange count
            cur = self.db.cursor()
            cur.execute("""
                UPDATE conversations
                SET total_exchanges = total_exchanges + 1
                WHERE id = %s
            """, (conversation_id,))
            self.db.commit()
            self.current_exchanges += 1

            return assistant_message

        except anthropic.APIError as e:
            log.error(f"Claude API error: {e}")
            raise

    def extract_memories(self, conversation_id: int) -> List[Dict]:
        """Extract structured facts from conversation using Claude."""
        history = self.get_conversation_history(conversation_id)

        if not history or len(history) < 2:
            return []

        # Format conversation for memory extraction
        conv_text = "\n".join([
            f"{msg['role'].upper()}: {msg['content']}"
            for msg in history
        ])

        extraction_prompt = f"""Extract key facts about the user from this conversation.
Focus on:
- Preferences (likes, dislikes, preferences)
- Habits (routines, patterns)
- Interests (topics they care about)
- Family/social info
- Goals
- Work patterns

Return as JSON array with objects: {{"fact": "...", "category": "...", "confidence": 0.0-1.0}}

Conversation:
{conv_text}

Return ONLY the JSON array, no other text."""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{"role": "user", "content": extraction_prompt}]
            )

            # Parse JSON response
            response_text = response.content[0].text
            memories = json.loads(response_text)
            return memories if isinstance(memories, list) else []

        except (json.JSONDecodeError, anthropic.APIError) as e:
            log.error(f"Memory extraction error: {e}")
            return []

    def store_extracted_memories(self, extracted_memories: List[Dict]):
        """Store extracted memories in database."""
        if not extracted_memories:
            return

        cur = self.db.cursor()
        for memory in extracted_memories:
            fact = memory.get("fact", "")
            category = memory.get("category", "general")
            confidence = memory.get("confidence", 0.8)

            if fact:
                cur.execute("""
                    INSERT INTO user_memories (memory_text, category, confidence, created_at)
                    VALUES (%s, %s, %s, NOW())
                """, (fact, category, confidence))

        self.db.commit()
        log.info(f"Stored {len(extracted_memories)} extracted memories")

    def end_conversation(self, conversation_id: int):
        """End the current conversation."""
        cur = self.db.cursor()
        cur.execute("""
            UPDATE conversations
            SET ended_at = NOW()
            WHERE id = %s
        """, (conversation_id,))
        self.db.commit()

        # Extract and store memories
        memories = self.extract_memories(conversation_id)
        self.store_extracted_memories(memories)

        log.info(f"Ended conversation {conversation_id} with {self.current_exchanges} exchanges")

    def get_relevant_memories(self, query: str, limit: int = 5) -> List[str]:
        """Get relevant memories for current context (simple keyword match)."""
        cur = self.db.cursor(cursor_factory=psycopg2.extras.DictCursor)

        # Simple keyword search in memories
        query_terms = query.lower().split()
        cur.execute("""
            SELECT memory_text, usage_count
            FROM user_memories
            ORDER BY usage_count DESC, created_at DESC
            LIMIT %s
        """, (limit,))

        memories = [dict(row)['memory_text'] for row in cur.fetchall()]

        # Mark memories as used
        if memories:
            cur.execute("""
                UPDATE user_memories
                SET usage_count = usage_count + 1, last_used = NOW()
                WHERE memory_text = ANY(%s)
            """, (memories,))
            self.db.commit()

        return memories
