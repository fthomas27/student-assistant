# Jarvis: Your Personal AI Assistant

Welcome to Jarvis—your all-in-one AI assistant that replaces ChatGPT, web search, and document analysis. Jarvis is a sophisticated personal AI designed to be your decision-making partner, managing your life, analyzing documents, and always available via voice or web interface.

## 🎯 Core Concept

Jarvis solves your biggest problem: **risk/consequence blindness** in life, career, and interpersonal decisions. Instead of just answering questions, Jarvis:

- Automatically detects when you're facing a decision
- Surfaces hidden risks and consequences you'd miss alone
- Researches relevant information via live web search
- Uses Claude's extended thinking for deep reasoning on complex decisions
- Learns from your past decisions to improve future guidance
- Never tells you what to do—helps you think better

Beyond decisions, Jarvis is your complete life management system:
- **Chat interface**: Talk naturally, upload documents for analysis
- **Dashboard**: Tasks, calendar, notes, briefing, smart home control
- **Voice access**: Always-on voice interface via Raspberry Pi
- **Independence**: Works on Kindle, computer, or via voice—pick any combination
- **Memory**: Learns about your preferences, habits, and patterns over time

## 🚀 Quick Start

### Access Jarvis

**Via Web Browser** (Kindle, laptop, desktop):
```
http://localhost:5000/
  └─ Chat interface with document upload
  
http://localhost:5000/dashboard
  └─ Full dashboard (tasks, notes, calendar, briefing, devices)
```

**Via Voice** (Raspberry Pi with microphone + speaker):
- Say wake word: "Jarvis" or "Hey Jarvis"
- Jarvis responds with spoken answers
- Ask for tasks, chat, control smart home, get briefing

### Key Features

#### 1. **Chat with Document Analysis**
```
1. Go to http://localhost:5000/
2. Drag/drop documents or click upload button
3. Documents are analyzed alongside your message
4. Claude references document context in responses
```

**Supported formats**: PDF, DOCX, TXT, MD

#### 2. **Dashboard**
```
http://localhost:5000/dashboard

Views:
- Dashboard: Quick overview, briefing, upcoming tasks
- Chat: Full chat interface (embedded)
- Tasks: Create, track, prioritize tasks
- Notes: Write, organize, search notes
- Calendar: View upcoming events and assignments
- Briefing: Morning briefing summary
- Devices: Control smart home devices
- Settings: Configure voice, briefing time, theme
```

#### 3. **Decision-Making System**
When you discuss a decision, Jarvis automatically:
1. **Detects** you're making a decision (via keywords)
2. **Analyzes**: Type (career/interpersonal/financial), stakeholders, assumptions
3. **Researches**: Finds relevant information via web search
4. **Thinks deeply**: For complex decisions, uses extended thinking (10,000 tokens of reasoning)
5. **Surfaces risks**: Hidden consequences across time and stakeholders
6. **References past**: Shows similar past decisions and their outcomes

**Example**: "I'm thinking about leaving my job"
→ Jarvis surfaces: team impact, income change, reversibility, past career decisions, research on transitions

#### 4. **Always-On Voice**
Raspberry Pi runs 24/7 with:
- **Wake word detection**: "Jarvis" activation
- **Natural STT**: OpenAI Whisper (streaming)
- **Spoken responses**: ElevenLabs TTS with Alistair voice (British, sophisticated)
- **Smart timing**: Quick responses (< 2s) for simple queries, thinking time (< 5s) for complex ones

#### 5. **Memory System**
Jarvis learns about you:
- **Preferences**: "User prefers dark coffee"
- **Habits**: "User works out at 6 PM"
- **Interests**: "User interested in machine learning"
- **Family**: "Sister Emma's birthday March 15"
- **Work patterns**: "Most assignments due Fridays"

Memory automatically extracted after conversations, refined over time.

#### 6. **Decision Outcome Tracking**
Report how past decisions turned out:
```
User: "Remember that job change? It went well"
Jarvis: [Extracts lessons, updates decision database]
→ Uses learning in future career decision guidance
```

## 🏗️ Architecture

### Frontend
- **jarvis.html**: Chat interface with document upload, drag-and-drop
- **jarvis-dashboard.html**: Complete dashboard with all features
- **Color scheme**: Dark (#1a1a1a) + autumn orange (#d97706) + white tints

### Backend (Flask + PostgreSQL)
```
app.py (3600+ lines)
├─ Authentication & session management
├─ Database initialization & schema
├─ Voice API routes
├─ Document endpoints
├─ Dashboard endpoints
├─ Chat integration
└─ Settings management

conversation_manager.py
├─ Multi-turn conversations with Claude
├─ Decision detection & analysis
├─ Extended thinking integration
├─ Memory extraction & storage
├─ Decision outcome tracking
└─ Tool use coordination

decision_analyzer.py
├─ Identifies decision type
├─ Extracts stakeholders
├─ Maps consequences (5D × 5T)
├─ Generates probing questions
└─ Identifies hidden assumptions

web_search.py
├─ DuckDuckGo live search (no API key)
├─ Decision-specific research queries
├─ Citation formatting
└─ Natural integration into conversation

document_manager.py
├─ File upload handling (PDF, DOCX, TXT, MD)
├─ Text extraction from documents
├─ Database storage
└─ Context building for Claude

memory_manager.py
├─ Long-term memory storage
├─ Memory decay system
├─ Confidence scoring
└─ Context-based retrieval

tool_executor.py
├─ Processes Claude tool_use blocks
├─ 30+ integrated tools
├─ Task creation, note management, device control
└─ Memory storage, decision tracking

jarvis_tools.py
├─ 30 tool definitions for Claude
├─ Tool validation schema
└─ Comprehensive action catalog
```

### Database Schema
```
conversations (id, created_at, ended_at, total_exchanges)
messages (id, conversation_id, role, content, confidence_score, created_at)
user_memories (id, memory_text, category, confidence, usage_count, created_at)
notes (id, content, category, importance, created_at)
decision_records (id, conversation_id, decision_summary, decision_type, stakeholders, outcome, satisfaction)
decision_lessons (id, decision_id, lesson_text, pattern, confidence, created_at)
documents (id, filename, file_path, file_type, file_size, uploaded_at)
tasks (id, title, due_date, priority, completed, created_at)
+ calendar, projects, workout_logs, timer_state, config, etc.
```

### Key Models
- **Claude Sonnet 4.6**: Main AI (speed + quality balance)
- **Extended Thinking**: 10,000 tokens for complex decisions
- **Tool Use**: 30+ tools for structured actions
- **Streaming**: Real-time response generation

### Voice I/O
- **Wake word**: Porcupine detection (local, < 500ms latency)
- **STT**: OpenAI Whisper (streaming) + faster-whisper (local fallback)
- **TTS**: ElevenLabs (high quality) + pyttsx3 (offline fallback)
- **Voice**: Alistair (ElevenLabs, British, sophisticated)

## 📚 API Reference

### Chat & Documents
```
POST /api/chat
POST /api/documents/upload
GET /api/documents
DELETE /api/documents/{id}
```

### Dashboard
```
GET /api/dashboard/summary          # Stats overview
GET /api/dashboard/tasks            # Task list
GET /api/dashboard/notes            # Recent notes
GET /api/dashboard/briefing         # Morning briefing
GET /api/dashboard/calendar         # Upcoming events
GET /api/dashboard/devices          # Smart home devices
POST /api/dashboard/devices/{id}/control
GET /api/dashboard/settings
POST /api/dashboard/settings
```

### Decisions
```
POST /api/decisions
POST /api/decisions/{id}/outcome
GET /api/decisions/similar?decision_type=career
```

### Home Assistant
```
GET /api/ha/devices
POST /api/ha/control
GET /api/ha/status
```

### Notes, Tasks, etc.
```
POST /api/notes
GET /api/notes
GET /api/notes/search
PUT /api/notes/{id}
DELETE /api/notes/{id}
```

## 🎨 Design & UX

### Color Palette
- **Dark Background**: #1a1a1a
- **Darker Background**: #0f0f0f
- **Accent Orange**: #d97706 (main)
- **Light Orange**: #f97316 (hover)
- **Dark Orange**: #b45309 (active)
- **White Tint**: #f5f5f5
- **Muted Text**: #a0a0a0

### Responsive Design
- **Desktop**: Full layout with sidebar
- **Tablet (Kindle Fire)**: Optimized touch targets, collapsible sidebar
- **Mobile**: Single column, full-width interface

### User Experience
- **Auto-resize textarea**: Grows with input
- **Drag-and-drop**: Drop documents anywhere to upload
- **Keyboard support**: Enter = send, Shift+Enter = newline
- **Real-time feedback**: Status indicators, loading states
- **Smooth animations**: Fade-ins, transitions, hover effects

## 🔧 Configuration

### Environment Variables
```bash
# Core
ANTHROPIC_API_KEY=sk-ant-...
DATABASE_URL=postgresql://...

# Voice (optional)
OPENAI_API_KEY=sk-proj-...  # Whisper STT
ELEVENLABS_API_KEY=sk_...
JARVIS_WAKE_WORD=jarvis

# Home Assistant (optional)
HA_URL=http://home-assistant.local:8123
HA_TOKEN=eyJ...

# Settings
SECRET_KEY=your-secret-key
APP_PASSWORD=jarvis2025
TIMEZONE=America/Denver
JARVIS_VOICE_ID=alistair
MORNING_BRIEFING_TIME="0 6 * * *"  # 6 AM daily
```

### Settings via Dashboard
Via `/dashboard` → Settings tab:
- Toggle voice input on/off
- Configure morning briefing time
- Select theme (Dark/Light/High Contrast)
- Manage API keys

## 🚀 Deployment

### Local Development
```bash
git clone <repo>
cd student-assistant
python -m pip install -r requirements.txt
export ANTHROPIC_API_KEY=your_key
export DATABASE_URL=postgresql://user:pass@localhost/jarvis
python app.py
# Visit http://localhost:5000/
```

### Raspberry Pi Deployment
```bash
# See JARVIS_DEPLOYMENT.md for complete guide
# Quick: Docker Compose with PostgreSQL + Flask
docker-compose up -d
# Visit http://<pi-ip>:5000/
```

### Railway Deployment
```bash
# Push to Railway
git push
# Configure environment variables in Railway dashboard
# Auto-deploys on push
```

## 📊 Decision Analysis Example

**Scenario**: "I'm worried about leaving my team but feel stuck in my role"

**Jarvis detects**: Career + interpersonal + emotional intensity
**Activates**: Extended thinking mode (10,000 tokens)

**Analysis**:
1. **Type**: Career transition
2. **Stakeholders**: You, your team, your manager, your family's finances
3. **Assumptions**: 
   - "I must leave to grow" (can you grow here instead?)
   - "Team will fall apart" (will they manage?)
4. **Consequences across time**:
   - Immediate (1-2 weeks): Resignation, transition, emotions
   - Short-term (3 months): New job adjustment, team adaptation
   - Medium (1 year): Path clarification, identity formation
   - Long-term (5+ years): Career trajectory impact

5. **Research**: Career change success rates, team transition best practices
6. **Questions**: "What does growth actually mean to you? Is it learning new skills or a different environment?"

**Response**: Not "you should leave" but "help you think better about what you're really seeking"

## 🎯 What Makes Jarvis Different

| Feature | ChatGPT | Web Search | Jarvis |
|---------|---------|-----------|--------|
| **Decision guidance** | Generic | None | Specialized, learns from outcomes |
| **Risk detection** | Surface-level | N/A | Systematic (5D × 5T analysis) |
| **Memory** | None | None | Long-term, decaying, context-aware |
| **Extended thinking** | No | N/A | Yes, for complex decisions |
| **Document analysis** | Generic | N/A | Integrated with context |
| **Life integration** | Chat only | N/A | Tasks, notes, calendar, smart home |
| **Voice** | No | N/A | Always-on, natural, British |
| **Local data** | No | N/A | Everything stays on your network |
| **Independence** | Cloud-only | N/A | Works without voice or web interface |

## 📈 Future Enhancements

**Coming soon**:
- Vision: Analyze images, diagrams, screenshots
- File analysis: Deep dive into documents with Claude
- Prompt caching: 90% API cost savings for repeated context
- Batch processing: Queue non-urgent research overnight
- Decision dashboard: Visualize patterns and outcomes
- Voice alarm: Wake-up with morning briefing
- Kindle UI improvements: Gesture support, swipe navigation

**Possible integrations**:
- Google Calendar sync
- Gmail integration
- Slack/Discord notifications
- Apple Health data
- Habit tracking
- Financial analysis

## 🆘 Troubleshooting

### "Claude API error"
- Check `ANTHROPIC_API_KEY` is set
- Verify key is valid at console.anthropic.com
- Check usage and rate limits

### "Voice not working"
- Check `OPENAI_API_KEY` and `ELEVENLABS_API_KEY`
- Verify microphone is connected
- Test with: `curl -X POST http://localhost:5000/api/voice/text -d '{"text":"hello"}'`

### "Documents not uploading"
- Check `/tmp/jarvis_docs/` directory exists and is writable
- File size limit is 10MB
- Supported formats: PDF, DOCX, TXT, MD

### "Home Assistant not connecting"
- Verify `HA_URL` is reachable from Jarvis location
- Check `HA_TOKEN` is valid (Settings > Devices & Services > Tokens)
- Test: `curl -H "Authorization: Bearer $HA_TOKEN" http://home-assistant.local:8123/api/states`

### "Dashboard not loading"
- Clear browser cache
- Try incognito/private window
- Check browser console for JavaScript errors
- Verify `/dashboard` route is accessible

## 📝 License

This project is built on top of Anthropic's Claude API. Use per Claude's terms of service.

## 🤝 Support

- **Documentation**: See JARVIS_DECISION_SYSTEM.md, JARVIS_DEPLOYMENT.md
- **Issues**: Check GitHub issues
- **Questions**: Refer to inline code comments and docstrings

---

**Jarvis** - Your personal AI that helps you think better, not just answer faster.

*Last updated: April 2026*
