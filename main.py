"""
Main CLI Entry Point - Interactive REPL for the Local Memory Agent.
"""
import sys
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage

from config import config
from agent_graph import run_agent

console = Console()


def print_welcome():
    """Print welcome banner."""
    console.print(Panel.fit(
        "[bold cyan]🧠 Local Memory Agent[/bold cyan]\n"
        f"[dim]Model: {config.llm_model_name}[/dim]\n"
        f"[dim]Memory: Qdrant @ {config.qdrant_host}:{config.qdrant_port}[/dim]\n"
        "[dim]Type /quit to exit, /clear to reset conversation[/dim]",
        border_style="cyan"
    ))


def main():
    """Main CLI loop."""
    config.validate()
    print_welcome()
    
    history: list[BaseMessage] = []
    
    while True:
        try:
            # Get user input
            user_input = Prompt.ask("\n[bold green]You[/bold green]")
            
            if not user_input.strip():
                continue
            
            # Handle commands
            if user_input.strip().lower() == "/quit":
                console.print("[dim]Goodbye! 👋[/dim]")
                break
            
            if user_input.strip().lower() == "/clear":
                history = []
                console.print("[dim]Conversation cleared.[/dim]")
                continue
            
            if user_input.strip().lower() == "/history":
                if not history:
                    console.print("[dim]No conversation history.[/dim]")
                else:
                    for msg in history:
                        role = "You" if isinstance(msg, HumanMessage) else "AI"
                        console.print(f"[dim]{role}: {msg.content[:100]}...[/dim]")
                continue
            
            # Run the agent
            console.print("\n[bold blue]Assistant[/bold blue]", end=" ")
            
            with console.status("[dim]Thinking...[/dim]", spinner="dots"):
                response = run_agent(user_input, history.copy())
            
            # Display response as markdown
            console.print()
            console.print(Markdown(response))
            
            # Update history
            history.append(HumanMessage(content=user_input))
            history.append(AIMessage(content=response))
            
        except KeyboardInterrupt:
            console.print("\n[dim]Interrupted. Type /quit to exit.[/dim]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


if __name__ == "__main__":
    main()
