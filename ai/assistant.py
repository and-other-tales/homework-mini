"""AI Assistant module for LLM interaction using AWS Bedrock and LangChain React agent."""

import sys
import logging
import asyncio
from typing import Optional, Dict, Any

from utils.llm_client import LLMClient
from config.credentials_manager import CredentialsManager
from ai.agent import run_agent
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich import print as rich_print

# Setup logger
logger = logging.getLogger(__name__)

async def generate_ai_response(query: str, credentials_manager: Optional[CredentialsManager] = None) -> str:
    """
    Generate an AI response using the appropriate method based on the query.
    
    Args:
        query: The user query
        credentials_manager: Optional credentials manager
        
    Returns:
        str: The generated response
    """
    # Initialize LLM client
    llm_client = LLMClient(credentials_manager=credentials_manager)
    
    try:
        # Use agent-based response if the query seems to require tools
        if requires_agent_capabilities(query):
            logger.info("Query requires agent capabilities, using React agent")
            result = await run_agent(query)
            if result and result.get("success"):
                return result.get("response", "I encountered an error processing your request.")
            else:
                return "I encountered an error processing your request with agent capabilities."
        else:
            # Use standard chat completion for simple queries
            logger.info("Using standard response generation")
            return await llm_client.generate_response(query)
    except Exception as e:
        logger.error(f"Error generating response: {e}", exc_info=True)
        return f"I encountered an error: {str(e)}"


def run_full_ai_assistant():
    """
    Run a full-featured AI assistant in CLI mode, supporting all capabilities
    available in the TUI interface.
    """
    console = Console()
    console.print("\n[bold blue]🤖 AI Assistant[/bold blue] [green]CLI Mode[/green]\n")
    console.print("Type [bold]'exit'[/bold] or [bold]'quit'[/bold] to return to the main menu.\n")
    
    # Initialize credentials manager
    credentials_manager = CredentialsManager()
    aws_credentials = credentials_manager.get_aws_credentials()
    
    if not aws_credentials or not aws_credentials.get("access_key") or not aws_credentials.get("secret_key"):
        console.print("[bold red]Error:[/bold red] AWS credentials not configured.")
        console.print("Please set your AWS credentials in the Configuration menu first.")
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
    try:
        while True:
            console.print("[bold blue]You:[/bold blue] ", end="")
            user_input = input()
            
            if user_input.lower() in ['exit', 'quit', 'q']:
                console.print("\n[bold blue]AI Assistant:[/bold blue] Goodbye! Returning to main menu.")
                break
            
            # Show thinking indicator
            with console.status("[bold blue]Thinking...[/bold blue]"):
                # Generate response
                try:
                    assistant_response = loop.run_until_complete(
                        generate_ai_response(user_input, credentials_manager)
                    )
                except Exception as e:
                    logger.error(f"Error generating response: {e}", exc_info=True)
                    assistant_response = f"I encountered an error: {str(e)}"
            
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


def requires_agent_capabilities(query: str) -> bool:
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
        "find", "look up", "research", "information about", "tool", "when",
        "how", "what time", "current", "latest"
    ]
    
    query_lower = query.lower()
    return any(keyword in query_lower for keyword in agent_keywords)


if __name__ == "__main__":
    # This allows testing the assistant directly by running this file
    logging.basicConfig(level=logging.INFO)
    run_full_ai_assistant()