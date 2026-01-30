"""
MeGPT Agent Graph - Enhanced with Domain Integration
Unified architecture: LangGraph ReAct loop with 4-tier memory + domain-specific tools
Integrates: Chat, Email, Calendar
"""

import asyncio
import logging
from typing import TypedDict, List, Literal, Optional
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

from config import config
from utils.llm_factory import get_llm
from tools.memory_tool import retrieve_context, save_interaction, MEMORY_TOOLS
from tools.web_search import web_search
from database import get_adaptive_context, get_summary

# Import domain-specific tools
from tools.email_tools import EMAIL_TOOLS
from tools.calendar_tools import CALENDAR_TOOLS
from tools.vision_tools import VISION_TOOLS

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ========== System Prompt ==========
SYSTEM_PROMPT = """You are MeGPT, a helpful AI assistant with persistent long-term memory and web search capabilities.

[LONG-TERM MEMORY - Facts about the user]
{memory_facts}

[CONVERSATION SUMMARY]
{conversation_summary}

Important facts about yourself:
- You DO have long-term memory that persists across conversations
- You remember important facts about user
- You can learn new information and recall it later
- You CAN and SHOULD search the web when asked about current/real-time information
- Format code blocks with proper syntax highlighting using ```language

Guidelines:
- Be conversational and helpful
- When asked about your memory, confirm that you DO remember things
- Use web_search tool for ANY question about current/real-time information
- Format code blocks with proper syntax highlighting using ```language
- Be concise but thorough

DO NOT HALLUCINATE DATA. If asked about current prices, news, etc., USE THE WEB SEARCH TOOL.
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


# ========== Tool Registration ==========
# All tools are registered here for easy access
ALL_TOOLS = [
    *EMAIL_TOOLS,
    *CALENDAR_TOOLS,
    *VISION_TOOLS,
    *MEMORY_TOOLS,
    web_search,
]


# ========== Helper Functions ==========

def _get_llm_with_tools(streaming: bool = False):
    """Get LLM with tools bound - extracted to avoid duplication."""
    llm = get_llm(streaming=streaming)
    return llm.bind_tools(ALL_TOOLS)


def _create_initial_state(user_input: str, chat_id: Optional[str], user_id: str) -> AgentState:
    """Create initial state for agent execution - extracted to avoid duplication."""
    return {
        "messages": [],
        "user_input": user_input,
        "chat_id": chat_id,
        "user_id": user_id or config.user_id,
        "context": {},
        "final_response": "",
        "tool_call_count": 0,
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
    workflow.add_node("respond", respond_node)
    workflow.add_node("memorize", memorize_node)
    
    # Set conditional edges
    workflow.add_conditional_edges(
        "reason",
        should_continue,
        {"tools": "tools", "respond": "respond"}
    )
    workflow.add_edge("tools", "reason")
    # Removed incorrect duplicate edge from reason to respond
    workflow.add_edge("respond", "memorize")
    workflow.add_edge("recall", "reason")
    
    # Set entry point
    workflow.set_entry_point("recall")
    
    # Compile graph
    return workflow.compile()


# ========== Node Functions ==========

def recall_node(state: AgentState) -> AgentState:
    """Node 1: Recall - Fetch adaptive 3-Tier + Tier 4 context based on query intent."""
    user_input = state.get("user_input", "")
    chat_id = state.get("chat_id")
    user_id = state.get("user_id") or config.user_id
    
    logger.info("Recall node: Fetching adaptive context...")
    
    try:
        # Use enhanced context with domain contexts
        adaptive_result = get_adaptive_context(user_input, chat_id, user_id)
        context = adaptive_result.get("context", {})
        
        return {**state, "context": context}
    except Exception as e:
        logger.warning(f"Context fetch failed: {e}")
        # Return empty context on failure
        return {**state, "context": {
            "facts": "No prior facts available.",
            "summary": "No summary available.",
            "recent": "",
            "domains": {},
        }}


def reason_node(state: AgentState) -> AgentState:
    """Node 2: Reason - LLM decides response or tool use."""
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

    # System prompt with all contexts
    system_content = SYSTEM_PROMPT.format(
        memory_facts=facts,
        conversation_summary=summary,
    )

    # Append domain contexts to system prompt
    if emails:
        system_content += f"\n\n[RECENT EMAILS]\n{emails}"
    if calendar:
        system_content += f"\n\n[UPCOMING CALENDAR]\n{calendar}"
    
    # Build message sequence:
    # 1. System: Core instructions + All contexts
    full_messages = [SystemMessage(content=system_content)]
    
    # 2. Recent history dump (bridges gap between summary and current input)
    if recent_history_str:
        history_refresh = f"""
RECENT CONVERSATION HISTORY (from database):
{recent_history_str}
"""
        full_messages.append(SystemMessage(content=history_refresh))
    
    # 3. Current user input
    full_messages.append(HumanMessage(content=user_input))

    # Get LLM with tools bound
    logger.debug("Calling LLM with comprehensive context...")
    llm_with_tools = _get_llm_with_tools(streaming=False)
    response = llm_with_tools.invoke(full_messages)
    
    logger.debug(f"LLM response received: {len(response.content)} chars")
    
    # Check for tool calls
    if hasattr(response, "tool_calls") and response.tool_calls:
        logger.debug(f"Tool calls detected: {[tc.get('name') for tc in response.tool_calls]}")
    
    new_messages = messages + [response]
    
    # Increment tool call count
    tool_count = state.get("tool_call_count", 0) + 1
    
    return {**state, "messages": new_messages, "tool_call_count": tool_count}


def should_continue(state: AgentState) -> Literal["tools", "respond"]:
    """Edge condition: Check if we need to call more tools."""
    messages = state.get("messages", [])
    
    logger.debug("Checking if more tools needed...")
    
    # Check last message for tool calls
    if not messages:
        logger.debug("No messages yet, responding...")
        return "respond"
    
    last_message = messages[-1]
    
    # Check for tool calls in last message
    if not hasattr(last_message, "tool_calls"):
        logger.debug("Last message has no tool calls, responding...")
        return "respond"
    
    # Check if last message requested more information
    last_message_content = last_message.content if hasattr(last_message, "content") else ""
    
    # Simple heuristic: if last message asks questions or seems incomplete
    # Could be enhanced with LLM-based classification
    
    if last_message_content:
        logger.debug(f"Last message asks: {last_message_content[:50]}...")
        return "respond"
    
    return "tools"





def respond_node(state: AgentState) -> AgentState:
    """Node 4: Synthesize final response with context hygiene."""
    messages = state.get("messages", [])
    final_response = state.get("final_response", "")
    context = state.get("context", {})
    
    # Extract domain contexts for synthesis token estimation
    domains = context.get("domains", {})
    chat_history = ""  # Placeholder for estimation
    
    logger.info("Respond node: Synthesizing final response...")
    
    if not final_response:
        logger.debug("No response found, checking earlier messages...")
        
        # Find last non-tool message with content
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                final_response = msg.content
                break
            else:
                logger.debug("No AIMessage with content found!")
        
        if not final_response:
            return {**state, "messages": messages}
    
    # Context hygiene: Create clean history for synthesis
    clean_messages = []
    
    for msg in messages:
        if isinstance(msg, HumanMessage):
            clean_messages.append(msg)
        elif isinstance(msg, AIMessage):
            if msg.content:
                clean_messages.append(msg)
        # Remove SystemMessages and empty AIMessages
        # Keep ToolMessages with content
        # Remove duplicate consecutive ToolMessages (keep last one)
    
    # Build synthesis prompt
    synthesis_prompt = """You are MeGPT, a helpful AI assistant with persistent long-term memory and web search capabilities.

[CONTEXT]
Previous conversation:
{chat_history}

[LONG-TERM MEMORY]
{facts}

[DOMAIN CONTEXTS]
{domains}

[NEW INPUT]
User: {new_input}

[INSTRUCTIONS]
Based on the conversation and context above, provide a helpful response.
Use domain tools if needed (email, calendar, finance).
"""

    # Count tokens roughly
    chat_history_str = "\n".join([m.content for m in clean_messages])
    token_count = len(synthesis_prompt) + len(chat_history_str) + len(str(domains))
    logger.debug(f"Synthesis context: ~{token_count} tokens")
    
    # Get LLM synthesis
    llm = get_llm(streaming=False)
    synthesis_response = llm.invoke([HumanMessage(content=synthesis_prompt)])
    
    synthesis_content = synthesis_response.content
    logger.debug(f"Synthesis returned: {len(synthesis_content)} chars")
    
    new_messages = messages + [AIMessage(content=synthesis_content)]
    
    return {**state, "messages": new_messages, "final_response": synthesis_content}


def memorize_node(state: AgentState) -> AgentState:
    """Node 5: Save interaction to long-term memory."""
    messages = state.get("messages", [])
    user_input = state.get("user_input", "")
    chat_id = state.get("chat_id")
    final_response = state.get("final_response", "")
    user_id = state.get("user_id") or config.user_id
    
    logger.info("Memorize node: Saving to memory...")
    
    # Extract facts from conversation
    last_message = messages[-1]
    ai_response = final_response if final_response else last_message.content if isinstance(last_message, AIMessage) else ""
    human_input = user_input
    
    # Save interaction (includes LLM extraction)
    save_interaction(human_input, ai_response, user_id, chat_id)
    
    logger.info("Saved to memory")
    return {**state, "messages": messages}


# ========== Agent Creation & Execution ==========

# Thread pool for blocking operations
_executor = ThreadPoolExecutor(max_workers=10)


def run_agent(user_input: str, chat_id: Optional[str] = None, user_id: str = None) -> str:
    """
    Run agent synchronously (for testing or simple use).
    """
    logger.info(f"Running MeGPT Agent with input: {user_input}")

    # Initialize state
    state = _create_initial_state(user_input, chat_id, user_id or config.user_id)

    try:
        agent = create_agent_graph()
        result = agent.invoke({
            "user_input": user_input,
            "chat_id": chat_id,
            "user_id": user_id or config.user_id,
            "context": state.get("context", {}),
        })

        final_response = result.get("final_response", "")
        tool_count = result.get("tool_call_count", 0)

        logger.info("Agent execution complete")
        logger.info(f"Total tool calls: {tool_count}")
        logger.info(f"Final response length: {len(final_response)} chars")

        return final_response

    except Exception as e:
        logger.error(f"Agent failed: {e}")
        return f"I encountered an error: {str(e)}"


async def run_agent_async(user_input: str, chat_id: Optional[str] = None, user_id: str = None) -> str:
    """
    Run agent asynchronously (for production FastAPI).
    """
    logger.info("Running MeGPT Agent Async...")

    state = _create_initial_state(user_input, chat_id, user_id or config.user_id)

    try:
        agent = create_agent_graph()
        result = await agent.ainvoke({
            "user_input": user_input,
            "chat_id": chat_id,
            "user_id": user_id or config.user_id,
            "context": state.get("context", {}),
        })

        final_response = result.get("final_response", "")

        logger.info("Agent execution complete")
        return final_response

    except Exception as e:
        logger.error(f"Agent async failed: {e}")
        return f"I encountered an error: {str(e)}"
