"""
MeGPT Agent Graph - Enhanced with Domain Integration
Unified architecture: LangGraph ReAct loop with 4-tier memory + domain-specific tools
Integrates: Chat, Email, Calendar
"""

import asyncio
import logging
from typing import TypedDict, List, Literal, Optional, Union
from concurrent.futures import ThreadPoolExecutor
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    BaseMessage,
)
from langchain_core.runnables import RunnableConfig
from langchain_core.prompts import ChatPromptTemplate

from config import config, estimate_tokens, truncate_to_token_limit, get_context_budget
from utils.llm_factory import get_llm
from tools.memory_tool import (
    retrieve_context,
    save_interaction,
    MEMORY_TOOLS,
    get_urgent_reminders,
    get_unread_emails_summary,
)
from tools.web_search import web_search
from database import get_adaptive_context, get_summary

# Import custom exceptions
from exceptions import (
    MeGPTError,
    DatabaseError,
    DomainError,
    LLMError,
    MemoryServiceError,
    wrap_exception,
    is_retryable_error,
)

# Import domain-specific tools
from tools.email_tools import EMAIL_TOOLS
from tools.calendar_tools import CALENDAR_TOOLS
from tools.vision_tools import VISION_TOOLS
from tools.garmin_tools import HEALTH_TOOLS

# Get logger (logging is configured in server.py)
logger = logging.getLogger(__name__)


def _extract_text_from_content(content: Union[str, List]) -> str:
    """Extract text from AIMessage content which can be str or list."""
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and "text" in item:
                parts.append(item["text"])
            else:
                parts.append(str(item))
        return " ".join(parts)
    else:
        return str(content)


# ========== System Prompt ==========
SYSTEM_PROMPT = """You are MeGPT, a helpful AI assistant with persistent long-term memory, web search, and domain-specific tools.

[LONG-TERM MEMORY - Facts about the user]
{memory_facts}

[CONVERSATION SUMMARY]
{conversation_summary}

## Your Capabilities:
1. **Long-term Memory**: You remember facts about the user across conversations
2. **Web Search**: Use `web_search` for current/real-time information (prices, news, weather)
3. **Email Tools**: You can search and retrieve the user's REAL emails:
   - `list_unread_emails` - Get unread emails from inbox
   - `search_emails` - Search emails by content/subject
   - `get_email_thread` - Get full email conversation
   - `get_email_count` - Get email counts by priority
4. **Calendar Tools**: You can view and manage the user's REAL calendar:
   - `get_upcoming_events` - View upcoming calendar events
   - `create_event` - Create new calendar events
   - `update_event` / `delete_event` - Modify events
5. **Health Tools**: You can access the user's REAL health data from Garmin:
   - `get_health_summary` - Get daily health metrics (steps, HR, calories, stress, Body Battery)
   - `get_recent_workouts` - View recent workout activities
   - `get_sleep_data` - Get sleep analysis and quality
   - `get_health_trends` - Analyze health patterns over time
   - `get_upcoming_events` - View upcoming calendar events
   - `create_event` - Create new calendar events
   - `update_event` / `delete_event` - Modify events

## CRITICAL RULES:
- **NEVER HALLUCINATE DATA**. If asked about emails, calendar, news, prices, etc., you MUST use the appropriate tool.
- When user asks about "emails", "inbox", "messages" -> USE email tools (list_unread_emails, search_emails)
- When user asks about "calendar", "schedule", "meetings" -> USE calendar tools (get_upcoming_events)
- When user asks about "health", "fitness", "sleep", "steps", "workout" -> USE health tools (get_health_summary)
- When user asks about current events, prices, news -> USE web_search
- If a tool returns "no results", tell the user honestly - don't make up fake data

## TOOL USAGE RULES (IMPORTANT):
- **ALWAYS give a complete answer after getting tool results** - don't just say "let me check" and call another tool
- **DO NOT call the same tool twice with the same query** - if search_emails returned results, use those results
- **DO NOT repeatedly call get_email_thread if it returns "no results"** - move on and answer with what you have
- After using tools, synthesize the information into a helpful response for the user
- If tool results don't perfectly match the user's question, say what you found and ask for clarification

## Guidelines:
- Be conversational and helpful
- Use tools proactively when the user's question requires external data
- Format responses clearly with markdown
- Be concise but thorough
"""



# ========== Agent State ==========
class AgentState(TypedDict, total=False):
    """State passed between nodes in graph."""

    messages: list[BaseMessage]
    user_input: str
    chat_id: Optional[str]
    user_id: Optional[str]
    context: dict  # {facts, summary, recent, domains, intent}
    final_response: str
    tool_call_count: int
    # Performance tracking
    timing: dict  # {"recall": 0.0, "reason": 0.0, "tools": 0.0, "respond": 0.0, "memorize": 0.0}


# ========== Tool Registration ==========
# All tools are registered here for easy access
ALL_TOOLS = [
    *EMAIL_TOOLS,
    *CALENDAR_TOOLS,
    *HEALTH_TOOLS,
    *VISION_TOOLS,
    *MEMORY_TOOLS,
    web_search,
]


# ========== Helper Functions ==========


def _get_llm_with_tools(streaming: bool = False):
    """Get LLM with tools bound - extracted to avoid duplication."""
    llm = get_llm(streaming=streaming)
    return llm.bind_tools(ALL_TOOLS)


def _create_initial_state(
    user_input: str, chat_id: Optional[str], user_id: str
) -> AgentState:
    """Create initial state for agent execution - extracted to avoid duplication."""
    return {
        "messages": [],
        "user_input": user_input,
        "chat_id": chat_id,
        "user_id": user_id or config.user_id,
        "context": {},
        "final_response": "",
        "tool_call_count": 0,
        "timing": {},  # Initialize timing dict
    }


def create_agent_graph():
    """Create and compile LangGraph agent."""

    # Tool node for executing tools
    tool_node = ToolNode(ALL_TOOLS)

    # Build workflow
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("recall", recall_node)
    workflow.add_node("reason", reason_node)
    workflow.add_node("tools", tool_node)
    workflow.add_node("answer", answer_node)  # New: forces LLM to answer without tools
    workflow.add_node("respond", respond_node)
    workflow.add_node("memorize", memorize_node)

    # Set conditional edges
    workflow.add_conditional_edges(
        "reason", should_continue, {"tools": "tools", "respond": "respond"}
    )
    # After tools, ALWAYS go to answer (forces final response, no more tools)
    workflow.add_edge("tools", "answer")
    workflow.add_edge("answer", "respond")
    workflow.add_edge("respond", "memorize")
    workflow.add_edge("recall", "reason")

    # Set entry point
    workflow.set_entry_point("recall")

    # Compile graph
    return workflow.compile()


# ========== Node Functions ==========


def recall_node(state: AgentState) -> AgentState:
    """Node 1: Recall - Fetch adaptive 3-Tier + Tier 4 context based on query intent."""
    import time

    start_time = time.perf_counter()
    user_input = state.get("user_input", "")
    chat_id = state.get("chat_id")
    user_id = state.get("user_id") or config.user_id

    logger.info("Recall node: Fetching adaptive context...")

    try:
        # Use enhanced context with domain contexts
        adaptive_result = get_adaptive_context(user_input, chat_id, user_id)
        context = adaptive_result.get("context", {})

        exec_time = time.perf_counter() - start_time
        timing = state.get("timing", {})
        timing["recall"] = exec_time

        logger.info(f"Recall node completed in {exec_time:.3f}s")
        return {**state, "context": context, "timing": timing}
    except DatabaseError as e:
        logger.warning(f"Database error fetching context: {e}")
        # Return empty context on failure
        exec_time = time.perf_counter() - start_time
        timing = state.get("timing", {})
        timing["recall"] = exec_time
        return {
            **state,
            "context": {
                "facts": "No prior facts available.",
                "summary": "No summary available.",
                "recent": "",
                "domains": {},
            },
            "timing": timing,
        }
    except Exception as e:
        wrapped = wrap_exception(
            e, DomainError, operation="recall_node", user_id=user_id, chat_id=chat_id
        )
        logger.warning(f"Context fetch failed: {wrapped}")
        # Return empty context on failure
        exec_time = time.perf_counter() - start_time
        timing = state.get("timing", {})
        timing["recall"] = exec_time
        return {
            **state,
            "context": {
                "facts": "No prior facts available.",
                "summary": "No summary available.",
                "recent": "",
                "domains": {},
            },
            "timing": timing,
        }


def reason_node(state: AgentState) -> AgentState:
    """Node 2: Reason - LLM decides response or tool use."""
    import time

    start_time = time.perf_counter()
    context = state.get("context", {})
    messages = state.get("messages", [])
    user_input = state.get("user_input", "")

    logger.info("Reason node: Thinking...")

    # Build comprehensive prompt with context
    facts = context.get("facts", "") or "No prior facts available."
    summary = context.get("summary", "") or "No conversation summary yet."

    # Get recent history from database
    recent_history_str = context.get("recent", "")  # Fixed: was "recent_history"

    # Domain contexts
    domains = context.get("domains", {})
    emails = domains.get("emails", "")
    calendar = domains.get("calendar", "")

    # Email & Reminder awareness - inject urgent items
    # Only add if not already present in domain contexts
    urgent_reminders = get_urgent_reminders()
    unread_emails = get_unread_emails_summary()

    if urgent_reminders and not urgent_reminders.startswith("[URGENT REMINDERS]"):
        emails = f"{emails}\n\n{urgent_reminders}" if emails else urgent_reminders
    if unread_emails and not unread_emails.startswith("[UNREAD IMPORTANT EMAILS]"):
        emails = f"{emails}\n\n{unread_emails}" if emails else unread_emails

    # Calculate context budget and truncate if needed
    # Reserve tokens for system prompt template, user input, and response
    user_input_tokens = estimate_tokens(user_input)
    base_system_tokens = estimate_tokens(SYSTEM_PROMPT.format(
        memory_facts="{memory_facts}",
        conversation_summary="{conversation_summary}",
    ))
    reserved_tokens = base_system_tokens + user_input_tokens + 500  # 500 for response overhead

    # Available tokens for context components
    context_budget = get_context_budget() - reserved_tokens
    if context_budget < 500:
        context_budget = 500  # Minimum safe budget

    # Truncate context components to fit budget
    # Priority: summary > facts > recent > domains
    facts_tokens = estimate_tokens(facts)
    summary_tokens = estimate_tokens(summary)
    recent_tokens = estimate_tokens(recent_history_str)
    emails_tokens = estimate_tokens(emails) if emails else 0
    calendar_tokens = estimate_tokens(calendar) if calendar else 0

    # Start with budget allocation
    facts_budget = int(context_budget * 0.25)  # 25% for facts
    summary_budget = int(context_budget * 0.35)  # 35% for summary
    recent_budget = int(context_budget * 0.25)  # 25% for recent history
    domains_budget = int(context_budget * 0.15)  # 15% for domains

    # Truncate if needed
    if facts_tokens > facts_budget:
        facts = truncate_to_token_limit(facts, facts_budget)
    if summary_tokens > summary_budget:
        summary = truncate_to_token_limit(summary, summary_budget)
    if recent_tokens > recent_budget:
        recent_history_str = truncate_to_token_limit(recent_history_str, recent_budget)

    # Domain contexts share a budget
    domains_text = ""
    if emails or calendar:
        total_domains_tokens = emails_tokens + calendar_tokens
        if total_domains_tokens > domains_budget:
            # Allocate proportionally
            if emails and calendar:
                email_ratio = emails_tokens / total_domains_tokens
                email_budget = int(domains_budget * email_ratio)
                calendar_budget = domains_budget - email_budget
                emails = truncate_to_token_limit(emails, email_budget)
                calendar = truncate_to_token_limit(calendar, calendar_budget)
            elif emails:
                emails = truncate_to_token_limit(emails, domains_budget)
            elif calendar:
                calendar = truncate_to_token_limit(calendar, domains_budget)

        if emails:
            domains_text += f"\n\n[RECENT EMAILS]\n{emails}"
        if calendar:
            domains_text += f"\n\n[UPCOMING CALENDAR]\n{calendar}"

    # System prompt with all contexts
    system_content = SYSTEM_PROMPT.format(
        memory_facts=facts,
        conversation_summary=summary,
    )
    system_content += domains_text

    # Log token usage for debugging
    total_context_tokens = (
        estimate_tokens(system_content) +
        estimate_tokens(recent_history_str) +
        user_input_tokens
    )
    logger.debug(f"Context window usage: ~{total_context_tokens} tokens (budget: {get_context_budget()})")

    # Build message sequence:
    # 1. System: Core instructions + All contexts
    full_messages: List[BaseMessage] = []
    full_messages.append(SystemMessage(content=system_content))

    # 2. Include previous messages (AIMessage with tool calls, ToolMessage with results, etc.)
    # This is critical so the LLM sees what tools were already called
    for msg in messages:
        full_messages.append(msg)

    # 3. Recent history dump (bridges gap between summary and current input)
    if recent_history_str:
        history_refresh = f"""
RECENT CONVERSATION HISTORY (from database):
{recent_history_str}
"""
        full_messages.append(SystemMessage(content=history_refresh))

    # 4. Current user input (only if messages is empty or last message isn't the same user input)
    if not messages or not (isinstance(messages[-1], HumanMessage) and messages[-1].content == user_input):
        full_messages.append(HumanMessage(content=user_input))

    # Get LLM with tools bound
    logger.debug("Calling LLM with comprehensive context...")
    llm_with_tools = _get_llm_with_tools(streaming=False)
    response = llm_with_tools.invoke(full_messages)

    logger.debug(f"LLM response received: {len(response.content)} chars")

    # Check for tool calls
    has_tool_calls = hasattr(response, "tool_calls") and response.tool_calls
    if has_tool_calls:
        logger.debug(
            f"Tool calls detected: {[tc.get('name') for tc in response.tool_calls]}"
        )

    new_messages = messages + [response]

    # Increment tool call count only if tools were actually called
    current_count = state.get("tool_call_count", 0)
    tool_count = current_count + (1 if has_tool_calls else 0)

    exec_time = time.perf_counter() - start_time
    timing = state.get("timing", {})
    timing["reason"] = exec_time

    logger.info(f"Reason node completed in {exec_time:.3f}s")
    return {
        **state,
        "messages": new_messages,
        "tool_call_count": tool_count,
        "timing": timing,
    }


def should_continue(state: AgentState) -> Literal["tools", "respond"]:
    """Edge condition: Check if we need to call more tools."""
    messages = state.get("messages", [])
    tool_call_count = state.get("tool_call_count", 0)

    logger.debug("Checking if more tools needed...")

    # Safety: Force response after too many tool calls to prevent infinite loops
    MAX_TOOL_CALLS = 10
    if tool_call_count >= MAX_TOOL_CALLS:
        logger.warning(f"Tool call limit reached ({MAX_TOOL_CALLS}), forcing response...")
        return "respond"

    # Check for repeated tool calls (infinite loop detection)
    if tool_call_count >= 3:
        recent_tools = []
        for msg in messages[-10:]:  # Check last 10 messages
            if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    recent_tools.append(tc.get("name", ""))

        # If we see the same tool 3+ times in recent history, force response
        from collections import Counter
        tool_counts = Counter(recent_tools)
        for tool_name, count in tool_counts.items():
            if count >= 3:
                logger.warning(f"Detected repeated tool calls ({tool_name} x{count}), forcing response...")
                return "respond"

    # Check last message for tool calls
    if not messages:
        logger.debug("No messages yet, responding...")
        return "respond"

    last_message = messages[-1]

    # Check if last message is an AIMessage with tool calls
    if isinstance(last_message, AIMessage):
        # Check if there are tool_calls to execute
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            logger.debug(f"Tool calls detected: {[tc.get('name') for tc in last_message.tool_calls]}")
            return "tools"

    # No tool calls, proceed to respond
    logger.debug("No tool calls, proceeding to respond...")
    return "respond"


def answer_node(state: AgentState) -> AgentState:
    """Node: Force LLM to give final answer WITHOUT tools (breaks tool-calling loop)."""
    import time

    start_time = time.perf_counter()
    context = state.get("context", {})
    messages = state.get("messages", [])
    user_input = state.get("user_input", "")

    logger.info("Answer node: Forcing final response...")

    # Build comprehensive prompt with context (same as reason_node)
    facts = context.get("facts", "") or "No prior facts available."
    summary = context.get("summary", "") or "No conversation summary yet."
    recent_history_str = context.get("recent", "")

    # Domain contexts
    domains = context.get("domains", {})
    emails = domains.get("emails", "")
    calendar = domains.get("calendar", "")

    # Inject urgent items
    urgent_reminders = get_urgent_reminders()
    unread_emails = get_unread_emails_summary()
    if urgent_reminders and not urgent_reminders.startswith("[URGENT REMINDERS]"):
        emails = f"{emails}\n\n{urgent_reminders}" if emails else urgent_reminders
    if unread_emails and not unread_emails.startswith("[UNREAD IMPORTANT EMAILS]"):
        emails = f"{emails}\n\n{unread_emails}" if emails else unread_emails

    # Build system prompt with ANSWER mode
    system_content = SYSTEM_PROMPT.format(
        memory_facts=facts,
        conversation_summary=summary,
    )

    # Add domain contexts
    if emails or calendar:
        if emails:
            system_content += f"\n\n[RECENT EMAILS]\n{emails}"
        if calendar:
            system_content += f"\n\n[UPCOMING CALENDAR]\n{calendar}"

    # Add explicit instruction to ANSWER (not call tools)
    system_content += """

## IMPORTANT: You must now provide your final answer.
Based on the tool results above, give a complete and helpful response to the user.
Do NOT call any more tools - just synthesize the information you have and answer.
If you found relevant information, share it. If not, say so honestly.
"""

    # Build messages for LLM (NO TOOLS this time!)
    # Keep it simple: System message with all context, then Human message with user input
    tool_results_text = ""
    from langchain_core.messages import ToolMessage

    # Extract tool results
    for msg in messages:
        if isinstance(msg, ToolMessage):
            tool_name = getattr(msg, 'name', 'tool')
            tool_results_text += f"\n\n--- Result from {tool_name} ---\n{msg.content}\n"

    # Build system prompt with tool results embedded
    if tool_results_text:
        system_content += f"""

[TOOL RESULTS - Information retrieved for you]
{tool_results_text}

Based on these tool results, please provide your final answer to the user's question.
Share the relevant information you found. If the results don't fully answer the question,
explain what you found and ask for any clarification needed.
"""
    else:
        system_content += """

[No tools were executed]
Please answer the user's question based on your knowledge and the context provided above.
"""

    # Simple message structure: System + Human
    full_messages: List[BaseMessage] = [
        SystemMessage(content=system_content),
        HumanMessage(content=user_input),
    ]

    # Call LLM WITHOUT tools
    logger.debug("Calling LLM without tools to force final answer...")
    llm_no_tools = get_llm(streaming=False)
    response = llm_no_tools.invoke(full_messages)

    final_response = _extract_text_from_content(response.content)

    exec_time = time.perf_counter() - start_time
    timing = state.get("timing", {})
    timing["answer"] = exec_time

    logger.info(f"Answer node completed in {exec_time:.3f}s")
    return {
        **state,
        "messages": messages + [response],
        "final_response": final_response,
        "timing": timing,
    }


def respond_node(state: AgentState) -> AgentState:
    """Node 4: Extract final response from reason_node (no extra LLM call)."""
    import time
    from langchain_core.messages import ToolMessage

    start_time = time.perf_counter()
    messages = state.get("messages", [])
    tool_call_count = state.get("tool_call_count", 0)
    final_response = state.get("final_response", "")

    logger.info("Respond node: Extracting final response...")

    # Extract response from last AIMessage if not already set
    if not final_response:
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                final_response = _extract_text_from_content(msg.content)
                break

    # If we hit the tool call limit, synthesize a proper answer from tool results
    # This handles the case where LLM kept calling tools but never gave a final answer
    if tool_call_count >= 10 and (not final_response or len(final_response) < 200):
        logger.debug(f"Tool limit hit, synthesizing response from tool results...")

        # Collect all tool results
        tool_results = []
        for msg in messages:
            if isinstance(msg, ToolMessage):
                tool_results.append(str(msg.content))

        if tool_results:
            # Build a synthesized response from tool results
            # Check if we have email search results
            email_results = [r for r in tool_results if "Drop" in r or "order" in r.lower() or "shipping" in r.lower()]

            if email_results:
                final_response = f"Based on your emails, I found:\n\n" + "\n\n".join(email_results[:3])
                logger.debug("Synthesized response from email results")
            else:
                final_response = "I searched your emails but couldn't find specific delivery information. " + \
                               "Here's what I found:\n\n" + "\n\n".join(tool_results[:3])
                logger.debug("Synthesized response from tool results")
        else:
            final_response = "I apologize, but I couldn't find the information you're looking for. " \
                           "The search didn't return any results."

    # Fallback: if still no response, try basic tool results join
    if not final_response:
        # Look for tool results and format them
        tool_results = []
        for msg in messages:
            if isinstance(msg, ToolMessage):
                tool_results.append(str(msg.content))

        if tool_results:
            # Join tool results as fallback response
            final_response = "\n\n".join(tool_results)
            logger.debug("Using tool results as fallback response")
        else:
            # Ultimate fallback
            final_response = "I apologize, but I couldn't generate a proper response. Please try again."

    exec_time = time.perf_counter() - start_time
    timing = state.get("timing", {})
    timing["respond"] = exec_time

    logger.info(f"Respond node completed in {exec_time:.3f}s")
    return {
        **state,
        "final_response": final_response,
        "timing": timing,
    }


def memorize_node(state: AgentState) -> AgentState:
    """Node 5: Save interaction to long-term memory (non-blocking background)."""
    import time
    import threading

    start_time = time.perf_counter()
    messages = state.get("messages", [])
    user_input = state.get("user_input", "")
    chat_id = state.get("chat_id")
    final_response = state.get("final_response", "")
    user_id = state.get("user_id") or config.user_id

    logger.info("Memorize node: Queueing background save...")

    # Extract facts from conversation
    last_message = messages[-1] if messages else None
    ai_response: str = final_response if final_response else ""
    if not ai_response and last_message and isinstance(last_message, AIMessage):
        ai_response = _extract_text_from_content(last_message.content)
    human_input = user_input

    # Save interaction in background thread (non-blocking)
    def background_save():
        try:
            save_interaction(human_input, ai_response, user_id, chat_id)
            logger.info("Background memory save complete")
        except Exception as e:
            logger.warning(f"Background memory save failed: {e}")

    # Start background thread
    thread = threading.Thread(target=background_save, daemon=True)
    thread.start()

    exec_time = time.perf_counter() - start_time
    timing = state.get("timing", {})
    timing["memorize"] = exec_time

    logger.info(f"Memorize node completed in {exec_time:.3f}s (background)")
    return {**state, "messages": messages, "timing": timing}


# ========== Agent Creation & Execution ==========

# Thread pool for blocking operations
_executor = ThreadPoolExecutor(max_workers=10)


def run_agent(
    user_input: str, chat_id: Optional[str] = None, user_id: Optional[str] = None
) -> str:
    """
    Run agent synchronously (for testing or simple use).
    """
    logger.info(f"Running MeGPT Agent with input: {user_input}")

    # Initialize state
    state = _create_initial_state(user_input, chat_id, user_id or config.user_id)

    try:
        agent = create_agent_graph()
        result = agent.invoke(state)

        final_response = result.get("final_response", "")
        tool_count = result.get("tool_call_count", 0)

        logger.info("Agent execution complete")
        logger.info(f"Total tool calls: {tool_count}")
        logger.info(f"Final response length: {len(final_response)} chars")

        return final_response

    except MeGPTError as e:
        logger.error(f"Agent failed with MeGPT error: {e}")
        return f"I encountered an error: {str(e)}"
    except Exception as e:
        wrapped = wrap_exception(
            e,
            DomainError,
            operation="run_agent",
            user_input=user_input,
            user_id=user_id,
            chat_id=chat_id,
        )
        logger.error(f"Agent failed: {wrapped}")
        return f"I encountered an error: {str(wrapped)}"


async def run_agent_async(
    user_input: str, chat_id: Optional[str] = None, user_id: Optional[str] = None
) -> str:
    """
    Run agent asynchronously (for production FastAPI).
    """
    import time

    total_start = time.perf_counter()
    logger.info("Running MeGPT Agent Async...")

    state = _create_initial_state(user_input, chat_id, user_id or config.user_id)

    try:
        agent = create_agent_graph()
        result = await agent.ainvoke(state)

        final_response = result.get("final_response", "")
        timing = result.get("timing", {})
        total_time = time.perf_counter() - total_start

        # Log timing breakdown
        logger.info("=" * 60)
        logger.info("PERFORMANCE BREAKDOWN")
        logger.info("=" * 60)
        logger.info(f"Total execution time: {total_time:.3f}s")
        for node, node_time in timing.items():
            if node_time:
                percentage = (node_time / total_time * 100) if total_time > 0 else 0
                logger.info(
                    f"  {node.capitalize()}: {node_time:.3f}s ({percentage:.1f}%)"
                )
        logger.info("=" * 60)

        logger.info("Agent execution complete")
        return final_response

    except MeGPTError as e:
        logger.error(f"Agent failed with MeGPT error: {e}")
        return f"I encountered an error: {str(e)}"
    except Exception as e:
        wrapped = wrap_exception(
            e,
            DomainError,
            operation="run_agent_async",
            user_input=user_input,
            user_id=user_id,
            chat_id=chat_id,
        )
        logger.error(f"Agent async failed: {wrapped}")
        return f"I encountered an error: {str(wrapped)}"
