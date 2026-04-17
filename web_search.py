"""
Web search integration for Jarvis.
Provides live research capability with background queries and natural integration into conversation.
"""

import logging
import requests
from typing import List, Dict, Optional, Tuple
from datetime import datetime

log = logging.getLogger(__name__)


class WebSearch:
    """Handles web searches for decision research and live information."""

    def __init__(self, use_duckduckgo: bool = True):
        """Initialize web search (DuckDuckGo by default - no API key needed)."""
        self.use_duckduckgo = use_duckduckgo
        self.search_history = []

    def search(self, query: str, max_results: int = 5) -> List[Dict]:
        """
        Perform a web search.

        Args:
            query: Search query
            max_results: Maximum results to return

        Returns:
            List of search results with title, snippet, url
        """
        if self.use_duckduckgo:
            return self._search_duckduckgo(query, max_results)
        else:
            return self._search_fallback(query, max_results)

    def _search_duckduckgo(self, query: str, max_results: int = 5) -> List[Dict]:
        """Search using DuckDuckGo (no API key required)."""
        try:
            # DuckDuckGo lite search (simple, no JS required)
            url = "https://lite.duckduckgo.com/lite"
            params = {"q": query, "kp": -2}  # kp -2 = no safe search

            response = requests.get(url, params=params, timeout=5)
            response.raise_for_status()

            results = self._parse_duckduckgo_results(response.text, max_results)
            return results

        except Exception as e:
            log.error(f"DuckDuckGo search failed: {e}")
            return []

    def _parse_duckduckgo_results(self, html: str, max_results: int) -> List[Dict]:
        """Parse DuckDuckGo HTML results."""
        results = []

        try:
            # Very basic HTML parsing
            lines = html.split('\n')
            for i, line in enumerate(lines):
                if '<a class="result-link"' in line and len(results) < max_results:
                    try:
                        # Extract title and URL from DuckDuckGo result
                        # This is fragile but works for basic parsing
                        import re

                        # Find href
                        href_match = re.search(r'href="([^"]+)"', line)
                        title_match = re.search(r'>([^<]+)</a>', line)

                        if href_match and title_match:
                            url = href_match.group(1)
                            title = title_match.group(1).strip()

                            # Try to get snippet from next few lines
                            snippet = ""
                            if i + 1 < len(lines):
                                snippet_line = lines[i + 1]
                                snippet_match = re.search(r'<p>([^<]+)</p>', snippet_line)
                                if snippet_match:
                                    snippet = snippet_match.group(1).strip()

                            if title and url:
                                results.append({
                                    "title": title,
                                    "url": url,
                                    "snippet": snippet or "No preview available"
                                })
                    except Exception as e:
                        log.debug(f"Error parsing result: {e}")
                        continue

            return results

        except Exception as e:
            log.error(f"Error parsing DuckDuckGo results: {e}")
            return []

    def _search_fallback(self, query: str, max_results: int) -> List[Dict]:
        """Fallback search (returns empty results if web search not available)."""
        log.warning("Web search not available - returning empty results")
        return []

    def research_decision(self, decision_topic: str, specific_questions: List[str] = None) -> Dict:
        """
        Research a decision topic with relevant queries.

        Args:
            decision_topic: The decision being made (e.g., "career change", "moving")
            specific_questions: Specific aspects to research

        Returns:
            Dict with research findings organized by question
        """
        research = {
            "topic": decision_topic,
            "researched_at": datetime.now().isoformat(),
            "findings": []
        }

        # Default research questions for the topic
        if not specific_questions:
            specific_questions = self._generate_research_questions(decision_topic)

        # Perform searches
        for question in specific_questions[:3]:  # Limit to 3 searches to avoid spam
            try:
                results = self.search(question, max_results=3)
                if results:
                    research["findings"].append({
                        "question": question,
                        "results": results
                    })
            except Exception as e:
                log.error(f"Research search failed for '{question}': {e}")

        return research

    def _generate_research_questions(self, topic: str) -> List[str]:
        """Generate research questions based on decision topic."""
        topic_lower = topic.lower()

        # Career change research
        if any(w in topic_lower for w in ["career", "job", "leave", "switch"]):
            return [
                f"risks of {topic}",
                f"how to successfully transition in {topic}",
                "career change regret statistics"
            ]

        # Relationship/interpersonal
        if any(w in topic_lower for w in ["relationship", "friend", "family", "confront"]):
            return [
                f"how to handle {topic} professionally",
                "relationship repair after conflict",
                "communication strategies for difficult conversations"
            ]

        # Major life changes
        if any(w in topic_lower for w in ["move", "relocate", "travel"]):
            return [
                f"things to consider when {topic}",
                f"hidden costs of {topic}",
                "what people regret about relocation decisions"
            ]

        # Default
        return [
            f"pros and cons of {topic}",
            f"things to consider before {topic}",
            f"common mistakes people make with {topic}"
        ]

    def format_research_for_conversation(self, research: Dict) -> str:
        """Format research results as natural conversation references, not a report."""
        if not research.get("findings"):
            return ""

        # Return just 1-2 key findings naturally integrated, not a list
        findings = research["findings"][:2]

        formatted = []
        for finding in findings:
            if finding["results"]:
                result = finding["results"][0]  # Best result
                formatted.append(f"Relevant: {result['title']}\n  {result['snippet']}")

        return "\n".join(formatted) if formatted else ""

    def search_and_cite(self, query: str) -> Tuple[str, List[Dict]]:
        """
        Search and return results with proper citations.

        Returns:
            Tuple of (formatted_text, sources)
        """
        results = self.search(query, max_results=3)

        if not results:
            return "No results found.", []

        # Format for readability
        text_parts = []
        sources = []

        for i, result in enumerate(results, 1):
            text_parts.append(f"{i}. {result['title']}\n   {result['snippet']}")
            sources.append({"title": result['title'], "url": result['url']})

        return "\n".join(text_parts), sources

    def get_conversation_context(self, decision_type: str, stakeholders: List[str] = None) -> str:
        """Get relevant background context via web search for conversation."""
        queries = []

        if "career" in decision_type.lower():
            queries.append("career change success rate 2024")
        if "relationship" in decision_type.lower():
            queries.append("difficult conversations relationship advice")

        if not queries:
            return ""

        # Research silently in background
        research = self.research_decision(decision_type, queries)
        return self.format_research_for_conversation(research)

    def is_available(self) -> bool:
        """Check if web search is available."""
        try:
            response = requests.get("https://lite.duckduckgo.com/lite", timeout=2)
            return response.status_code == 200
        except:
            return False
