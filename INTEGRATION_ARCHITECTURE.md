# MeGPT + Personal-Assist → Unified AI Assistant
## Complete Architecture & Integration Plan

## Executive Summary

This document outlines the complete architecture for integrating MeGPT (Chat Assistant) with Personal-Assist (Email/Calendar/Finance) into a unified personal AI assistant, following 2025-2026 design trends and optimizing for a 15k token context limit.

---

## 1. Architecture Overview

### Current State
- **MeGPT**: Clean LangGraph ReAct agent with 3-tier context (Recent + Facts + Summary), FastAPI backend, Next.js frontend
- **Personal-Assist**: Email sync (Gmail/Outlook), calendar automation, finance tracking, SQLCipher encryption, family profiles

### Unified Architecture Pattern
**Single-Model Orchestration with Domain-Specific Tools** (per 2025-2026 trend)

```
┌──────────────────────────────────────────────────────────────┐
│              MULTI-MODAL UNIFIED INTERFACE                │
│  ┌──────────┬──────────┬──────────┬────────────────┐  │
│  │ Next.js   │ CLI       │ Voice     │ Email/Calendar│  │
│  │ Chat UI   │ REPL      │ WebSocket │  Dashboard     │  │
│  └─────┬─────┴─────┬─────┴────────┬─────────┘  │
└─────────┼───────────────┼─────────────────┼─────────────────────┘
          │
    ┌──────────▼─────────────────────▼─────────────────▼─────────────────┐
│              ENHANCED FASTAPI BACKEND                      │
│  - SSE Streaming (chat)                                   │
│  - WebSocket (voice)                                      │
│  - REST API (email/calendar/finance)                      │
│  - Background sync scheduler                                   │
│  └─────────────────────┬──────────────────────────────┘     │
│                        │                                      │
│  ┌──────────▼─────────────────▼─────────────────▼─────────────────┐  │
│  │              UNIFIED LANGGRAPH AGENT                        │  │
│  │  ┌──────────────────────────────────────────────────────────┐  │  │
│  │  │  5-Node ReAct Loop:                                │  │  │
│  │  │  Recall → Reason → Tools → Respond → Memorize       │  │  │
│  │  └──────────────────────────────────────────────────────────┘  │  │  │
│  └─────────────────────┬──────────────────────────────┘     │  │
│                        │                 │                 │
┌──▼──────────────────────▼─────────────────▼─────────────────▼─────────────────┐  │
│  │              ENHANCED 4-TIER CONTEXT SYSTEM                   │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Enhanced 4-Tier Context Strategy

### Token Budget for 15k Context Limit

| Component | Tokens | Percentage | Notes |
|-----------|--------|------------|--------|
| System Prompt | 500 | 3.3% | Fixed instructions |
| Tier 1 (Recent Messages) | 1,000 | 6.7% | Last 5-7 exchanges |
| Tier 2 (Vector Facts) | 800 | 5.3% | Query-relevant via Qdrant |
| Tier 3 (Rolling Summary) | 300 | 2.0% | Updated every 5 messages |
| Tier 4 (Domain Contexts) | **800** | **5.3%** | Email/Calendar/Finance cached |
| User Input | 1,500 | 10.0% | Current query |
| LLM Reserve | 4,000 | 26.7% | Buffer for edge cases |
| Total | **8,600** | **57.3%** | **6,100 available for response** |

### Tier 4: Domain Contexts (NEW)

```python
# database.py - New tier
class DomainContextManager:
    async def get_domain_context(chat_id: str, user_id: str) -> dict:
        """
        Tier 4: Domain-specific cached context blocks
        Cached per chat to avoid repeated queries
        """
        
        # Email context (last 3 important emails, recent threads)
        email_context = await self._get_email_context(chat_id, limit=3)
        
        # Calendar context (upcoming 7 days, pending proposals)
        calendar_context = await self._get_calendar_context(chat_id, days=7)
        
        # Finance context (portfolio summary, recent alerts)
        finance_context = await self._get_finance_context(user_id)
        
        return {
            "emails": email_context,
            "calendar": calendar_context,
            "finance": finance_context,
        }
```

### Enhanced Intent Classification

```python
# database.py - Extended intent classifier
def classify_query_intent_enhanced(user_query: str) -> dict:
    """
    Extended intent classification with domain detection
    """
    classification = call_llm_classifier(f"""
Classify this query's intent and domain:

Query: "{user_query}"

Intents:
- followup: "what about X?", "continue", "more details"
- factual: "what's my email from X?", "what's on my calendar?", "what's my net worth?"
- overview: "catch me up", "what have we discussed?", "show me my emails"
- new_topic: Starts fresh, unrelated to prior context

Domains:
- email: "show me emails", "what did X say?", "search for email about..."
- calendar: "what's on my schedule?", "add event", "schedule meeting"
- finance: "how much money do I have?", "portfolio performance", "spending trends"

Return JSON:
{{
    "intent": "<intent>",
    "needs_history": true/false,
    "needs_tier4": true/false,  # Whether to include domain contexts
    "domain": "email" | "calendar" | "finance" | null
}}
""")
    
    return classification
```

### Adaptive Context Selection Logic

| Intent | Tier 1 (Recent) | Tier 2 (Facts) | Tier 3 (Summary) | Tier 4 (Domains) |
|--------|----------------|----------------|------------------|----------------|
| `followup` | limit=5 | ✓ Always | ✗ Skip | ✗ Skip |
| `factual` | limit=0 | ✓ Always | ✓ If needed | ✗ Skip |
| `overview` | limit=2 | ✓ Always | ✓ Always | ✓ Always |
| `new_topic` | limit=0 | ✓ Always | ✗ Skip | ✗ Skip |
| `email_query` | limit=0 | ✓ Always | ✓ If needed | ✗ Skip | ✓ Email |
| `calendar_query` | limit=0 | ✓ Always | ✓ If needed | ✗ Skip | ✓ Calendar |
| `finance_query` | limit=0 | ✓ Always | ✓ If needed | ✗ Skip | ✓ Finance |
| `general` | limit=3 | ✓ Always | ✓ Always | ✗ Skip | ✗ Skip |

---

## 3. Unified Database Schema

### Schema Changes for Integration

```sql
-- database.py - Unified schema with personal-assist tables

-- Existing MeGPT tables (keep)
CREATE TABLE IF NOT EXISTS chats (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    title TEXT,
    summary TEXT DEFAULT '',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    -- NEW: Domain context metadata
    last_email_sync TEXT,  -- Last email sync timestamp
    last_calendar_sync TEXT  -- Last calendar sync timestamp
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    chat_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
);

-- NEW: Emails table (from personal-assist)
CREATE TABLE IF NOT EXISTS emails (
    id TEXT PRIMARY KEY,
    chat_id TEXT,  -- Link to chat if relevant
    thread_id TEXT,
    subject TEXT NOT NULL,
    sender TEXT NOT NULL,
    body_markdown TEXT,
    body_html TEXT,
    date_received DATETIME NOT NULL,
    
    -- Classification
    priority TEXT DEFAULT 'normal',  -- 'critical' | 'important' | 'normal' | 'low' | 'spam'
    category TEXT,
    is_spam_or_scam INTEGER DEFAULT 0,
    summary TEXT,  -- LLM-generated summary
    action_items TEXT,  -- JSON array
    relevant_to TEXT,  -- JSON array of family member IDs
    processed_at DATETIME,
    
    -- Metadata
    gmail_message_id TEXT UNIQUE,
    outlook_message_id TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- NEW: Calendar events table
CREATE TABLE IF NOT EXISTS calendar_events (
    id TEXT PRIMARY KEY,
    chat_id TEXT,  -- Link to chat if generated from email
    google_calendar_id TEXT,
    
    -- Event details
    title TEXT NOT NULL,
    description TEXT,
    start_time DATETIME NOT NULL,
    end_time DATETIME NOT NULL,
    location TEXT,
    attendees TEXT,  -- JSON array
    status TEXT DEFAULT 'pending',  -- 'pending' | 'approved' | 'rejected' | 'confirmed'
    action_type TEXT,  -- 'create' | 'update' | 'delete'
    
    -- Proposal metadata
    proposal_source TEXT,  -- 'email' | 'chat'
    source_email_id TEXT,  -- If from email extraction
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- NEW: Calendar proposals (for approval workflow)
CREATE TABLE IF NOT EXISTS calendar_proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id TEXT NOT NULL,
    email_id TEXT,  -- Reference to email
    title TEXT NOT NULL,
    description TEXT,
    start_time DATETIME NOT NULL,
    end_time DATETIME NOT NULL,
    location TEXT,
    status TEXT DEFAULT 'pending',  -- 'pending' | 'approved' | 'rejected'
    action_type TEXT,
    
    approved_at DATETIME,
    approved_by TEXT,  -- User ID who approved
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- NEW: Finance tables (from personal-assist)
CREATE TABLE IF NOT EXISTS finance_accounts (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    account_type TEXT NOT NULL,  -- 'bank' | 'brokerage' | 'credit_card'
    name TEXT NOT NULL,
    provider TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS finance_assets (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    ticker_symbol TEXT NOT NULL,
    shares REAL NOT NULL,
    avg_cost REAL,
    current_value REAL,
    last_updated DATETIME,
    FOREIGN KEY (account_id) REFERENCES finance_accounts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS finance_liabilities (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    liability_type TEXT NOT NULL,  -- 'loan' | 'mortgage' | 'credit_card'
    provider TEXT,
    balance REAL NOT NULL,
    interest_rate REAL,
    monthly_payment REAL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS finance_snapshots (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    net_worth REAL NOT NULL,
    asset_allocation TEXT,  -- JSON: {"stocks": 0.7, "bonds": 0.3}
    emergency_fund_status TEXT,
    total_assets REAL,
    total_liabilities REAL,
    snapshot_date DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS finance_transactions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    date DATE NOT NULL,
    description TEXT NOT NULL,
    category TEXT,  -- 'income' | 'expense' | 'transfer'
    amount REAL NOT NULL,
    account_id TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- NEW: Family members (from personal-assist)
CREATE TABLE IF NOT EXISTS family_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_profile_id TEXT UNIQUE NOT NULL,  -- Maps to user_id
    name TEXT NOT NULL,
    relationship TEXT NOT NULL,  -- 'self' | 'spouse' | 'child' | 'parent'
    aliases TEXT,  -- JSON array
    email TEXT,
    google_calendar_id TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- NEW: Interest profiles (for deal detection)
CREATE TABLE IF NOT EXISTS interest_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    family_member_id INTEGER NOT NULL,
    category TEXT NOT NULL,  -- 'electronics' | 'running' | 'groceries' etc.
    keywords TEXT,  -- JSON array of keywords
    priority INTEGER DEFAULT 5,  -- Higher = more important
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (family_member_id) REFERENCES family_members(id) ON DELETE CASCADE
);

-- NEW: Deal alerts
CREATE TABLE IF NOT EXISTS deal_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    family_member_id INTEGER NOT NULL,
    email_id TEXT,  -- Reference to email
    title TEXT,
    deal_value REAL,
    deal_currency TEXT,
    is_valid_deal INTEGER DEFAULT 0,  -- LLM-validated
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (family_member_id) REFERENCES family_members(id) ON DELETE CASCADE
);

-- NEW: Sync state (from personal-assist)
CREATE TABLE IF NOT EXISTS sync_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL UNIQUE,
    gmail_history_id TEXT,
    outlook_delta_link TEXT,
    last_sync_at INTEGER,
    sync_window_start INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Enhanced indexes
CREATE INDEX IF NOT EXISTS idx_emails_chat ON emails(chat_id);
CREATE INDEX IF NOT EXISTS idx_emails_date ON emails(date_received);
CREATE INDEX IF NOT EXISTS idx_emails_priority ON emails(priority, date_received);
CREATE INDEX IF NOT EXISTS idx_events_chat ON calendar_events(chat_id, start_time);
CREATE INDEX IF NOT EXISTS idx_events_user ON calendar_events(start_time);
CREATE INDEX IF NOT EXISTS idx_proposals_chat ON calendar_proposals(chat_id, status);
CREATE INDEX IF NOT EXISTS idx_finance_user ON finance_snapshots(user_id, snapshot_date);
```

---

## 4. Domain-Specific Tools

### Tool Architecture

```python
# agent_graph.py - Enhanced tool registration
from langchain_core.tools import tool
from tools.email_tools import search_emails, get_email_thread
from tools.calendar_tools import get_upcoming_events, create_event, approve_proposal
from tools.finance_tools import get_portfolio_summary, get_net_worth, analyze_spending

def create_agent_graph():
    """Create enhanced agent with domain tools."""
    
    # Get LLM with tools bound
    llm = get_llm(streaming=False)
    
    # Organize tools by category
    core_tools = [web_search]
    email_tools = [search_emails, get_email_thread]
    calendar_tools = [get_upcoming_events, create_event, approve_proposal]
    finance_tools = [get_portfolio_summary, get_net_worth, analyze_spending]
    
    all_tools = core_tools + email_tools + calendar_tools + finance_tools
    llm_with_tools = llm.bind_tools(all_tools)
    
    # Tool node for execution
    tool_node = ToolNode(tools=all_tools)
```

### Email Tools Implementation

```python
# tools/email_tools.py
from langchain_core.tools import tool
from database import get_db_connection

@tool
def search_emails(query: str, limit: int = 5) -> str:
    """Search emails by content using full-text search."""
    # Implementation uses FTS5 index on emails_fts table
    pass

@tool
def get_email_thread(email_id: str) -> str:
    """Get full email thread with replies."""
    # Implementation fetches all messages with same thread_id
    pass

### Calendar Tools Implementation

```python
# tools/calendar_tools.py
from langchain_core.tools import tool

@tool
def get_upcoming_events(days: int = 7) -> str:
    """Get upcoming calendar events for next N days."""
    pass

@tool
def create_event(
    title: str,
    start_time: str,
    end_time: str,
    location: str = "",
    description: str = ""
) -> str:
    """Create a calendar event."""
    pass

@tool
def approve_proposal(proposal_id: int) -> str:
    """Approve a calendar proposal."""
    pass
```

### Finance Tools Implementation

```python
# tools/finance_tools.py
from langchain_core.tools import tool

@tool
def get_portfolio_summary(user_id: str) -> str:
    """Get financial portfolio summary."""
    pass

@tool
def get_net_worth(user_id: str) -> str:
    """Get current net worth."""
    pass

@tool
def analyze_spending(user_id: str, days: int = 30) -> str:
    """Analyze spending trends."""
    pass
```

---

## 5. Unified API Endpoints

### REST API Extensions

```python
# server.py - Enhanced API endpoints

# Email endpoints
@app.get("/api/emails")
async def list_emails(
    chat_id: str | None = None,
    limit: int = 20,
    unread_only: bool = False
):
    """List emails with filtering."""
    pass

@app.get("/api/emails/{email_id}")
async def get_email(email_id: str):
    """Get single email."""
    pass

@app.post("/api/emails/{email_id}/mark-read")
async def mark_email_read(email_id: str):
    """Mark email as read."""
    pass

# Calendar endpoints
@app.get("/api/calendar/events")
async def list_events(days: int = 7):
    """List upcoming calendar events."""
    pass

@app.get("/api/calendar/proposals")
async def list_proposals():
    """List pending calendar proposals."""
    pass

@app.post("/api/calendar/proposals/{proposal_id}/approve")
async def approve_calendar_proposal(proposal_id: int):
    """Approve a calendar proposal."""
    pass

@app.post("/api/calendar/proposals/{proposal_id}/reject")
async def reject_calendar_proposal(proposal_id: int):
    """Reject a calendar proposal."""
    pass

# Finance endpoints
@app.get("/api/finance/overview")
async def get_finance_overview(user_id: str):
    """Get financial overview."""
    pass

@app.get("/api/finance/portfolio")
async def get_portfolio(user_id: str):
    """Get portfolio details."""
    pass

@app.post("/api/finance/snapshot")
async def create_finance_snapshot(data: FinanceSnapshot):
    """Create financial snapshot."""
    pass

@app.get("/api/finance/spending")
async def get_spending_trends(days: int = 30):
    """Get spending trends."""
    pass

# Sync endpoints (background tasks)
@app.post("/api/sync/emails")
async def trigger_email_sync(background_tasks: BackgroundTasks):
    """Trigger email sync (background)."""
    pass

@app.post("/api/sync/calendar")
async def trigger_calendar_sync(background_tasks: BackgroundTasks):
    """Trigger calendar sync (background)."""
    pass
```

---

## 6. Frontend Architecture

### Component Structure

```
frontend/src/
├── app/
│   ├── dashboard/
│   │   └── page.tsx          # Main unified dashboard
│   ├── emails/
│   │   └── page.tsx          # Email management
│   ├── calendar/
│   │   ├── page.tsx          # Calendar view
│   │   └── proposals/          # Proposal approval
│   ├── finance/
│   │   ├── page.tsx          # Finance dashboard
│   │   ├── portfolio/          # Portfolio details
│   │   └── trends/             # Spending analysis
│   └── settings/
│       └── page.tsx          # Settings & theme
├── components/
│   ├── UnifiedNavigation.tsx        # Main navigation (NEW)
│   ├── GlassCard.tsx              # Reusable glassmorphism card
│   ├── StatusBadge.tsx             # Badge component
│   ├── QuickStat.tsx               # Stat widget
│   ├── CalendarEvent.tsx           # Event card
│   ├── EmailCard.tsx               # Email list item
│   └── FinanceChart.tsx            # Chart component
└── styles/
    └── themes.css                   # Theme variables
```

### Design Patterns Implemented

**Layout Patterns:**
- Bento grid for dashboard widgets
- Floating navbar with `top-0 left-4 right-4` spacing
- Consistent max-width containers (`max-w-7xl`)
- Content padding accounting for fixed navbar

**Visual Style:**
- Cleaner glassmorphism (higher transparency, clearer borders)
- Modern card design with soft shadows
- Smooth transitions (150-300ms duration)
- Subtle hover effects (color/opacity changes, scale transforms)
- Gradient backgrounds for quick stat cards

**Interaction Design:**
- No emoji icons as UI elements (use SVG from Lucide)
- Consistent icon sizing (24x24 viewBox with proper sizing)
- Cursor pointer on all interactive elements
- Hover feedback (color, shadow, border changes)
- Focus states visible for keyboard navigation

**Accessibility:**
- Never use color-only indicators for status
- Proper alt text for images
- Form inputs have labels
- Respect `prefers-reduced-motion`
- Keyboard navigation support

**Typography:**
- Professional font pairing (Outfit for body, JetBrains Mono for code)
- Clear hierarchy with consistent spacing
- Readable line lengths (45-75 characters)

**Responsive:**
- Mobile-first approach (320px, 768px, 1024px, 1440px breakpoints)
- No horizontal scroll on mobile
- Touch-friendly tap targets (44px minimum)

---

## 7. Encryption Decision

### Recommendation: **Adopt SQLCipher Encryption**

**Pros:**
- **Security**: Data encrypted at rest with AES-256
- **Privacy**: Only decrypted in memory when accessed
- **Proven**: Personal-assist uses this successfully
- **Minimal Overhead**: 5-10% performance impact with caching

**Implementation Plan:**
1. Install SQLCipher dependencies: `pip install sqlcipher3-wheels`
2. Create database migration script
3. Extend `config.py` with encryption settings
4. Import `vault_manager.py` from personal-assist
5. Update `.env.example` with new variables

---

## 8. Phased Migration Path

### Phase 1: Foundation (Weeks 1-2)

**Objective**: Merge core infrastructure and adopt encryption

**Tasks:**
1. ✅ Install SQLCipher dependencies
2. ✅ Create database migration script (`data/migrate_unified_db.py`)
3. ✅ Extend `config.py` with encryption settings
4. ✅ Import `vault_manager.py` from personal-assist
5. ✅ Merge `requirements.txt`

**Deliverables:**
- Unified encrypted database schema
- Working vault manager integration
- Updated configuration system

---

### Phase 2: Domain Integration (Weeks 3-4)

**Objective**: Integrate email, calendar, and finance tools

**Tasks:**
1. ✅ Create `tools/email_tools.py`
2. ✅ Create `tools/calendar_tools.py`
3. ✅ Create `tools/finance_tools.py`
4. ✅ Register tools in `agent_graph.py`
5. ✅ Implement background sync scheduler
6. ✅ Add REST API endpoints
7. ✅ Update 4-tier context to include domain blocks

**Deliverables:**
- Working email search and retrieval
- Calendar event management
- Portfolio overview and spending analysis
- Background sync system

---

### Phase 3: Frontend Expansion (Weeks 5-6)

**Objective**: Add UI for email/calendar/finance in Next.js

**Tasks:**
1. ✅ Create `frontend/src/app/emails/page.tsx`
2. ✅ Create `frontend/src/app/calendar/page.tsx`
3. ✅ Create `frontend/src/app/finance/page.tsx`
4. ✅ Add email/calendar/finance to main navigation
5. ✅ Implement sync progress indicators
6. ✅ Add calendar proposal approval UI

**Deliverables:**
- Email browsing interface
- Calendar view with proposal management
- Finance dashboard
- Unified navigation

---

### Phase 4: Voice/Multi-Modal (Weeks 7-8) [OPTIONAL]

**Objective**: Add voice input/output capabilities

**Tasks:**
1. ✅ Create `tools/voice_tool.py` (Whisper + TTS)
2. ✅ Add WebSocket endpoint for audio streaming
3. ✅ Add voice controls to chat UI
4. ✅ Implement audio transcription caching
5. ✅ Add TTS streaming

**Deliverables:**
- Voice-to-text transcription
- Text-to-speech synthesis
- Audio streaming interface

**Note**: This phase can be deferred if voice is not a priority.

---

## 9. Token Optimization Strategy

### Context Strategy Comparison

| Strategy | Token Usage | Quality | Implementation Effort |
|-----------|--------------|---------|---------------------|
| Current 3-Tier | ~2,800 tokens | High | Low (already implemented) |
| Enhanced 4-Tier | ~3,600 tokens | High | Medium |
| Provence Pruning | ~1,200 tokens (60% reduction) | Medium-High | High |
| Hierarchical Memory | ~1,500 tokens | High | High |
| Sliding Window + Summarization | ~2,000 tokens | Medium-High | Medium |

### Recommendation

**Keep 3-tier for now, add Tier 4 domains, measure usage, then consider advanced techniques if needed.**

The current 3-tier approach is cost-effective and working well. Adding Tier 4 for domain-specific context (email/calendar/finance) will provide the additional intelligence needed without overwhelming the LLM.

---

## 10. Architecture Best Practices Applied

### ✅ Implemented Already
- [x] Streaming-First: MeGPT uses SSE streaming
- [x] LangGraph Orchestration: Proven ReAct pattern
- [x] 3-Tier Context: Working adaptive system
- [x] Privacy-First: Local LLM, local vector DB
- [x] Checkpointing: LangGraph supports state persistence

### 🔜 Enhancements Needed
- [ ] Hierarchical Memory: Consider if 4-tier insufficient
- [ ] Context Pruning: Implement if token pressure detected
- [ ] Tool Call Optimization: "Less is More" for tool selection
- [ ] Caching Layer: Redis for high-frequency queries
- [ ] Monitoring: OpenTelemetry for observability
- [ ] Guardrails: Input validation, output filtering

---

## 11. Risk Assessment & Mitigation

### High-Risk Areas

| Risk | Impact | Likelihood | Mitigation |
|-------|---------|-------------|------------|
| Database Migration | High | Medium | Use migration scripts, rollback capability |
| Encryption Overhead | Medium | Low | 5-10% perf hit acceptable |
| Context Explosion | High | Medium | Enforce token budgets, monitor usage |
| Background Sync Conflicts | Medium | Low | Use locks, queue tasks, retry with exponential backoff |
| LLM Tool Hallucination | High | High | Validate tool outputs |

---

## 12. Final Recommendations

### Immediate Actions (This Week)

1. ✅ Review Architecture Document
2. ✅ Create Feature Branch: `git checkout -b feature/unified-assistant`
3. ✅ Start Phase 1: Begin database migration and encryption adoption
4. ✅ Test Personal-Assist: Run personal-assist sync to understand data patterns
5. ✅ Set Up Monitoring: Add logging/token tracking for optimization insights

### Priority Features to Integrate

| Priority | Feature | Effort | Value |
|----------|-----------|---------|--------|
| P0 (Critical) | Email sync & search | Medium | HIGH - Personal data access |
| P0 (Critical) | Calendar events & proposals | Medium | HIGH - Scheduling automation |
| P1 (High) | Portfolio overview | Low | MEDIUM - Financial visibility |
| P1 (High) | Spending trends | Low | MEDIUM - Financial tracking |
| P2 (Medium) | Deal detection | High | MEDIUM - Family value |
| P3 (Low) | Voice I/O | High | LOW - Nice to have |
| P3 (Low) | YouTube summary | Low | LOW - Convenient feature |

### Long-Term Enhancements (Q2 2026)

- Advanced context pruning (Provence-style)
- Hierarchical memory with multi-level summaries
- Multi-modal context (text + images)
- Tool usage analytics and optimization
- Automated deal purchasing (if desired)
- Investment insights and recommendations

---

## Conclusion

**Unified Assistant Feasibility**: ✅ **HIGHLY FEASIBLE**

**Recommended Approach**: **Single-Model Monolithic LangGraph with 4-Tier Enhanced Context**

**Timeline**: **8-12 weeks** for full integration

**Risk Level**: **Medium** (manageable with phased approach, backup, rollback)

**Key Success Factors**:
1. Preserve MeGPT's clean LangGraph architecture
2. Add domain-specific tools (email/calendar/finance)
3. Adopt SQLCipher encryption for privacy
4. Extend 3-tier context to 4-tier with domain blocks
5. Maintain token budgeting for 15k limit
6. Follow 2025-2026 trends (streaming, checkpointing, guardrails)
7. Modern, accessible design with proper contrast
8. Clean glassmorphism and responsive layouts

**The unified system will provide:**
- Unified chat interface for conversations
- Email access and search capabilities
- Calendar automation and proposal workflow
- Financial oversight and insights
- Privacy-first local LLM operation
- Optimized token usage for 15k context window

---

## Appendix: File Structure Reference

### New Components Created

1. `frontend/src/components/UnifiedNavigation.tsx` - Main navigation with domain switching
2. `frontend/src/app/dashboard/page.tsx` - Unified dashboard with bento grid stats
3. `frontend/src/app/globals.css` - Enhanced theme variables and cleaner glassmorphism

### Backend Extensions Needed

1. `tools/email_tools.py` - Email search and thread view
2. `tools/calendar_tools.py` - Calendar event management
3. `tools/finance_tools.py` - Finance portfolio and spending analysis
4. `database.py` - Enhanced with domain context manager and Tier 4
5. `server.py` - REST API endpoints for all domains
6. `data/migrate_unified_db.py` - Database migration script

### Migration Scripts Needed

1. Database schema migration
2. Data migration from personal-assist (if applicable)
3. Encryption key generation and vault setup
4. Rollback capability before migration

---

**END OF DOCUMENT**

*This architecture plan provides a complete roadmap for integrating MeGPT with personal-assist, creating a unified AI assistant that follows modern design trends while optimizing for a 15k token context limit.*
