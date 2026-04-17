"""
Document manager for Jarvis.
Handles document uploads, storage, and retrieval for conversation context.
"""

import os
import json
import logging
from datetime import datetime
from typing import List, Dict, Tuple
import psycopg2.extras

log = logging.getLogger(__name__)


class DocumentManager:
    """Manages document uploads and retrieval for conversation context."""

    def __init__(self, db_connection, upload_dir: str = "/tmp/jarvis_docs"):
        self.db = db_connection
        self.upload_dir = upload_dir

        # Create upload directory if it doesn't exist
        os.makedirs(upload_dir, exist_ok=True)

    def save_document(self, file_content: bytes, filename: str, file_type: str) -> Tuple[bool, int, str]:
        """
        Save an uploaded document and store metadata in database.

        Returns: (success, doc_id, error_message)
        """
        try:
            # Save file
            file_path = os.path.join(self.upload_dir, f"{datetime.now().timestamp()}_{filename}")
            with open(file_path, 'wb') as f:
                f.write(file_content)

            # Store metadata in database
            cur = self.db.cursor()
            cur.execute("""
                INSERT INTO documents (filename, file_path, file_type, file_size, uploaded_at)
                VALUES (%s, %s, %s, %s, NOW())
                RETURNING id
            """, (filename, file_path, file_type, len(file_content)))

            doc_id = cur.fetchone()[0]
            self.db.commit()

            log.info(f"Saved document {doc_id}: {filename}")
            return True, doc_id, ""

        except Exception as e:
            log.error(f"Error saving document: {e}")
            return False, None, str(e)

    def get_document(self, doc_id: int) -> Dict:
        """Retrieve document metadata and optionally content."""
        try:
            cur = self.db.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute("""
                SELECT id, filename, file_path, file_type, file_size, uploaded_at
                FROM documents
                WHERE id = %s
            """, (doc_id,))

            row = cur.fetchone()
            if not row:
                return None

            doc = dict(row)

            # Try to read content
            try:
                with open(doc['file_path'], 'rb') as f:
                    content = f.read()
                    doc['content'] = content.decode('utf-8', errors='ignore')
            except:
                doc['content'] = None

            return doc

        except Exception as e:
            log.error(f"Error retrieving document: {e}")
            return None

    def get_documents(self, limit: int = 50) -> List[Dict]:
        """Get all documents."""
        try:
            cur = self.db.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute("""
                SELECT id, filename, file_type, file_size, uploaded_at
                FROM documents
                ORDER BY uploaded_at DESC
                LIMIT %s
            """, (limit,))

            return [dict(row) for row in cur.fetchall()]

        except Exception as e:
            log.error(f"Error getting documents: {e}")
            return []

    def delete_document(self, doc_id: int) -> bool:
        """Delete a document."""
        try:
            cur = self.db.cursor()

            # Get file path
            cur.execute("SELECT file_path FROM documents WHERE id = %s", (doc_id,))
            row = cur.fetchone()

            if row:
                file_path = row[0]
                # Delete file
                if os.path.exists(file_path):
                    os.remove(file_path)

                # Delete from database
                cur.execute("DELETE FROM documents WHERE id = %s", (doc_id,))
                self.db.commit()

                log.info(f"Deleted document {doc_id}")
                return True

            return False

        except Exception as e:
            log.error(f"Error deleting document: {e}")
            return False

    def build_document_context(self, doc_ids: List[int]) -> str:
        """Build context string from selected documents for Claude."""
        if not doc_ids:
            return ""

        context_parts = []

        for doc_id in doc_ids:
            doc = self.get_document(doc_id)
            if doc and doc.get('content'):
                context_parts.append(f"\n--- Document: {doc['filename']} ---\n{doc['content']}")

        if context_parts:
            return "\n".join(context_parts)
        return ""

    def extract_text_from_document(self, file_path: str) -> str:
        """Extract text from various document types."""
        try:
            ext = os.path.splitext(file_path)[1].lower()

            if ext == '.txt':
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()

            elif ext == '.md':
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()

            elif ext == '.pdf':
                try:
                    import PyPDF2
                    text = []
                    with open(file_path, 'rb') as f:
                        reader = PyPDF2.PdfReader(f)
                        for page in reader.pages:
                            text.append(page.extract_text())
                    return '\n'.join(text)
                except ImportError:
                    return "(PDF support requires PyPDF2 - install with: pip install PyPDF2)"

            elif ext in ['.doc', '.docx']:
                try:
                    from docx import Document
                    doc = Document(file_path)
                    text = []
                    for para in doc.paragraphs:
                        text.append(para.text)
                    return '\n'.join(text)
                except ImportError:
                    return "(DOCX support requires python-docx - install with: pip install python-docx)"

            else:
                # Try as text
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()

        except Exception as e:
            log.error(f"Error extracting text from {file_path}: {e}")
            return f"(Error reading file: {str(e)})"
