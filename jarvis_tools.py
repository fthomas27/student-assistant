"""
Claude tool definitions for Jarvis.
Allows Claude to execute structured actions within conversations.
"""

import json
from typing import List, Dict, Any


def get_jarvis_tools() -> List[Dict[str, Any]]:
    """
    Get all tools available to Claude for Jarvis to use.
    These tools are passed to the Claude API for tool_use capability.
    """
    return [
        # ── Task Management ──
        {
            "name": "create_task",
            "description": "Create a new task for the user",
            "input_schema": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Task title"
                    },
                    "description": {
                        "type": "string",
                        "description": "Task description (optional)"
                    },
                    "due_date": {
                        "type": "string",
                        "description": "Due date in YYYY-MM-DD format (optional)"
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "description": "Task priority (optional)"
                    }
                },
                "required": ["title"]
            }
        },
        {
            "name": "complete_task",
            "description": "Mark a task as completed",
            "input_schema": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "integer",
                        "description": "ID of the task to complete"
                    },
                    "notes": {
                        "type": "string",
                        "description": "Completion notes (optional)"
                    }
                },
                "required": ["task_id"]
            }
        },
        {
            "name": "get_pending_tasks",
            "description": "Get user's pending tasks",
            "input_schema": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max number of tasks to return (default: 10)"
                    },
                    "filter": {
                        "type": "string",
                        "enum": ["all", "today", "overdue", "priority"],
                        "description": "Filter tasks (default: all)"
                    }
                }
            }
        },

        # ── Notes ──
        {
            "name": "create_note",
            "description": "Create a voice or text note",
            "input_schema": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "Note content"
                    },
                    "category": {
                        "type": "string",
                        "description": "Note category (auto-categorized if omitted)"
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional tags for organization"
                    }
                },
                "required": ["content"]
            }
        },
        {
            "name": "search_notes",
            "description": "Search user's notes by query",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default: 10)"
                    }
                },
                "required": ["query"]
            }
        },
        {
            "name": "get_notes_by_category",
            "description": "Get notes by category",
            "input_schema": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Note category (work, personal, ideas, shopping, health, etc.)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default: 20)"
                    }
                },
                "required": ["category"]
            }
        },

        # ── Reminders ──
        {
            "name": "create_reminder",
            "description": "Create a reminder for the user",
            "input_schema": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Reminder message"
                    },
                    "due_date": {
                        "type": "string",
                        "description": "Due date in YYYY-MM-DD format"
                    },
                    "due_time": {
                        "type": "string",
                        "description": "Due time in HH:MM format (24-hour)"
                    },
                    "reminder_type": {
                        "type": "string",
                        "enum": ["call", "email", "meeting", "birthday", "anniversary", "task"],
                        "description": "Type of reminder"
                    }
                },
                "required": ["message", "due_date"]
            }
        },
        {
            "name": "get_upcoming_reminders",
            "description": "Get upcoming reminders",
            "input_schema": {
                "type": "object",
                "properties": {
                    "days_ahead": {
                        "type": "integer",
                        "description": "Look ahead N days (default: 7)"
                    }
                }
            }
        },

        # ── Calendar ──
        {
            "name": "get_calendar_events",
            "description": "Get user's calendar events",
            "input_schema": {
                "type": "object",
                "properties": {
                    "filter": {
                        "type": "string",
                        "enum": ["today", "tomorrow", "week", "upcoming"],
                        "description": "Time filter (default: upcoming)"
                    }
                }
            }
        },
        {
            "name": "get_assignments",
            "description": "Get user's assignments and their due dates",
            "input_schema": {
                "type": "object",
                "properties": {
                    "filter": {
                        "type": "string",
                        "enum": ["all", "due_today", "due_this_week", "overdue"],
                        "description": "Assignment filter (default: all)"
                    }
                }
            }
        },

        # ── Home Assistant Control ──
        {
            "name": "control_home_assistant",
            "description": "Control a smart home device via Home Assistant",
            "input_schema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "Action to perform (e.g., 'turn on', 'turn off', 'set brightness')"
                    },
                    "device": {
                        "type": "string",
                        "description": "Device name or entity (e.g., 'office light', 'bedroom fan')"
                    },
                    "parameters": {
                        "type": "object",
                        "description": "Additional parameters (brightness: 0-100, temperature, etc.)"
                    }
                },
                "required": ["action", "device"]
            }
        },
        {
            "name": "get_home_status",
            "description": "Get current smart home status summary",
            "input_schema": {
                "type": "object",
                "properties": {
                    "include": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific entities to check (e.g., ['lights', 'doors', 'climate'])"
                    }
                }
            }
        },

        # ── Conversation & Memory ──
        {
            "name": "store_memory",
            "description": "Store a fact about the user for future reference",
            "input_schema": {
                "type": "object",
                "properties": {
                    "memory": {
                        "type": "string",
                        "description": "The fact to remember (e.g., 'User prefers coffee at 7am')"
                    },
                    "category": {
                        "type": "string",
                        "description": "Memory category (preferences, habits, goals, family, work, etc.)"
                    },
                    "confidence": {
                        "type": "number",
                        "description": "Confidence score 0-1 (1.0 = very confident)"
                    }
                },
                "required": ["memory", "category"]
            }
        },
        {
            "name": "get_memories",
            "description": "Retrieve user memories by category or context",
            "input_schema": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Memory category to retrieve"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max memories to return (default: 10)"
                    }
                }
            }
        },

        # ── Decision Support ──
        {
            "name": "get_similar_decisions",
            "description": "Get similar past decisions this user made to learn from patterns",
            "input_schema": {
                "type": "object",
                "properties": {
                    "decision_type": {
                        "type": "string",
                        "enum": ["career", "relationship", "financial", "life_major", "interpersonal"],
                        "description": "Type of decision to find precedents for"
                    }
                },
                "required": ["decision_type"]
            }
        },
        {
            "name": "record_decision",
            "description": "Record a decision for future outcome tracking and learning",
            "input_schema": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Brief summary of the decision"
                    },
                    "type": {
                        "type": "string",
                        "enum": ["career", "relationship", "financial", "life_major", "interpersonal"],
                        "description": "Type of decision"
                    },
                    "stakeholders": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "People affected by this decision"
                    }
                },
                "required": ["summary", "type"]
            }
        },

        # ── Workouts & Health ──
        {
            "name": "log_workout",
            "description": "Log a workout session",
            "input_schema": {
                "type": "object",
                "properties": {
                    "exercise": {
                        "type": "string",
                        "description": "Type of exercise (running, swimming, strength, yoga, etc.)"
                    },
                    "duration_minutes": {
                        "type": "integer",
                        "description": "Duration in minutes"
                    },
                    "intensity": {
                        "type": "string",
                        "enum": ["light", "moderate", "intense"],
                        "description": "Workout intensity"
                    },
                    "notes": {
                        "type": "string",
                        "description": "Optional notes about the workout"
                    }
                },
                "required": ["exercise", "duration_minutes"]
            }
        },
        {
            "name": "get_workout_history",
            "description": "Get user's workout history and patterns",
            "input_schema": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Look back N days (default: 30)"
                    }
                }
            }
        },

        # ── Search & Research ──
        {
            "name": "web_search",
            "description": "Search the web for current information",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Max results to return (default: 5, max: 10)"
                    }
                },
                "required": ["query"]
            }
        },

        # ── Briefing & Daily ──
        {
            "name": "get_morning_briefing",
            "description": "Generate and speak the morning briefing",
            "input_schema": {
                "type": "object",
                "properties": {
                    "voice": {
                        "type": "boolean",
                        "description": "Synthesize to voice (default: true)"
                    }
                }
            }
        },
        {
            "name": "get_evening_debrief",
            "description": "Get evening summary and reflection",
            "input_schema": {
                "type": "object"
            }
        },

        # ── Time & Info ──
        {
            "name": "get_current_time",
            "description": "Get current time and date",
            "input_schema": {
                "type": "object"
            }
        },
        {
            "name": "get_weather",
            "description": "Get current weather and forecast",
            "input_schema": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "Location for weather (default: user's location)"
                    }
                }
            }
        }
    ]


def get_tool_by_name(name: str) -> Dict[str, Any]:
    """Get a specific tool definition by name."""
    tools = get_jarvis_tools()
    for tool in tools:
        if tool["name"] == name:
            return tool
    return None


def validate_tool_input(tool_name: str, input_dict: Dict[str, Any]) -> tuple[bool, str]:
    """
    Validate that tool input matches the schema.
    Returns (is_valid, error_message)
    """
    tool = get_tool_by_name(tool_name)
    if not tool:
        return False, f"Unknown tool: {tool_name}"

    schema = tool.get("input_schema", {})
    required = schema.get("required", [])
    properties = schema.get("properties", {})

    # Check required fields
    for req_field in required:
        if req_field not in input_dict:
            return False, f"Missing required field: {req_field}"

    # TODO: Add more schema validation (types, enums, etc.)

    return True, ""
