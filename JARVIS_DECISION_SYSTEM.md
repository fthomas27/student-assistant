# Jarvis Decision-Making System

## Overview

Jarvis is now equipped with a sophisticated decision-making system that addresses your core pain point: **risk/consequence blindness**. The system automatically detects when you're facing a decision and helps you think through hidden consequences, stakeholder impacts, and reversibility.

## System Architecture

### 1. Decision Detection (`conversation_manager.py`)

**Method**: `detect_decision_moment(user_message)`

Automatically recognizes when you're discussing a decision by detecting:
- Uncertainty keywords: "thinking about", "should I", "torn between", "can't decide"
- Emotional signals: "worried about", "anxious about", "scared of"
- Major life events: "career", "relationship", "moving", "quit", "break up"
- Decision framing: "decision", "choice", "should I", "am I making a mistake"

**Example**: User says "I've been thinking about leaving my job. I like it but I don't feel like I'm growing."
→ System detects: Career decision with emotional intensity

### 2. Decision Analysis (`decision_analyzer.py`)

Once a decision is detected, Jarvis analyzes:

#### Type Identification
- **Career**: Job changes, industry switches, role changes
- **Interpersonal**: Relationship decisions, confrontations, breakups
- **Life Major**: Moving, marriage, major health decisions
- **Financial**: Investment, spending, debt decisions
- **Timing**: Whether to do something now or wait

#### Stakeholder Extraction
Who will be affected by this decision?
- Yourself (always identified)
- Team/colleagues (if job-related)
- Partner/spouse (if relationship-relevant)
- Family, friends, children, mentors, etc.

**Example**: Changing jobs affects:
- **You**: Career growth, income, skills, fulfillment
- **Your team**: Knowledge loss, transition chaos
- **Your partner**: Location, stress, income change
- **Your family**: Moving implications, time availability

#### Hidden Assumption Detection
Surfaces assumptions you might not realize you're making:
- "Should I?" → Assumption: There's urgency (is it real or perceived?)
- "Either/or" → Assumption: Binary choice when middle ground exists
- "They will react badly" → Assumption: You can predict their reaction
- "This will finally make me happy" → Assumption: One decision solves everything

#### Consequence Mapping
Consequences across 5 dimensions and 5 time horizons:

**Dimensions**:
- Interpersonal: How will relationships be affected?
- Career/Growth: Impact on your growth path?
- Financial: Money implications?
- Emotional: How will this feel over time? Regret potential?
- Reversibility: Can you undo this if it goes wrong?

**Time Horizons**:
- Immediate (1-2 weeks): Right away logistics and emotions
- Short-term (1-3 months): Adjustment and learning phase
- Medium-term (1 year): Integration and impact clarity
- Long-term (5 years): Trajectory and life impact
- Very long-term (10+ years): Life satisfaction and no regrets

### 3. Live Research (`web_search.py`)

For complex decisions, Jarvis researches relevant information via DuckDuckGo:
- Career changes: success rates, transition strategies, regret statistics
- Relationships: communication advice, repair strategies
- Major moves: hidden costs, what people regret
- Financial decisions: pros/cons, common mistakes

Results are naturally integrated into conversation, not dumped as a report.

### 4. Extended Thinking (`conversation_manager.py`)

For emotionally intense or high-stakes decisions, Claude uses extended thinking mode:

**Triggers**:
- Career + emotional intensity ("worried", "anxious", "torn")
- Relationship decisions + complexity
- Major life decisions + multiple stakeholders
- Explicit requests for deep thinking

**What happens**:
- 10,000 thinking tokens allocated for deep reasoning
- Claude systematically analyzes consequences, risks, and patterns
- Response emerges from thorough reasoning, not pattern-matching
- You get genuinely thoughtful advice, not surface-level

### 5. Decision Outcome Tracking

**Record decisions**: `record_decision()`
- Stores: summary, type, stakeholders affected
- Linked to conversation for context

**Report outcomes**: `report_decision_outcome()`
- User reports how it went
- Satisfaction rating (1-5 scale)
- Claude analyzes what went well/poorly

**Learn patterns**: `_learn_from_decision_outcome()`
- Extracts lessons from outcomes
- Identifies patterns (what usually works, what doesn't)
- Stores with confidence scores

**Reference precedents**: `get_similar_past_decisions()`
- Jarvis retrieves similar past decisions
- Shows you what happened before, what you learned
- Helps avoid repeating mistakes

## How It Works in Conversation

### Example: Career Change Decision

**You**: "I've been thinking about leaving my job. I like it but I'm not growing."

**Jarvis detects**: Career decision + emotional intensity

**Jarvis analyzes**:
- Type: Career transition
- Stakeholders: You, your team, your family, your financial security
- Assumptions: "Growing" = moving companies; "Not growing" means it's time to leave
- Research: Career change success rates, transition strategies

**Jarvis responds** (with extended thinking):
"That's real tension I hear—you're not unhappy, but you're feeling stuck. Before jumping, let's think this through.

First: What does 'growing' actually mean to you specifically? Is it learning new skills, leading bigger projects, different industry, or something else? Because you might get growth without leaving.

Second: Your team—how would losing you affect them? Not to guilt you, but to make sure you understand the ripple effects.

Third: The reversibility question. Could you come back to this role later if the outside world isn't what you hoped? Or is this a one-way door?

And here's what I'm curious about: If you stayed and got what you wanted—more growth in this role—would that actually solve the restlessness, or is there something else underneath? Sometimes it's not about the job."

**You provide more context**, Jarvis continues with probing questions and references past decisions if relevant.

### Integrated into Briefing

Each morning, Jarvis considers your decision patterns:
"You have an assignment due today. Also, remember you were thinking about that job decision—no pressure, but worth noting you have headspace to think about it if you want."

## Claude Tool Use

Jarvis can now execute structured actions:

**Task Management**:
- "Create a task to research Python libraries"
- "What's my task list for today?"
- "Mark that done"

**Notes**:
- "Note that I need to write a project proposal"
- "Show me notes about that coffee place"
- "Create a shopping list"

**Home Assistant Control**:
- "Turn on the office light to 50%"
- "What's the thermostat at?"
- "Close the garage door"

**Decisions**:
- "Show me other times I've changed jobs"
- "Remember this decision: leaving my current team"

**Memory**:
- "Store: I prefer dark coffee"
- "What do you know about my workout habits?"

**Search & Research**:
- "What are current trends in machine learning?"
- "Research: cost of living in Denver"

Claude seamlessly chooses when to use tools based on what you're asking.

## Database Schema

**decision_records** table:
```
id, conversation_id, decision_summary, decision_type, 
stakeholders (JSON), outcome, satisfaction, created_at, updated_at
```

**decision_lessons** table:
```
id, decision_id, lesson_text, pattern, confidence, created_at
```

## API Endpoints

```
POST /api/decisions - Record a decision
POST /api/decisions/{id}/outcome - Report how it went
GET /api/decisions/similar?decision_type=career - Get similar past decisions
```

## Configuration

Set in `.env`:
```
# Decision analysis mode (can be disabled)
DECISION_MODE=enabled

# Extended thinking budget (tokens for deep reasoning)
EXTENDED_THINKING_BUDGET=10000

# Store decision outcomes (enables learning)
TRACK_DECISION_OUTCOMES=true
```

## What This Solves

### Your Pain Point: Risk/Consequence Blindness

**Before**: You'd make decisions and only realize implications later.
**Now**: Jarvis proactively surfaces:
- Hidden consequences across time and stakeholders
- Reversibility (can you undo this?)
- People impacts (your biggest blind spot, now flagged)
- Assumptions you're making unconsciously
- Patterns from similar past decisions

### Integration with Life/Work

Jarvis doesn't just chat—it:
- Understands your decision context automatically
- Researches relevant information
- Thinks deeply on complex decisions
- Learns from your actual outcomes
- References precedent ("Like when you...")
- Adapts guidance based on what you've learned before

## Limitations & Future Work

**Not yet implemented**:
- Vision (analyze images, charts, scenarios)
- File analysis (read documents to understand context)
- Extended memory decay (memories gradually fade if unused)
- Prompt caching (90% cost savings for repeated analysis)
- Batch processing (queue non-urgent research overnight)

**Stubbed but need implementation**:
- Decision insights dashboard
- Outcome reporting UI (voice + text)
- Proactive alerts ("This is similar to when...")
- Decision templates for common scenarios

## Testing the System

### Quick Test: Career Decision Flow

```
User: "I'm thinking about switching careers to software engineering"
Jarvis: [detects career decision + uncertainty]
        [activates extended thinking]
        [researches career transitions]
→ Surfaces: current role value, team impact, income transition, 
           reversibility (can return?), pattern from similar decisions

User: "Yeah, everyone would miss me. But I think I need this."
Jarvis: "They would miss you—that's real value. But 'need' is interesting.
         Is this about getting away from something or moving toward something?
         Big difference in how it plays out."

[Continue conversation, Jarvis asks hard questions]

User: [Three weeks later] "I decided to stay but negotiate for a new project"
Jarvis: [records outcome: satisfaction 4/5]
        [learns: sometimes middle ground works better than major change]
        [uses this in future career decision guidance]
```

## Integration with Existing Systems

**Conversation Manager**: Detects decisions, triggers analysis
**Web Search**: Researches decision context
**Decision Analyzer**: Identifies type, stakeholders, assumptions
**Memory Manager**: Recalls similar past situations
**Claude API**: Extended thinking for complex decisions
**Database**: Stores decisions and outcomes for learning
**Tool Executor**: Executes structured actions during decisions
**Voice API**: Surfaces decision context in voice interactions

## Next Steps

1. **Test extended thinking** with actual complex decisions
2. **Validate decision detection** accuracy (reduce false positives)
3. **Implement outcome tracking UI** (easy way to report back)
4. **Add decision templates** for common scenarios
5. **Enable vision** for analyzing scenarios, diagrams, charts
6. **Build decision dashboard** showing patterns over time

---

**Core Philosophy**: Jarvis isn't telling you what to do. It's helping you think better by surfacing what you might miss alone. Your decisions stay your own, but now you see the blind spots.
