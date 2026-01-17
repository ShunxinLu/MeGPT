"""
Agent Graph - LangGraph ReAct loop orchestration with Async support.
Brain Transplant: Centralized 3-Tier Context with proper tool execution.
Implements: Recall → Reason → Tool → Response → Memorize
"""
import asyncio
from typing import TypedDict, Literal, Optional
from concurrent.futures import ThreadPoolExecutor
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage, ToolMessage

from utils.llm_factory import get_llm
from tools.memory_tool import retrieve_context, save_interaction
from tools.web_search import web_search
from database import get_summary, get_recent_messages_text
from config import config


# Thread pool for blocking operations
_executor = ThreadPoolExecutor(max_workers=10)


# ========== Agent State ==========

class AgentState(TypedDict):
    """State passed between nodes in the graph."""
    messages: list[BaseMessage]
    user_input: str
    chat_id: Optional[str]
    user_id: Optional[str]
    context: dict  # {facts, summary, recent_history}
    final_response: str
    tool_call_count: int  # Track tool iterations to prevent infinite loops


# ========== System Prompt (3-Tier) ==========

SYSTEM_PROMPT = """You are MeGPT, a helpful AI assistant with persistent long-term memory and web search capabilities.

[LONG-TERM MEMORY - Facts about the user]
{memory_facts}

[CONVERSATION SUMMARY]
{conversation_summary}

Important facts about yourself:
- You DO have long-term memory that persists across conversations
- You remember important facts about the user
- You can learn new information and recall it later
- You CAN and SHOULD search the web when asked about current events, prices, news, weather, etc.

Guidelines:
- Be conversational and helpful
- When asked about your memory, confirm that you DO remember things
- Use the web_search tool for ANY question about current/real-time information
- Format code blocks with proper syntax highlighting using ```language
- Be concise but thorough

DO NOT HALLUCINATE DATA. If asked about current prices, news, etc., USE THE WEB SEARCH TOOL."""


def create_agent_graph():
    """Create and compile the LangGraph agent."""
    
    # Get LLM with tools bound
    llm = get_llm(streaming=False)
    tools = [web_search]
    llm_with_tools = llm.bind_tools(tools)
    
    # Tool node for executing tools
    tool_node = ToolNode(tools)
    
    def recall_node(state: AgentState) -> AgentState:
        """Node 1: Recall - Fetch 3-Tier Context."""
        user_input = state.get("user_input", "")
        chat_id = state.get("chat_id")
        user_id = state.get("user_id") or config.user_id
        
        print("Brain Recall node: Fetching 3-tier context...")
        
        # Tier 2: Vector Facts from Qdrant
        facts = ""
        try:
            facts = retrieve_context(user_input, user_id)
            print(f"  Tier 2: {len(facts)} chars of facts")
        except Exception as e:
            print(f"  Tier 2: Failed - {e}")
        
        # Tier 3: Rolling Summary
        summary = ""
        if chat_id:
            try:
                summary = get_summary(chat_id)
                print(f"  Tier 3: {len(summary)} chars of summary")
            except Exception as e:
                print(f"  Tier 3: Failed - {e}")
        
        # Tier 1: Recent Messages
        recent_history = ""
        if chat_id:
            try:
                recent_history = get_recent_messages_text(chat_id, limit=10)
                print(f"  Tier 1: {len(recent_history)} chars of history")
            except Exception as e:
                print(f"  Tier 1: Failed - {e}")
        
        return {
            **state,
            "context": {
                "facts": facts,
                "summary": summary,
                "recent_history": recent_history,
            }
        }
    
    def reason_node(state: AgentState) -> AgentState:
        """Node 2: Reason - LLM decides response or tool use."""
        context = state.get("context", {})
        messages = state.get("messages", [])
        
        # Build system message with 3-tier context
        facts_section = context.get("facts", "") or "No prior memories about this user yet."
        summary_section = context.get("summary", "") or "No summary yet."
        
        system_content = SYSTEM_PROMPT.format(
            memory_facts=facts_section,
            conversation_summary=summary_section
        )
        
        # Prepare messages for LLM
        full_messages = [SystemMessage(content=system_content)] + messages
        
        print(f"Thought Reason node: Invoking LLM with {len(messages)} messages...")
        
        # Get LLM response (may include tool_calls)
        response = llm_with_tools.invoke(full_messages)
        
        # Debug: Check for tool calls
        if hasattr(response, "tool_calls") and response.tool_calls:
            print(f"Tool calls detected: {[tc.get('name') for tc in response.tool_calls]}")
        else:
            print("Text response (no tools)")
        
        return {
            **state,
            "messages": messages + [response]
        }
    
    def should_continue(state: AgentState) -> Literal["tools", "respond"]:
        """Edge condition: Check if we need to call tools."""
        messages = state.get("messages", [])
        tool_count = state.get("tool_call_count", 0)
        MAX_TOOL_CALLS = 3  # Limit tool iterations
        
        if not messages:
            return "respond"
        
        # Prevent infinite tool loops
        if tool_count >= MAX_TOOL_CALLS:
            print(f"Warning: Max tool calls ({MAX_TOOL_CALLS}) reached, forcing response...")
            return "respond"
        
        last_message = messages[-1]
        
        # Check if the last message has tool calls
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return "respond"
    
    def tools_wrapper_node(state: AgentState) -> AgentState:
        """Wrapper around ToolNode that properly accumulates messages."""
        tool_result = tool_node.invoke(state)
        new_messages = tool_result.get("messages", [])
        
        # CRITICAL: Append new messages to existing, don't overwrite!
        all_messages = state.get("messages", []) + new_messages
        
        print(f"   Tool executed, added {len(new_messages)} messages, total: {len(all_messages)}")
        
        return {
            **state,
            "messages": all_messages,
            "tool_call_count": state.get("tool_call_count", 0) + 1
        }
    
    def respond_node(state: AgentState) -> AgentState:
        """Node 4: Synthesize final response with Context Hygiene."""
        messages = state.get("messages", [])
        user_input = state.get("user_input", "")
        
        print(f"[RESPOND] Processing {len(messages)} messages")
        
        if messages:
            last_message = messages[-1]
            
            # If we have an AIMessage with content, use it directly
            if isinstance(last_message, AIMessage) and last_message.content:
                print(f"   Using last AIMessage content ({len(last_message.content)} chars)")
                return {
                    **state,
                    "final_response": last_message.content
                }
            
            # Collect tool results for synthesis
            tool_results = []
            for msg in messages:
                if isinstance(msg, ToolMessage):
                    tool_results.append(msg.content)
            
            print(f"   Found {len(tool_results)} tool results")
            
            if tool_results:
                all_results = "\n\n---\n\n".join(tool_results)
                
                # CONTEXT HYGIENE: Create a clean history for the LLM
                # Keep: User messages, AI text responses (summaries)
                # Remove: SystemMessages, ToolMessages, empty AIMessages
                clean_history = []
                for m in messages:
                    if isinstance(m, HumanMessage):
                        clean_history.append(m)
                    elif isinstance(m, AIMessage) and m.content:
                        clean_history.append(m)
                
                # Build synthesis prompt
                synthesis_prompt = f"""You are MeGPT. Answer the user based on the Search Results.

CONTEXT:
User asked: "{user_input}"

SEARCH RESULTS:
{all_results}

INSTRUCTIONS:
1. Synthesize a conversational answer using ONLY the search results.
2. Use EXACT numbers, prices, and facts - do NOT make up data.
3. Cite sources (SOURCE 1, SOURCE 2, etc.) when referencing information.
4. If results don't contain the answer, admit it honestly.
5. Be concise."""

                synthesis_messages = [
                    SystemMessage(content="You are a helpful AI assistant."),
                    *clean_history,
                    HumanMessage(content=synthesis_prompt)
                ]
                
                print(f"Synthesizing with {len(clean_history)} clean history messages...")
                
                llm = get_llm()
                response = llm.invoke(synthesis_messages)
                
                print(f"   Synthesis complete: {len(response.content)} chars")
                return {
                    **state,
                    "final_response": response.content
                }
        
        return {
            **state,
            "final_response": "I couldn't find any information to help with that."
        }
    
    def memorize_node(state: AgentState) -> AgentState:
        """Node 5: Save interaction to memory."""
        user_input = state.get("user_input", "")
        final_response = state.get("final_response", "")
        user_id = state.get("user_id") or config.user_id
        chat_id = state.get("chat_id")
        
        if user_input and final_response:
            try:
                save_interaction(user_input, final_response, user_id, chat_id)
                print("Saved interaction to memory")
            except Exception as e:
                print(f"Warning: Failed to save to memory: {e}")
        
        return state
    
    # Build the graph
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("recall", recall_node)
    workflow.add_node("reason", reason_node)
    workflow.add_node("tools", tools_wrapper_node)
    workflow.add_node("respond", respond_node)
    workflow.add_node("memorize", memorize_node)
    
    # Set entry point
    workflow.set_entry_point("recall")
    
    # Add edges
    workflow.add_edge("recall", "reason")
    workflow.add_conditional_edges(
        "reason",
        should_continue,
        {
            "tools": "tools",
            "respond": "respond"
        }
    )
    workflow.add_edge("tools", "reason")  # Loop back after tool execution
    workflow.add_edge("respond", "memorize")
    workflow.add_edge("memorize", END)
    
    # Compile the graph
    return workflow.compile()


# Create the agent instance
agent = create_agent_graph()


def run_agent(
    user_input: str, 
    history: list[BaseMessage] | None = None,
    chat_id: str | None = None,
    user_id: str | None = None,
) -> str:
    """
    Run the agent synchronously (for testing).
    """
    messages = history or []
    messages.append(HumanMessage(content=user_input))
    
    result = agent.invoke({
        "messages": messages,
        "user_input": user_input,
        "chat_id": chat_id,
        "user_id": user_id or config.user_id,
        "context": {},
        "final_response": "",
        "tool_call_count": 0
    })
    
    return result.get("final_response", "I couldn't generate a response.")


async def run_agent_async(
    user_input: str, 
    history: list[BaseMessage] | None = None,
    chat_id: str | None = None,
    user_id: str | None = None,
) -> str:
    """
    Run the agent asynchronously (for FastAPI).
    Uses ainvoke for non-blocking execution.
    """
    messages = history or []
    messages.append(HumanMessage(content=user_input))
    
    result = await agent.ainvoke({
        "messages": messages,
        "user_input": user_input,
        "chat_id": chat_id,
        "user_id": user_id or config.user_id,
        "context": {},
        "final_response": "",
        "tool_call_count": 0
    })
    
    return result.get("final_response", "I couldn't generate a response.")
