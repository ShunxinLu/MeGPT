# Phase 6: Domain Integration Plan

## Executive Summary

Phase 6 focuses on integrating email, calendar, and finance capabilities into MeGPT to create a unified personal AI assistant. The UI/UX designs are already complete; this phase focuses on backend implementation and API integration.

---

## Phase 6 Decision Rationale

### Why New Features vs Further Optimization?

**Performance Analysis:**
- Chat completion time: ~10 seconds average
- Reason node (LLM inference): ~4s (35-40%)
- Memorize node (memory save): ~4.1s (38-40%)
- Recall node (context retrieval): ~2.2s (20-22%)

**Assessment:**
1. **Performance is ACCEPTABLE**: 10 seconds for local 30B model is reasonable
2. **Optimizations have DIMINISHING RETURNS**: Further gains require major refactoring
3. **HIGH VALUE FEATURES AVAILABLE**: Email/Calendar/Finance integration ready
4. **UI/UX ALREADY COMPLETE**: Frontend designs ready to connect

**Decision**: **Phase 6 = Domain Integration** (email, calendar, finance)

---

## Phase 6 Scope

### Goal
Integrate email, calendar, and finance capabilities into MeGPT to create a unified personal assistant with persistent long-term memory.

### Timeline
**8-12 weeks** (as per `INTEGRATION_ARCHITECTURE.md`)

---

## Phase 6.1: Foundation (Weeks 1-2)

### Objective
Merge core infrastructure and adopt encryption for unified assistant.

### Tasks

1. ✅ SQLCipher Encryption Setup
   - Install dependencies: `pip install sqlcipher3-wheels`
   - Import `vault_manager.py` from personal-assist
   - Extend `config.py` with encryption settings
   - Update `.env.example` with new variables

2. ✅ Database Schema Migration
   - Create `data/migrate_unified_db.py` script
   - Add unified tables to `database.py`:
     - `emails` table
     - `calendar_events` table
     - `calendar_proposals` table
     - `finance_accounts` table
     - `finance_assets` table
     - `finance_liabilities` table
     - `finance_snapshots` table
     - `finance_transactions` table
     - `family_members` table
     - `interest_profiles` table
     - `deal_alerts` table
     - `sync_state` table
   - Add indexes for performance

3. ✅ Merge Requirements
   - Merge personal-assist requirements into `requirements.txt`

### Deliverables
- Unified encrypted database schema
- Working vault manager integration
- Updated configuration system

---

## Phase 6.2: Domain Integration (Weeks 3-4)

### Objective
Integrate email, calendar, and finance tools into MeGPT agent.

### Tasks

1. ✅ Email Tools Implementation (`tools/email_tools.py`)
   - `search_emails(query, limit)` - Search emails by content using FTS5
   - `get_email_thread(email_id)` - Get full email thread with replies
   - Integrate Gmail/Outlook APIs for sync
   - Implement email classification (critical/important/spam)
   - Add LLM-based summarization and action item extraction

2. ✅ Calendar Tools Implementation (`tools/calendar_tools.py`)
   - `get_upcoming_events(days)` - Get upcoming calendar events
   - `create_event(title, start_time, end_time, location, description)` - Create calendar event
   - `approve_proposal(proposal_id)` - Approve a calendar proposal
   - Integrate Google Calendar API
   - Implement proposal approval workflow

3. ✅ Finance Tools Implementation (`tools/finance_tools.py`)
   - `get_portfolio_summary(user_id)` - Get financial portfolio summary
   - `get_net_worth(user_id)` - Get current net worth
   - `analyze_spending(user_id, days)` - Analyze spending trends
   - Calculate asset allocation
   - Track financial goals

4. ✅ Tool Registration
   - Register email tools in `agent_graph.py`
   - Register calendar tools in `agent_graph.py`
   - Register finance tools in `agent_graph.py`
   - Update `ALL_TOOLS` list

5. ✅ Background Sync Scheduler
   - Implement periodic email sync
   - Implement periodic calendar sync
   - Use queue for background tasks
   - Add retry with exponential backoff

6. ✅ 4-Tier Context Enhancement (`database.py`)
   - Add `DomainContextManager` class
   - Implement `get_domain_context(chat_id, user_id)` method
   - Cache domain contexts per chat
   - Update intent classification to detect domain queries

7. ✅ REST API Extensions (`server.py`)
   - Email endpoints: `/api/emails`, `/api/emails/{id}`, `/api/emails/{id}/mark-read`
   - Calendar endpoints: `/api/calendar/events`, `/api/calendar/proposals`, `/api/calendar/proposals/{id}/approve`
   - Finance endpoints: `/api/finance/overview`, `/api/finance/portfolio`, `/api/finance/snapshot`, `/api/finance/spending`
   - Sync endpoints: `/api/sync/emails`, `/api/sync/calendar`

### Deliverables
- Working email search and retrieval
- Calendar event management with proposal approval
- Portfolio overview and spending analysis
- Background sync system
- REST API endpoints for all domains

---

## Phase 6.3: Frontend Integration (Weeks 5-6)

### Objective
Connect existing frontend UI designs to backend APIs.

### Tasks

1. ✅ Connect Email Page (`frontend/src/app/emails/page.tsx`)
   - Implement data fetching from `/api/emails`
   - Add search and filtering
   - Implement email detail/thread view
   - Add action buttons (mark read, archive, delete)
   - Display priority badges and action items

2. ✅ Connect Calendar Page (`frontend/src/app/calendar/page.tsx`)
   - Implement data fetching from `/api/calendar/events`
   - Display upcoming events
   - Implement proposal approval UI
   - Add source indicators (email/chat/manual)
   - Display attendee lists and status badges

3. ✅ Connect Finance Page (`frontend/src/app/finance/page.tsx`)
   - Implement data fetching from `/api/finance/overview`
   - Display net worth and asset allocation
   - Show portfolio with gain/loss
   - Track financial goals
   - Display transaction history

4. ✅ Enhanced Navigation (`frontend/src/components/UnifiedNavigation.tsx`)
   - Add domain switching (Chat, Email, Calendar, Finance, Settings)
   - Display real-time badge counts
   - Connect bento grid quick stats to APIs
   - Update active state indicators

5. ✅ Sync Progress Indicators
   - Add sync status to pages
   - Display progress bars for background tasks
   - Show last sync timestamps
   - Add manual sync triggers

### Deliverables
- Email browsing interface connected to backend
- Calendar view with proposal management connected
- Finance dashboard connected to backend
- Unified navigation with real-time stats
- Sync progress indicators

---

## Optional Phase 6.4: Voice/Multi-Modal (Weeks 7-8)

### Objective
Add voice input/output capabilities.

### Tasks

1. ✅ Voice Tool Implementation (`tools/voice_tool.py`)
   - Implement Whisper for speech-to-text
   - Implement TTS for text-to-speech
   - Add audio transcription caching
   - Implement TTS streaming

2. ✅ WebSocket Endpoint
   - Add `/ws/audio-stream` endpoint for audio streaming
   - Handle bidirectional audio streams

3. ✅ Voice UI Components
   - Add voice controls to chat UI
   - Implement microphone button
   - Add audio visualization

### Note
This phase can be deferred if voice is not a priority.

---

## Success Criteria

### Phase 6 Complete When:
- [x] SQLCipher encryption integrated and tested
- [x] Database schema migration successful
- [x] Email tools working (search, retrieval, sync)
- [x] Calendar tools working (events, proposals, approval)
- [x] Finance tools working (portfolio, spending, goals)
- [x] All tools registered in agent graph
- [x] REST API endpoints functional
- [x] Frontend pages connected to APIs
- [x] Real-time badge counts working
- [x] Sync progress indicators working
- [x] Background scheduler operational
- [ ] (Optional) Voice input/output working

---

## Risk Assessment

### High-Risk Areas

| Risk | Impact | Likelihood | Mitigation |
|-------|---------|-------------|------------|
| Database Migration | High | Medium | Use migration scripts, rollback capability, test thoroughly |
| API Integration (Gmail/Outlook/Google Calendar) | High | Medium | Handle rate limiting, implement token refresh, test with test accounts |
| Background Sync Conflicts | Medium | Low | Use locks, queue tasks, retry with exponential backoff |
| LLM Tool Hallucination | High | High | Validate tool outputs, add guardrails |
| Performance Impact | Medium | Medium | Monitor resource usage, implement caching, optimize queries |

---

## Performance Considerations

### Current Baseline
- Chat completion: ~10 seconds
- Memory retrieval: 46ms (with cache)
- Database queries: < 6ms

### Expected Impact
- Additional tool calls may add 2-5 seconds per query
- Domain context adds ~600 tokens to context (within 15k limit)
- Background sync uses minimal resources when idle

### Optimization Strategies
1. Cache domain contexts (Tier 4) per chat
2. Use FTS5 indexes for email search
3. Implement async parallel execution for independent queries
4. Stream tool outputs when possible
5. Monitor and optimize hot queries

---

## Next Steps

1. Review and approve this plan
2. Create feature branch: `git checkout -b feature/phase6-domain-integration`
3. Begin Phase 6.1: SQLCipher encryption setup
4. Set up monitoring and logging for integration work
5. Track progress with TODO list

---

## References

- `INTEGRATION_ARCHITECTURE.md` - Complete architecture document
- `UI_UX_DESIGN_COMPLETE.md` - Frontend designs already complete
- `frontend/src/app/emails/page.tsx` - Email UI component
- `frontend/src/app/calendar/page.tsx` - Calendar UI component
- `frontend/src/app/finance/page.tsx` - Finance UI component
- `frontend/src/components/UnifiedNavigation.tsx` - Navigation component

---

**END OF PHASE 6 PLAN**
