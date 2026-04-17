"""
Voice API endpoints for Jarvis voice assistant.
Exposed via Flask in main app.py
"""

import logging
import os
import json
from flask import Blueprint, request, jsonify
from conversation_manager import ConversationManager
from memory_manager import MemoryManager
from note_manager import NoteManager
from ha_client import HAClient
from stt_handler import STTHandler
from tts_handler import TTSHandler

log = logging.getLogger(__name__)

voice_bp = Blueprint('voice', __name__, url_prefix='/api/voice')


class VoiceAPI:
    """Voice API handler."""

    def __init__(self, db_connection):
        """Initialize voice API with database connection."""
        self.db = db_connection
        self.conv_manager = ConversationManager(db_connection)
        self.memory_manager = MemoryManager(db_connection)
        self.note_manager = NoteManager(db_connection)
        self.stt = STTHandler()
        self.tts = TTSHandler()
        self.ha = self._init_ha()

    def _init_ha(self):
        """Initialize Home Assistant client if configured."""
        try:
            from app import get_config
            config = get_config()
            ha_url = config.get("ha_url")
            ha_token = config.get("ha_token")

            if ha_url and ha_token:
                return HAClient(ha_url, ha_token)
        except Exception as e:
            log.warning(f"Failed to initialize HA client: {e}")
        return None

    def process_voice_command(self, audio_data: bytes) -> dict:
        """
        Process a voice command from start to finish.

        Args:
            audio_data: Raw audio bytes

        Returns:
            Dict with transcription, response, and audio
        """
        result = {
            "success": False,
            "transcription": "",
            "response": "",
            "audio": None,
            "confidence": 0.0
        }

        # Step 1: Transcribe audio
        text, confidence = self.stt.transcribe_audio(audio_data)
        if not text:
            result["error"] = "Failed to transcribe audio"
            return result

        result["transcription"] = text
        result["confidence"] = confidence

        # Step 2: Get or create conversation
        conv_id = self.conv_manager.get_current_conversation_id()
        if not conv_id:
            conv_id = self.conv_manager.start_conversation()

        # Step 3: Get relevant memories
        keywords = text.split()
        memories = self.memory_manager.suggest_memories_for_context(keywords, limit=5)

        # Step 4: Get response from Claude (with decision-making superpowers)
        try:
            response = self.conv_manager.get_jarvis_response_with_decisions(
                text,
                conv_id,
                user_memories=memories
            )
            result["response"] = response
        except Exception as e:
            log.error(f"Claude error: {e}")
            result["error"] = f"Claude API error: {e}"
            return result

        # Step 5: Check if response contains action (home assistant)
        if self.ha and ("turn" in response.lower() or "light" in response.lower()):
            self._handle_ha_action(text, response)

        # Step 6: Synthesize response to audio
        try:
            audio = self.tts.synthesize(response)
            if audio:
                result["audio"] = audio  # Would be base64 encoded for JSON transmission
        except Exception as e:
            log.error(f"TTS error: {e}")
            # Continue without audio

        result["success"] = True
        return result

    def _handle_ha_action(self, command: str, response: str):
        """Parse command and execute Home Assistant action if needed."""
        if not self.ha:
            return

        try:
            # Very simple pattern matching for HA commands
            if "turn on" in command.lower() or "on" in command.lower():
                if "light" in command.lower():
                    # Extract entity name - very naive parsing
                    # In production, use Claude to extract intent properly
                    lights = self.ha.get_lights()
                    if lights:
                        self.ha.turn_on_light(lights[0]['entity_id'])
                elif "switch" in command.lower():
                    switches = self.ha.get_switches()
                    if switches:
                        self.ha.call_service("switch", "turn_on", {"entity_id": switches[0]['entity_id']})

            elif "turn off" in command.lower() or "off" in command.lower():
                if "light" in command.lower():
                    lights = self.ha.get_lights()
                    if lights:
                        self.ha.turn_off_light(lights[0]['entity_id'])
                elif "switch" in command.lower():
                    switches = self.ha.get_switches()
                    if switches:
                        self.ha.call_service("switch", "turn_off", {"entity_id": switches[0]['entity_id']})

        except Exception as e:
            log.error(f"HA action error: {e}")

    def create_note_from_command(self, text: str) -> dict:
        """Create a note from a voice command."""
        # Extract note content (remove "note that" or similar prefixes)
        prefixes = ["note that", "note:", "create a note", "add note"]
        content = text
        for prefix in prefixes:
            if content.lower().startswith(prefix):
                content = content[len(prefix):].strip()
                break

        # Auto-categorize
        category = self.note_manager.auto_categorize(content)

        # Create note
        note_id = self.note_manager.create_note(content, category=category)

        return {
            "success": True,
            "note_id": note_id,
            "category": category,
            "content": content
        }

    def search_notes_command(self, query: str) -> dict:
        """Search notes and return results."""
        notes = self.note_manager.search_notes(query, limit=10)

        result_text = f"Found {len(notes)} notes about '{query}':\n"
        for note in notes[:3]:  # Read first 3
            result_text += f"- {note['content'][:50]}...\n"

        return {
            "success": True,
            "query": query,
            "count": len(notes),
            "results": notes,
            "summary": result_text
        }

    def get_briefing_command(self) -> dict:
        """Generate and return morning briefing."""
        # This would integrate with existing briefing logic
        try:
            conv_id = self.conv_manager.get_current_conversation_id()
            if not conv_id:
                conv_id = self.conv_manager.start_conversation()

            # Request briefing from Claude
            briefing = self.conv_manager.get_jarvis_response_with_decisions(
                "Give me my morning briefing. Include my calendar, tasks, and any important reminders.",
                conv_id,
                user_memories=self.memory_manager.get_top_memories(5)
            )

            # Synthesize to audio
            audio = self.tts.synthesize(briefing)

            return {
                "success": True,
                "briefing": briefing,
                "audio": audio
            }

        except Exception as e:
            log.error(f"Briefing error: {e}")
            return {"success": False, "error": str(e)}

    def end_conversation(self):
        """End current conversation and extract memories."""
        conv_id = self.conv_manager.get_current_conversation_id()
        if conv_id:
            self.conv_manager.end_conversation(conv_id)
            self.conv_manager.current_conversation_id = None
            return {"success": True, "conversation_id": conv_id}
        return {"success": False, "error": "No active conversation"}


def create_voice_routes(app, db_connection):
    """Create voice-related Flask routes."""
    api = VoiceAPI(db_connection)

    @app.route('/api/voice/command', methods=['POST'])
    def voice_command():
        """Process a voice command (audio + transcription + response)."""
        try:
            audio_data = request.files.get('audio').read() if 'audio' in request.files else None

            if not audio_data:
                return jsonify({"error": "No audio data"}), 400

            result = api.process_voice_command(audio_data)
            return jsonify(result)

        except Exception as e:
            log.error(f"Voice command error: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/api/voice/text', methods=['POST'])
    def voice_text():
        """Process a text command (already transcribed)."""
        try:
            data = request.json
            text = data.get('text')

            if not text:
                return jsonify({"error": "No text provided"}), 400

            # Start conversation if needed
            conv_id = api.conv_manager.get_current_conversation_id()
            if not conv_id:
                conv_id = api.conv_manager.start_conversation()

            # Get response
            memories = api.memory_manager.get_top_memories(5)
            response = api.conv_manager.get_jarvis_response(text, conv_id, user_memories=memories)

            # Synthesize audio
            audio = api.tts.synthesize(response)

            return jsonify({
                "success": True,
                "text": text,
                "response": response,
                "audio": audio.hex() if audio else None
            })

        except Exception as e:
            log.error(f"Text command error: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/api/voice/briefing', methods=['GET'])
    def voice_briefing():
        """Get morning briefing."""
        return jsonify(api.get_briefing_command())

    @app.route('/api/voice/end-conversation', methods=['POST'])
    def end_conversation():
        """End conversation and extract memories."""
        return jsonify(api.end_conversation())

    return api
