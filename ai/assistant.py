import sys
import logging
import asyncio
from utils.llm_client import LLMClient
from config.credentials_manager import CredentialsManager
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich import print as rich_print

# Setup logger
logger = logging.getLogger(__name__)

def run_full_ai_assistant():
    """
    Run a full-featured AI assistant in CLI mode, supporting all capabilities
    available in the web interface.
    """
    console = Console()
    console.print("\n[bold blue]🤖 AI Assistant[/bold blue] [green]CLI Mode[/green]\n")
    console.print("Type [bold]'exit'[/bold] or [bold]'quit'[/bold] to return to the main menu.\n")
    
    # Initialize LLM client
    credentials_manager = CredentialsManager()
    openai_key = credentials_manager.get_openai_key()
    
    if not openai_key:
        console.print("[bold red]Error:[/bold red] OpenAI API key not configured.")
        console.print("Please set your OpenAI API key in the Configuration menu first.")
        return
    
    llm_client = LLMClient(api_key=openai_key, credentials_manager=credentials_manager)
    
    # Check if LLM client is properly initialized
    if not llm_client.api_key:
        console.print("[bold red]Error:[/bold red] Failed to initialize LLM client.")
        return
    
    # Show capabilities info
    console.print(Panel(
        "[bold]Supported capabilities:[/bold]\n"
        "• Web search and browsing\n"
        "• Website crawling and data extraction\n" 
        "• GitHub repository analysis\n"
        "• Knowledge graph creation and querying\n"
        "• Dataset management",
        title="AI Assistant Capabilities",
        border_style="blue"
    ))
    
    # Create a new event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Start conversation
    conversation_history = []
    conversation_history.append({
        "role": "system",
        "content": "You are an AI assistant for the Homework project. Your primary focus is helping users gather "
                 "and organize information through web searching, web crawling, and dataset creation."
    })
    
    try:
        while True:
            console.print("[bold blue]You:[/bold blue] ", end="")
            user_input = input()
            
            if user_input.lower() in ['exit', 'quit', 'q']:
                console.print("\n[bold blue]AI Assistant:[/bold blue] Goodbye! Returning to main menu.")
                break
            
            # Show thinking indicator
            with console.status("[bold blue]Thinking...[/bold blue]"):
                # Add user message to conversation history
                conversation_history.append({"role": "user", "content": user_input})
                
                # Generate response
                try:
                    # Use agent-based response if the query seems to require tools
                    if requires_agent_capabilities(user_input):
                        response = loop.run_until_complete(llm_client.run_agent(user_input))
                        if response and response.get("success") and response.get("data"):
                            assistant_response = response["data"].get("response", "I encountered an error processing your request.")
                        else:
                            assistant_response = "I encountered an error processing your request."
                    else:
                        # Use standard chat completion for simple queries
                        assistant_response = loop.run_until_complete(llm_client.generate_response(user_input))
                except Exception as e:
                    logger.error(f"Error generating response: {e}", exc_info=True)
                    assistant_response = f"I encountered an error: {str(e)}"
                
                # Add assistant response to conversation history
                conversation_history.append({"role": "assistant", "content": assistant_response})
            
            # Display the response with markdown formatting
            console.print("\n[bold blue]AI Assistant:[/bold blue]")
            console.print(Markdown(assistant_response))
            console.print()
            
    except KeyboardInterrupt:
        console.print("\n\n[bold blue]AI Assistant:[/bold blue] Conversation interrupted. Returning to main menu.")
    except Exception as e:
        logger.error(f"Error in AI assistant: {e}", exc_info=True)
        console.print(f"\n[bold red]Error:[/bold red] {str(e)}")
    finally:
        # Close the event loop
        loop.close()

def requires_agent_capabilities(query):
    """
    Determine if a query requires agent capabilities by looking for keywords.
    
    Args:
        query: The user's query
        
    Returns:
        bool: True if the query likely requires agent capabilities
    """
    agent_keywords = [
        "crawl", "scrape", "extract", "website", "search", "github", 
        "repository", "knowledge graph", "graph", "dataset", "datasets",
        "find", "look up", "research", "information about"
    ]
    
    query_lower = query.lower()
    return any(keyword in query_lower for keyword in agent_keywords)

if __name__ == "__main__":
    # This allows testing the assistant directly by running this file
    logging.basicConfig(level=logging.INFO)
    run_full_ai_assistant()
