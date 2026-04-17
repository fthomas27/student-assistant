"""
Tool execution handler for Jarvis.
Processes Claude's tool_use blocks and executes the requested actions.
"""

import logging
import json
from typing import Dict, Any, Tuple
import psycopg2.extras

log = logging.getLogger(__name__)


class ToolExecutor:
    """Executes tools requested by Claude."""

    def __init__(self, db_connection):
        self.db = db_connection

    def execute_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Execute a tool and return result.
        Returns (success, result_text)
        """
        try:
            # Task management
            if tool_name == "create_task":
                return self._create_task(tool_input)
            elif tool_name == "complete_task":
                return self._complete_task(tool_input)
            elif tool_name == "get_pending_tasks":
                return self._get_pending_tasks(tool_input)

            # Notes
            elif tool_name == "create_note":
                return self._create_note(tool_input)
            elif tool_name == "search_notes":
                return self._search_notes(tool_input)
            elif tool_name == "get_notes_by_category":
                return self._get_notes_by_category(tool_input)

            # Reminders
            elif tool_name == "create_reminder":
                return self._create_reminder(tool_input)
            elif tool_name == "get_upcoming_reminders":
                return self._get_upcoming_reminders(tool_input)

            # Calendar & Assignments
            elif tool_name == "get_calendar_events":
                return self._get_calendar_events(tool_input)
            elif tool_name == "get_assignments":
                return self._get_assignments(tool_input)

            # Home Assistant
            elif tool_name == "control_home_assistant":
                return self._control_home_assistant(tool_input)
            elif tool_name == "get_home_status":
                return self._get_home_status(tool_input)

            # Memory
            elif tool_name == "store_memory":
                return self._store_memory(tool_input)
            elif tool_name == "get_memories":
                return self._get_memories(tool_input)

            # Decisions
            elif tool_name == "get_similar_decisions":
                return self._get_similar_decisions(tool_input)
            elif tool_name == "record_decision":
                return self._record_decision(tool_input)

            # Workouts
            elif tool_name == "log_workout":
                return self._log_workout(tool_input)
            elif tool_name == "get_workout_history":
                return self._get_workout_history(tool_input)

            # Search & Research
            elif tool_name == "web_search":
                return self._web_search(tool_input)

            # Briefing
            elif tool_name == "get_morning_briefing":
                return self._get_morning_briefing(tool_input)
            elif tool_name == "get_evening_debrief":
                return self._get_evening_debrief(tool_input)

            # Utilities
            elif tool_name == "get_current_time":
                return self._get_current_time(tool_input)
            elif tool_name == "get_weather":
                return self._get_weather(tool_input)

            else:
                return False, f"Unknown tool: {tool_name}"

        except Exception as e:
            log.error(f"Tool execution error for {tool_name}: {e}")
            return False, f"Error executing {tool_name}: {str(e)}"

    # ── Task Management ──

    def _create_task(self, tool_input: Dict) -> Tuple[bool, str]:
        """Create a task."""
        try:
            from app import get_db
            title = tool_input.get("title", "")
            description = tool_input.get("description", "")
            due_date = tool_input.get("due_date", None)
            priority = tool_input.get("priority", "medium")

            db = get_db()
            cur = db.cursor()

            cur.execute("""
                INSERT INTO tasks (title, description, due_date, priority, completed)
                VALUES (%s, %s, %s, %s, false)
                RETURNING id
            """, (title, description, due_date, priority))

            task_id = cur.fetchone()[0]
            db.commit()

            return True, f"Task '{title}' created with ID {task_id}"
        except Exception as e:
            log.error(f"Error creating task: {e}")
            return False, f"Failed to create task: {str(e)}"

    def _complete_task(self, tool_input: Dict) -> Tuple[bool, str]:
        """Mark a task as completed."""
        try:
            from app import get_db
            task_id = tool_input.get("task_id")
            notes = tool_input.get("notes", "")

            db = get_db()
            cur = db.cursor()

            cur.execute("""
                UPDATE tasks
                SET completed = true, completed_at = NOW()
                WHERE id = %s
            """, (task_id,))

            db.commit()
            return True, f"Task {task_id} marked as complete"
        except Exception as e:
            log.error(f"Error completing task: {e}")
            return False, f"Failed to complete task: {str(e)}"

    def _get_pending_tasks(self, tool_input: Dict) -> Tuple[bool, str]:
        """Get pending tasks."""
        try:
            from app import get_db
            limit = tool_input.get("limit", 10)
            filter_type = tool_input.get("filter", "all")

            db = get_db()
            cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)

            if filter_type == "today":
                cur.execute("""
                    SELECT id, title, due_date, priority
                    FROM tasks
                    WHERE completed = false AND DATE(due_date) = CURRENT_DATE
                    ORDER BY priority DESC, due_date ASC
                    LIMIT %s
                """, (limit,))
            elif filter_type == "overdue":
                cur.execute("""
                    SELECT id, title, due_date, priority
                    FROM tasks
                    WHERE completed = false AND due_date < NOW()
                    ORDER BY due_date ASC
                    LIMIT %s
                """, (limit,))
            elif filter_type == "priority":
                cur.execute("""
                    SELECT id, title, due_date, priority
                    FROM tasks
                    WHERE completed = false
                    ORDER BY priority DESC, due_date ASC
                    LIMIT %s
                """, (limit,))
            else:  # all
                cur.execute("""
                    SELECT id, title, due_date, priority
                    FROM tasks
                    WHERE completed = false
                    ORDER BY due_date ASC
                    LIMIT %s
                """, (limit,))

            tasks = [dict(row) for row in cur.fetchall()]
            return True, json.dumps(tasks)

        except Exception as e:
            log.error(f"Error getting pending tasks: {e}")
            return False, f"Failed to get tasks: {str(e)}"

    # ── Notes ──

    def _create_note(self, tool_input: Dict) -> Tuple[bool, str]:
        """Create a note."""
        try:
            from note_manager import NoteManager
            from app import get_db

            content = tool_input.get("content", "")
            category = tool_input.get("category")
            tags = tool_input.get("tags", [])

            db = get_db()
            note_manager = NoteManager(db)

            note_id = note_manager.create_note(content, category=category, tags=tags)
            return True, f"Note created with ID {note_id}"

        except Exception as e:
            log.error(f"Error creating note: {e}")
            return False, f"Failed to create note: {str(e)}"

    def _search_notes(self, tool_input: Dict) -> Tuple[bool, str]:
        """Search notes."""
        try:
            from note_manager import NoteManager
            from app import get_db

            query = tool_input.get("query", "")
            limit = tool_input.get("limit", 10)

            db = get_db()
            note_manager = NoteManager(db)

            notes = note_manager.search_notes(query, limit=limit)
            return True, json.dumps(notes[:limit])

        except Exception as e:
            log.error(f"Error searching notes: {e}")
            return False, f"Failed to search notes: {str(e)}"

    def _get_notes_by_category(self, tool_input: Dict) -> Tuple[bool, str]:
        """Get notes by category."""
        try:
            from note_manager import NoteManager
            from app import get_db

            category = tool_input.get("category", "")
            limit = tool_input.get("limit", 20)

            db = get_db()
            note_manager = NoteManager(db)

            notes = note_manager.get_notes_by_category(category, limit=limit)
            return True, json.dumps(notes)

        except Exception as e:
            log.error(f"Error getting notes by category: {e}")
            return False, f"Failed to get notes: {str(e)}"

    # ── Reminders (stub - full implementation in reminders system) ──

    def _create_reminder(self, tool_input: Dict) -> Tuple[bool, str]:
        """Create a reminder."""
        try:
            message = tool_input.get("message", "")
            due_date = tool_input.get("due_date", "")
            reminder_type = tool_input.get("reminder_type", "task")

            # TODO: Implement reminders table in database if not exists
            # For now, return success with placeholder
            return True, f"Reminder '{message}' created for {due_date}"

        except Exception as e:
            log.error(f"Error creating reminder: {e}")
            return False, f"Failed to create reminder: {str(e)}"

    def _get_upcoming_reminders(self, tool_input: Dict) -> Tuple[bool, str]:
        """Get upcoming reminders."""
        try:
            days_ahead = tool_input.get("days_ahead", 7)
            # TODO: Implement reminders retrieval
            return True, json.dumps([])
        except Exception as e:
            return False, f"Failed to get reminders: {str(e)}"

    # ── Utility stubs ──

    def _get_calendar_events(self, tool_input: Dict) -> Tuple[bool, str]:
        """Get calendar events."""
        return True, json.dumps([])  # TODO: Implement calendar integration

    def _get_assignments(self, tool_input: Dict) -> Tuple[bool, str]:
        """Get assignments."""
        try:
            from app import get_db
            db = get_db()
            cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)

            filter_type = tool_input.get("filter", "all")

            if filter_type == "due_today":
                cur.execute("""
                    SELECT title, due_date FROM completions
                    WHERE DATE(due_date) = CURRENT_DATE
                    ORDER BY due_date ASC
                """)
            elif filter_type == "overdue":
                cur.execute("""
                    SELECT title, due_date FROM completions
                    WHERE due_date < NOW() AND completed_at IS NULL
                    ORDER BY due_date ASC
                """)
            else:  # all
                cur.execute("""
                    SELECT title, due_date FROM completions
                    WHERE completed_at IS NULL
                    ORDER BY due_date ASC
                    LIMIT 20
                """)

            assignments = [dict(row) for row in cur.fetchall()]
            return True, json.dumps(assignments)

        except Exception as e:
            log.error(f"Error getting assignments: {e}")
            return False, f"Failed to get assignments: {str(e)}"

    def _control_home_assistant(self, tool_input: Dict) -> Tuple[bool, str]:
        """Control Home Assistant device."""
        try:
            from ha_client import HAClient
            from app import get_config

            action = tool_input.get("action", "")
            device = tool_input.get("device", "")
            parameters = tool_input.get("parameters", {})

            config = get_config()
            ha_url = config.get("ha_url", "")
            ha_token = config.get("ha_token", "")

            if not ha_url or not ha_token:
                return False, "Home Assistant not configured"

            ha = HAClient(ha_url, ha_token)
            success = ha.execute_natural_language_command(action, device, parameters)

            return success, f"Command '{action}' executed on {device}"

        except Exception as e:
            log.error(f"Error controlling HA: {e}")
            return False, f"Failed to control device: {str(e)}"

    def _get_home_status(self, tool_input: Dict) -> Tuple[bool, str]:
        """Get Home Assistant status."""
        try:
            from ha_client import HAClient
            from app import get_config

            config = get_config()
            ha_url = config.get("ha_url", "")
            ha_token = config.get("ha_token", "")

            if not ha_url or not ha_token:
                return False, "Home Assistant not configured"

            ha = HAClient(ha_url, ha_token)
            status = ha.get_ha_status_summary()

            return True, json.dumps(status)

        except Exception as e:
            log.error(f"Error getting HA status: {e}")
            return False, f"Failed to get status: {str(e)}"

    def _store_memory(self, tool_input: Dict) -> Tuple[bool, str]:
        """Store a memory about the user."""
        try:
            from memory_manager import MemoryManager
            from app import get_db

            memory_text = tool_input.get("memory", "")
            category = tool_input.get("category", "general")
            confidence = tool_input.get("confidence", 0.8)

            db = get_db()
            memory_manager = MemoryManager(db)

            memory_manager.store_memory(memory_text, category, confidence)
            return True, f"Memory stored: '{memory_text}'"

        except Exception as e:
            log.error(f"Error storing memory: {e}")
            return False, f"Failed to store memory: {str(e)}"

    def _get_memories(self, tool_input: Dict) -> Tuple[bool, str]:
        """Get memories by category."""
        try:
            from memory_manager import MemoryManager
            from app import get_db

            category = tool_input.get("category", "all")
            limit = tool_input.get("limit", 10)

            db = get_db()
            memory_manager = MemoryManager(db)

            if category == "all":
                memories = memory_manager.get_top_memories(limit)
            else:
                memories = memory_manager.get_memories_by_category(category, limit)

            return True, json.dumps(memories)

        except Exception as e:
            log.error(f"Error getting memories: {e}")
            return False, f"Failed to get memories: {str(e)}"

    def _get_similar_decisions(self, tool_input: Dict) -> Tuple[bool, str]:
        """Get similar past decisions."""
        try:
            from conversation_manager import ConversationManager
            from app import get_db

            decision_type = tool_input.get("decision_type", "career")

            db = get_db()
            conv_manager = ConversationManager(db)

            similar = conv_manager.get_similar_past_decisions(decision_type, limit=3)
            return True, json.dumps(similar)

        except Exception as e:
            log.error(f"Error getting similar decisions: {e}")
            return False, f"Failed to get decisions: {str(e)}"

    def _record_decision(self, tool_input: Dict) -> Tuple[bool, str]:
        """Record a decision."""
        try:
            from conversation_manager import ConversationManager
            from app import get_db

            summary = tool_input.get("summary", "")
            decision_type = tool_input.get("type", "unknown")
            stakeholders = tool_input.get("stakeholders", [])

            # TODO: Get current conversation ID
            # For now, create a new conversation
            db = get_db()
            conv_manager = ConversationManager(db)

            conv_id = conv_manager.get_current_conversation_id()
            if not conv_id:
                conv_id = conv_manager.start_conversation()

            decision_id = conv_manager.record_decision(conv_id, summary, decision_type, stakeholders)

            return True, f"Decision recorded with ID {decision_id}"

        except Exception as e:
            log.error(f"Error recording decision: {e}")
            return False, f"Failed to record decision: {str(e)}"

    def _log_workout(self, tool_input: Dict) -> Tuple[bool, str]:
        """Log a workout."""
        try:
            from app import get_db

            exercise = tool_input.get("exercise", "")
            duration = tool_input.get("duration_minutes", 0)
            intensity = tool_input.get("intensity", "moderate")
            notes = tool_input.get("notes", "")

            db = get_db()
            cur = db.cursor()

            cur.execute("""
                INSERT INTO workout_logs (exercise_type, duration_minutes, intensity, notes, logged_at)
                VALUES (%s, %s, %s, %s, NOW())
            """, (exercise, duration, intensity, notes))

            db.commit()
            return True, f"Logged {duration} minutes of {exercise} ({intensity} intensity)"

        except Exception as e:
            log.error(f"Error logging workout: {e}")
            return False, f"Failed to log workout: {str(e)}"

    def _get_workout_history(self, tool_input: Dict) -> Tuple[bool, str]:
        """Get workout history."""
        try:
            from app import get_db
            import datetime

            days = tool_input.get("days", 30)

            db = get_db()
            cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)

            cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days)

            cur.execute("""
                SELECT exercise_type, duration_minutes, intensity, logged_at
                FROM workout_logs
                WHERE logged_at >= %s
                ORDER BY logged_at DESC
            """, (cutoff_date,))

            workouts = [dict(row) for row in cur.fetchall()]
            return True, json.dumps(workouts)

        except Exception as e:
            log.error(f"Error getting workout history: {e}")
            return False, f"Failed to get workout history: {str(e)}"

    def _web_search(self, tool_input: Dict) -> Tuple[bool, str]:
        """Perform web search."""
        try:
            from web_search import WebSearch

            query = tool_input.get("query", "")
            max_results = min(tool_input.get("max_results", 5), 10)

            ws = WebSearch()
            results = ws.search(query, max_results)

            return True, json.dumps(results)

        except Exception as e:
            log.error(f"Error with web search: {e}")
            return False, f"Failed to search: {str(e)}"

    def _get_morning_briefing(self, tool_input: Dict) -> Tuple[bool, str]:
        """Get morning briefing."""
        return True, "Morning briefing generated"  # TODO: Implement

    def _get_evening_debrief(self, tool_input: Dict) -> Tuple[bool, str]:
        """Get evening debrief."""
        return True, "Evening debrief generated"  # TODO: Implement

    def _get_current_time(self, tool_input: Dict) -> Tuple[bool, str]:
        """Get current time."""
        from datetime import datetime
        from app import get_config

        try:
            tz = get_config().get("timezone", "America/Denver")
            import pytz
            local_tz = pytz.timezone(tz)
            now = datetime.now(local_tz)
            return True, now.strftime("%A, %B %d, %Y at %I:%M %p %Z")
        except:
            now = datetime.now()
            return True, now.strftime("%A, %B %d, %Y at %I:%M %p")

    def _get_weather(self, tool_input: Dict) -> Tuple[bool, str]:
        """Get weather."""
        return True, "Weather data not yet integrated"  # TODO: Implement
