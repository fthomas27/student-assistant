"""
Decision analyzer: Helps systematically analyze decisions to uncover hidden risks.
Focuses on life/career and interpersonal decisions with consequence mapping.
"""

import json
import logging
from typing import Dict, List, Tuple
from enum import Enum

log = logging.getLogger(__name__)


class DecisionType(Enum):
    """Types of decisions to analyze differently."""
    CAREER = "career"
    LIFE_MAJOR = "life_major"
    INTERPERSONAL = "interpersonal"
    FINANCIAL = "financial"
    TIMING = "timing"
    UNKNOWN = "unknown"


class DecisionAnalyzer:
    """Analyzes decisions for hidden risks and consequences."""

    def __init__(self):
        self.decision_type = DecisionType.UNKNOWN
        self.stakeholders = []
        self.timeline_horizons = [
            ("immediate", "Next 1-2 weeks"),
            ("short_term", "Next 1-3 months"),
            ("medium_term", "Next 1 year"),
            ("long_term", "Next 5 years"),
            ("very_long_term", "10+ years")
        ]

    def identify_decision_type(self, text: str) -> DecisionType:
        """Identify what kind of decision the user is facing."""
        text_lower = text.lower()

        # Career indicators
        if any(w in text_lower for w in ["career", "job", "leave", "switch", "quit", "industry", "role", "position"]):
            return DecisionType.CAREER

        # Interpersonal indicators
        if any(w in text_lower for w in ["relationship", "friend", "family", "reach out", "confront", "tell them", "ask them", "apologize", "break up", "dating"]):
            return DecisionType.INTERPERSONAL

        # Major life indicators
        if any(w in text_lower for w in ["move", "marriage", "children", "health", "education", "school", "relocate", "travel"]):
            return DecisionType.LIFE_MAJOR

        # Financial indicators
        if any(w in text_lower for w in ["money", "invest", "buy", "spend", "budget", "loan", "debt"]):
            return DecisionType.FINANCIAL

        # Timing indicators
        if any(w in text_lower for w in ["now", "timing", "wait", "rush", "timing", "soon", "eventually"]):
            return DecisionType.TIMING

        return DecisionType.UNKNOWN

    def extract_stakeholders(self, text: str) -> List[Dict]:
        """Identify who will be affected by this decision."""
        stakeholders = []

        # Self
        stakeholders.append({
            "name": "You",
            "impact_area": "Well-being, growth, fulfillment",
            "power": "High (it's your decision)"
        })

        # People indicators
        people_keywords = {
            "team": ("Your team/colleagues", "Career/collaboration"),
            "partner": ("Your partner/spouse", "Relationship/life"),
            "family": ("Your family", "Relationships"),
            "friend": ("Friends", "Social"),
            "child": ("Children", "Future/upbringing"),
            "parent": ("Parents", "Family dynamics"),
            "boss": ("Boss/leadership", "Career"),
            "mentor": ("Mentors/advisors", "Guidance/support")
        }

        for keyword, (person, area) in people_keywords.items():
            if keyword in text.lower():
                stakeholders.append({
                    "name": person,
                    "impact_area": area,
                    "power": "Medium (can be affected)"
                })

        return stakeholders

    def map_consequences(self, decision_description: str) -> Dict:
        """Map out consequences across different dimensions and time horizons."""
        return {
            "dimensions": [
                {
                    "name": "Interpersonal",
                    "question": "How will this affect your relationships?",
                    "risks": [
                        "Relationship strain with team/friends",
                        "Trust impacts",
                        "Regret if people feel abandoned",
                        "Difficulty reconnecting later"
                    ]
                },
                {
                    "name": "Career/Growth",
                    "question": "How will this affect your growth path?",
                    "risks": [
                        "New skills vs. lost expertise",
                        "Network impact (who you know)",
                        "Resume implications",
                        "Opportunity cost"
                    ]
                },
                {
                    "name": "Financial",
                    "question": "What are the financial impacts?",
                    "risks": [
                        "Income changes",
                        "Hidden costs",
                        "Time to stability",
                        "Safety net erosion"
                    ]
                },
                {
                    "name": "Emotional",
                    "question": "How will this feel over time?",
                    "risks": [
                        "Regret patterns",
                        "FOMO (fear of missing out)",
                        "Identity shifts",
                        "Long-term satisfaction"
                    ]
                },
                {
                    "name": "Reversibility",
                    "question": "Can you undo this if it goes wrong?",
                    "risks": [
                        "Permanent vs. temporary",
                        "Coming back cost",
                        "Bridges burned",
                        "Path locked in"
                    ]
                }
            ],
            "time_horizons": [
                {
                    "horizon": "Immediate (1-2 weeks)",
                    "question": "What happens right away?",
                    "focus": "Logistics, emotions, reactions"
                },
                {
                    "horizon": "Short-term (1-3 months)",
                    "question": "What are you experiencing now?",
                    "focus": "Adjustment, learning, feedback"
                },
                {
                    "horizon": "Medium-term (1 year)",
                    "question": "Are you glad you did this?",
                    "focus": "Integration, growth, impact"
                },
                {
                    "horizon": "Long-term (5 years)",
                    "question": "How did this shape your life?",
                    "focus": "Trajectory, meaning, fulfillment"
                },
                {
                    "horizon": "Very long-term (10+ years)",
                    "question": "Looking back, was this right?",
                    "focus": "Life satisfaction, no regrets"
                }
            ]
        }

    def generate_probing_questions(self, decision_type: DecisionType) -> List[str]:
        """Generate natural clarifying questions based on decision type."""

        base_questions = [
            "What are you hoping will change?",
            "What would you regret most if you did this?",
            "What would you regret most if you didn't?",
            "Who would this actually affect beyond you?"
        ]

        type_specific = {
            DecisionType.CAREER: [
                "Is this about the work itself, the people, or your growth?",
                "What's making you feel stuck right now?",
                "Can you get what you need by changing roles instead of leaving?",
                "What would losing your team cost you emotionally?",
            ],
            DecisionType.INTERPERSONAL: [
                "What's the worst that could happen if you do this?",
                "What's the worst that could happen if you don't?",
                "Can you repair this relationship if it goes badly?",
                "What do you actually need from this person/situation?",
            ],
            DecisionType.LIFE_MAJOR: [
                "Is this about running toward something or away from something?",
                "What are you certain about vs. what's uncertain?",
                "How much of this is timing vs. substance?",
                "Can you test this before fully committing?",
            ],
        }

        questions = base_questions + type_specific.get(decision_type, [])
        return questions

    def format_for_conversation(self, analysis: Dict) -> str:
        """Format analysis as natural conversation prompts, not a report."""
        # This gets woven into Jarvis responses naturally, not dumped
        return json.dumps(analysis, indent=2)

    def identify_hidden_assumptions(self, text: str) -> List[str]:
        """Find assumptions the user might not realize they're making."""
        assumptions = []

        # Timing assumptions
        if "should" in text.lower() or "need to" in text.lower():
            assumptions.append("Assumption: There's urgency here. Is that real or perceived?")

        # All-or-nothing
        if "either/or" in text.lower() or " or " in text.lower():
            assumptions.append("Assumption: You might be seeing this as binary when there could be middle ground.")

        # Certainty about others
        if any(w in text.lower() for w in ["they will", "they won't", "they'll never", "people always"]):
            assumptions.append("Assumption: You're predicting how others will react. That might be worth testing.")

        # Perfect outcomes
        if any(w in text.lower() for w in ["perfect", "finally", "finally happy", "solve everything"]):
            assumptions.append("Assumption: This decision might be carrying weight of solving something bigger.")

        # Identity/permanence
        if "I am" in text or "I'm not" in text:
            assumptions.append("Assumption: You might be linking this to identity/permanence when it's actually changeable.")

        return assumptions

    def create_decision_record(self, decision_summary: str, analysis: Dict, user_id: int = None) -> Dict:
        """Create a record to store in database for future learning."""
        return {
            "decision_summary": decision_summary,
            "analysis": analysis,
            "created_at": __import__('datetime').datetime.now().isoformat(),
            "user_id": user_id,
            "outcome": None,  # Will be filled in later when user reports back
            "learned": None
        }

    def get_conversation_prompt(self, decision_type: DecisionType, stakeholders: List, assumptions: List) -> str:
        """Get a system prompt addition for Claude to handle this decision well."""

        prompt = f"""
The user is working through a {decision_type.value} decision.

Key people affected: {', '.join([s.get('name', 'Unknown') for s in stakeholders]) if stakeholders else 'Mostly themselves'}

They might be assuming: {' '.join(assumptions) if assumptions else 'Nothing obvious yet'}

Your approach:
1. Listen for what they actually want vs. what they think they should do
2. Ask questions that help them see risks they're not seeing
3. For interpersonal decisions especially, help them think through impact on relationships
4. Surface the reversibility question - can they change course if needed?
5. Help them distinguish between what's urgent vs. what's actually time-sensitive
6. Reference past similar decisions if they come up in conversation
7. Never tell them what to do - help them think better

Be conversational. These are natural questions, not an interrogation.
"""
        return prompt
