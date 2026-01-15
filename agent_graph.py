"""
Agent Graph - LangGraph ReAct loop orchestration.
Implements: Recall → Reason → Tool → Response → Memorize
"""
from typing import TypedDict, Annotated, Literal
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from utils.llm_factory import get_llm
from tools.memory_tool import retrieve_context, save_interaction
from tools.web_search import web_search
from config import config


# Define the agent state
class AgentState(TypedDict):
    """State passed between nodes in the graph."""
    messages: list[BaseMessage]
    context: str
    user_input: str
    final_response: str


# System prompt with memory context placeholder
SYSTEM_PROMPT = """You are a helpful, intelligent AI assistant with access to long-term memory and web search capabilities.

{memory_context}

Guidelines:
- Be conversational and helpful
- Use web search when you need current information (news, weather, recent events)
- Remember important facts about the user for future conversations
- Format code blocks with proper syntax highlighting using ```language
- Be concise but thorough

Available tools:
- web_search: Search the web for current information"""


def create_agent_graph():
    """Create and compile the LangGraph agent."""
    
    # Get LLM with tools bound
    llm = get_llm(streaming=True)
    tools = [web_search]
    llm_with_tools = llm.bind_tools(tools)
    
    # Tool node for executing tools
    tool_node = ToolNode(tools)
    
    def recall_node(state: AgentState) -> AgentState:
        """Node 1: Recall - Fetch relevant context from memory."""
        user_input = state.get("user_input", "")
        
        # Get context from memory
        context = retrieve_context(user_input)
        
        return {
            **state,
            "context": context
        }
    
    def reason_node(state: AgentState) -> AgentState:
        """Node 2: Reason - LLM decides response or tool use."""
        context = state.get("context", "")
        messages = state.get("messages", [])
        
        # Build system message with memory context
        memory_section = context if context else "No prior memories about this user."
        system_content = SYSTEM_PROMPT.format(memory_context=memory_section)
        
        # Prepare messages for LLM
        full_messages = [SystemMessage(content=system_content)] + messages
        
        # Get LLM response
        response = llm_with_tools.invoke(full_messages)
        
        return {
            **state,
            "messages": messages + [response]
        }
    
    def should_continue(state: AgentState) -> Literal["tools", "respond"]:
        """Edge condition: Check if we need to call tools."""
        messages = state.get("messages", [])
        if not messages:
            return "respond"
        
        last_message = messages[-1]
        
        # Check if the last message has tool calls
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return "respond"
    
    def respond_node(state: AgentState) -> AgentState:
        """Node 4: Generate final response."""
        messages = state.get("messages", [])
        
        if messages:
            last_message = messages[-1]
            if isinstance(last_message, AIMessage):
                return {
                    **state,
                    "final_response": last_message.content
                }
        
        return {
            **state,
            "final_response": "I apologize, I couldn't generate a response."
        }
    
    def memorize_node(state: AgentState) -> AgentState:
        """Node 5: Save interaction to memory (async in production)."""
        user_input = state.get("user_input", "")
        final_response = state.get("final_response", "")
        
        if user_input and final_response:
            try:
                save_interaction(user_input, final_response)
            except Exception as e:
                print(f"⚠ Failed to save to memory: {e}")
        
        return state
    
    # Build the graph
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("recall", recall_node)
    workflow.add_node("reason", reason_node)
    workflow.add_node("tools", tool_node)
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


def run_agent(user_input: str, history: list[BaseMessage] | None = None) -> str:
    """
    Run the agent with a user input and optional conversation history.
    
    Args:
        user_input: The user's message
        history: Optional list of previous messages
    
    Returns:
        The agent's response
    """
    messages = history or []
    messages.append(HumanMessage(content=user_input))
    
    # Run the graph
    result = agent.invoke({
        "messages": messages,
        "context": "",
        "user_input": user_input,
        "final_response": ""
    })
    
    return result.get("final_response", "I couldn't generate a response.")


async def run_agent_stream(user_input: str, history: list[BaseMessage] | None = None):
    """
    Stream the agent response token by token.
    
    Args:
        user_input: The user's message
        history: Optional list of previous messages
    
    Yields:
        Text chunks as they are generated
    """
    messages = history or []
    messages.append(HumanMessage(content=user_input))
    
    # Get context first
    context = retrieve_context(user_input)
    memory_section = context if context else "No prior memories about this user."
    system_content = SYSTEM_PROMPT.format(memory_context=memory_section)
    
    full_messages = [SystemMessage(content=system_content)] + messages
    
    llm = get_llm(streaming=True)
    tools = [web_search]
    llm_with_tools = llm.bind_tools(tools)
    
    full_response = ""
    
    async for chunk in llm_with_tools.astream(full_messages):
        if hasattr(chunk, "content") and chunk.content:
            full_response += chunk.content
            yield chunk.content
    
    # Save to memory after streaming completes
    if full_response:
        try:
            save_interaction(user_input, full_response)
        except Exception:
            pass
