"""
Notes API endpoints for Jarvis note-taking system.
"""

import logging
from flask import Blueprint, request, jsonify
from note_manager import NoteManager

log = logging.getLogger(__name__)

notes_bp = Blueprint('notes', __name__, url_prefix='/api/notes')


class NotesAPI:
    """Notes API handler."""

    def __init__(self, db_connection):
        """Initialize notes API."""
        self.note_manager = NoteManager(db_connection)

    def create_note(self, content: str, category: str = None, importance: int = 0) -> dict:
        """Create a new note."""
        if not category:
            category = self.note_manager.auto_categorize(content)

        note_id = self.note_manager.create_note(content, category=category, importance=importance)
        return {
            "success": True,
            "note_id": note_id,
            "category": category
        }

    def get_note(self, note_id: int) -> dict:
        """Get a single note with tags."""
        note = self.note_manager.get_note_with_tags(note_id)
        if not note:
            return {"success": False, "error": f"Note {note_id} not found"}

        self.note_manager.access_note(note_id)
        return {"success": True, "note": note}

    def list_notes(self, category: str = None, sort_by: str = "recent", limit: int = 50) -> dict:
        """List notes with optional filtering."""
        if category:
            notes = self.note_manager.get_notes_by_category(category, limit=limit)
        else:
            notes = self.note_manager.get_all_notes(limit=limit, sort_by=sort_by)

        return {
            "success": True,
            "count": len(notes),
            "notes": notes
        }

    def search_notes(self, query: str, limit: int = 50) -> dict:
        """Search notes by query."""
        notes = self.note_manager.search_notes(query, limit=limit)
        return {
            "success": True,
            "query": query,
            "count": len(notes),
            "notes": notes
        }

    def update_note(self, note_id: int, content: str = None, category: str = None, importance: int = None) -> dict:
        """Update a note."""
        self.note_manager.update_note(note_id, content=content, category=category, importance=importance)
        return {
            "success": True,
            "note_id": note_id,
            "message": "Note updated"
        }

    def delete_note(self, note_id: int) -> dict:
        """Delete a note."""
        self.note_manager.delete_note(note_id)
        return {
            "success": True,
            "note_id": note_id,
            "message": "Note deleted"
        }

    def get_categories(self) -> dict:
        """Get all note categories."""
        categories = self.note_manager.get_categories()
        return {
            "success": True,
            "categories": categories,
            "count": len(categories)
        }

    def get_statistics(self) -> dict:
        """Get notes statistics."""
        stats = self.note_manager.get_notes_statistics()
        return {
            "success": True,
            "statistics": stats
        }


def create_notes_routes(app, db_connection):
    """Create note-related Flask routes."""
    api = NotesAPI(db_connection)

    @app.route('/api/notes', methods=['POST'])
    def create_note():
        """Create a new note."""
        try:
            data = request.json
            content = data.get('content')
            category = data.get('category')
            importance = data.get('importance', 0)

            if not content:
                return jsonify({"error": "content required"}), 400

            result = api.create_note(content, category=category, importance=importance)
            return jsonify(result), 201

        except Exception as e:
            log.error(f"Create note error: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/api/notes/<int:note_id>', methods=['GET'])
    def get_note(note_id):
        """Get a single note."""
        try:
            result = api.get_note(note_id)
            status = 200 if result["success"] else 404
            return jsonify(result), status

        except Exception as e:
            log.error(f"Get note error: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/api/notes', methods=['GET'])
    def list_notes():
        """List notes with optional filtering."""
        try:
            category = request.args.get('category')
            sort_by = request.args.get('sort', 'recent')
            limit = int(request.args.get('limit', 50))

            result = api.list_notes(category=category, sort_by=sort_by, limit=limit)
            return jsonify(result)

        except Exception as e:
            log.error(f"List notes error: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/api/notes/search', methods=['GET'])
    def search_notes():
        """Search notes."""
        try:
            query = request.args.get('q', '')
            limit = int(request.args.get('limit', 50))

            if not query:
                return jsonify({"error": "query parameter required"}), 400

            result = api.search_notes(query, limit=limit)
            return jsonify(result)

        except Exception as e:
            log.error(f"Search notes error: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/api/notes/<int:note_id>', methods=['PUT'])
    def update_note(note_id):
        """Update a note."""
        try:
            data = request.json
            content = data.get('content')
            category = data.get('category')
            importance = data.get('importance')

            result = api.update_note(note_id, content=content, category=category, importance=importance)
            return jsonify(result)

        except Exception as e:
            log.error(f"Update note error: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/api/notes/<int:note_id>', methods=['DELETE'])
    def delete_note(note_id):
        """Delete a note."""
        try:
            result = api.delete_note(note_id)
            return jsonify(result)

        except Exception as e:
            log.error(f"Delete note error: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/api/notes/categories', methods=['GET'])
    def get_categories():
        """Get all note categories."""
        try:
            result = api.get_categories()
            return jsonify(result)

        except Exception as e:
            log.error(f"Get categories error: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/api/notes/statistics', methods=['GET'])
    def get_statistics():
        """Get notes statistics."""
        try:
            result = api.get_statistics()
            return jsonify(result)

        except Exception as e:
            log.error(f"Get statistics error: {e}")
            return jsonify({"error": str(e)}), 500

    return api
