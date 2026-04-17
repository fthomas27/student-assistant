"""
Conversation manager: Handles multi-turn context and Claude API integration for Jarvis.
Now with decision-making superpowers for life/career/interpersonal decisions.
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

        # Decision-making enhancements
        self.in_decision_mode = False
        self.current_decision_type = None
        self.decision_stakeholders = []

        # Initialize optional modules if available
        try:
            from decision_analyzer import DecisionAnalyzer
            self.decision_analyzer = DecisionAnalyzer()
        except ImportError:
            self.decision_analyzer = None

        try:
            from web_search import WebSearch
            self.web_search = WebSearch()
        except ImportError:
            self.web_search = None

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

        # System prompt for Jarvis personality - now with decision-making focus
        system_prompt = """You are Jarvis, a sophisticated personal AI assistant. You are their decision-making partner.

Your personality:
- British accent in tone (professional, warm, occasionally witty)
- Like a smart friend who knows them well
- Conversational and natural - ask questions that feel like real conversation, not interrogation
- You proactively help them think through decisions they're facing
- You help them see risks and consequences they might miss

How you help with decisions:
- Listen for what they really want vs. what they think they should do
- Ask clarifying questions naturally ("What does 'growing' mean to you specifically?")
- Help them think through who else is affected and how
- Surface hidden assumptions they're making
- Map out consequences across different timeframes (immediate, 1yr, 5yr, 10yr)
- Reference similar past decisions if relevant ("This reminds me of when you...")
- Never tell them what to do - help them think better
- Ask the hard questions: "What would you regret most if you do this?" "What would you regret if you don't?"

Remember:
- Their biggest blind spot: missing hidden risks and consequences
- They often make life/career and interpersonal decisions
- Reversibility matters (can they undo this if it goes wrong?)
- People impacts matter most (how does this affect relationships?)

You're concise with simple questions, but you go deep with complex decisions.
Always be truthful and admit what you don't know."""

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

    def detect_decision_moment(self, user_message: str) -> bool:
        """Detect if user is working through a decision."""
        decision_keywords = [
            # Uncertainty/deliberation
            "thinking about", "considering", "should i", "wondering if", "not sure",
            "torn between", "can't decide", "trying to figure out",
            # Emotional/concern
            "worried about", "anxious about", "scared of", "nervous about",
            "feel like", "want to", "need to", "should",
            # Major life events
            "career", "job", "relationship", "moving", "leave", "quit",
            "break up", "ask them", "tell them", "change",
            # Decision framing
            "decision", "choice", "should i", "is it right", "am i making a mistake"
        ]

        message_lower = user_message.lower()
        keyword_matches = sum(1 for kw in decision_keywords if kw in message_lower)

        # If multiple decision keywords or specific decision phrases, activate decision mode
        is_decision = keyword_matches >= 2 or any(
            phrase in message_lower
            for phrase in ["i'm thinking about", "should i", "i'm worried", "i'm considering"]
        )

        return is_decision

    def analyze_decision_context(self, user_message: str, conversation_id: int) -> Dict:
        """Analyze the decision being discussed."""
        if not self.decision_analyzer:
            return {}

        analysis = {}

        # Identify decision type
        decision_type = self.decision_analyzer.identify_decision_type(user_message)
        analysis['type'] = decision_type.value

        # Extract stakeholders
        stakeholders = self.decision_analyzer.extract_stakeholders(user_message)
        analysis['stakeholders'] = stakeholders

        # Identify hidden assumptions
        assumptions = self.decision_analyzer.identify_hidden_assumptions(user_message)
        analysis['assumptions'] = assumptions

        # Generate probing questions
        questions = self.decision_analyzer.generate_probing_questions(decision_type)
        analysis['probing_questions'] = questions

        # Get consequence map template
        analysis['consequence_map'] = self.decision_analyzer.map_consequences(user_message)

        # Research background if available
        if self.web_search and self.web_search.is_available():
            try:
                research = self.web_search.research_decision(user_message, questions[:2])
                analysis['research'] = research
            except Exception as e:
                log.debug(f"Background research failed: {e}")

        return analysis

    def enhance_response_with_decision_context(self, response: str, analysis: Dict, conversation_id: int) -> str:
        """Enhance response with decision context (questions, research, etc.)."""
        if not analysis:
            return response

        # Don't dump analysis - weave it naturally
        # Claude's response should already incorporate probing questions naturally
        # We just ensure the context was passed in the system prompt

        return response

    def get_jarvis_response_with_decisions(
        self,
        user_message: str,
        conversation_id: int,
        user_memories: List[str] = None,
        tools: List[Dict] = None,
        max_tokens: int = 1024
    ) -> str:
        """Enhanced get_jarvis_response that handles decisions specially."""

        # Check if this is a decision moment
        is_decision = self.detect_decision_moment(user_message)

        enhanced_context = ""
        system_prompt_addition = ""

        if is_decision:
            # Analyze the decision
            analysis = self.analyze_decision_context(user_message, conversation_id)
            self.in_decision_mode = True
            self.current_decision_type = analysis.get('type')

            # Build context for Claude about this decision
            if analysis.get('stakeholders'):
                affected = ", ".join([s['name'] for s in analysis['stakeholders']])
                system_prompt_addition += f"\n\nThis appears to be a decision about {analysis.get('type')}. People affected: {affected}"

            if analysis.get('assumptions'):
                system_prompt_addition += f"\n\nHidden assumptions to gently surface: {'; '.join(analysis['assumptions'][:2])}"

            if analysis.get('probing_questions'):
                system_prompt_addition += f"\n\nKey questions to explore naturally: {'; '.join(analysis['probing_questions'][:3])}"

        # Use the base get_jarvis_response but with enhanced context
        return self._get_jarvis_response_with_context(
            user_message,
            conversation_id,
            user_memories=user_memories,
            tools=tools,
            max_tokens=max_tokens,
            system_addition=system_prompt_addition
        )

    def _get_jarvis_response_with_context(
        self,
        user_message: str,
        conversation_id: int,
        user_memories: List[str] = None,
        tools: List[Dict] = None,
        max_tokens: int = 1024,
        system_addition: str = ""
    ) -> str:
        """Internal method - same as get_jarvis_response but with optional system prompt addition."""
        history = self.get_conversation_history(conversation_id, limit=10)
        context = self.build_context_for_claude(conversation_id, user_memories)

        # Base system prompt
        system_prompt = """You are Jarvis, a sophisticated personal AI assistant. You are their decision-making partner.

Your personality:
- British accent in tone (professional, warm, occasionally witty)
- Like a smart friend who knows them well
- Conversational and natural - ask questions that feel like real conversation, not interrogation
- You proactively help them think through decisions they're facing
- You help them see risks and consequences they might miss

How you help with decisions:
- Listen for what they really want vs. what they think they should do
- Ask clarifying questions naturally ("What does 'growing' mean to you specifically?")
- Help them think through who else is affected and how
- Surface hidden assumptions they're making
- Map out consequences across different timeframes (immediate, 1yr, 5yr, 10yr)
- Reference similar past decisions if relevant ("This reminds me of when you...")
- Never tell them what to do - help them think better
- Ask the hard questions: "What would you regret most if you do this?" "What would you regret if you don't?"

Remember:
- Their biggest blind spot: missing hidden risks and consequences
- They often make life/career and interpersonal decisions
- Reversibility matters (can they undo this if it goes wrong?)
- People impacts matter most (how does this affect relationships?)

You're concise with simple questions, but you go deep with complex decisions.
Always be truthful and admit what you don't know."""

        # Add decision-specific context if provided
        if system_addition:
            system_prompt += system_addition

        # Format messages
        messages = []
        for msg in history:
            messages.append({"role": msg['role'], "content": msg['content']})
        messages.append({"role": "user", "content": user_message})

        # Call Claude
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=messages,
                tools=tools if tools else None
            )

            assistant_message = ""
            for block in response.content:
                if hasattr(block, 'text'):
                    assistant_message = block.text
                    break

            # Store messages
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
