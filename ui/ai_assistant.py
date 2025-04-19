"""TUI AI Assistant implementation using latest Textual features."""

import sys
import logging
import asyncio
from typing import Optional

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import (
    Header,
    Footer,
    Button,
    Input,
    Label,
    Static,
    Markdown,
    LoadingIndicator,
)
from textual.reactive import reactive
from textual import work

from utils.llm_client import LLMClient
from ai.assistant import generate_ai_response
from ai.agent import run_agent
from config.credentials_manager import CredentialsManager

# Setup logger
logger = logging.getLogger(__name__)

class ResponseMessage(Static):
    """A message in the chat with role and content."""
    
    def __init__(self, role: str, content: str) -> None:
        """Initialize a message with role and content."""
        super().__init__()
        self.role = role
        self.content = content
        
    def compose(self) -> ComposeResult:
        """Render the message."""
        if self.role == "user":
            yield Static(f"[bold blue]You:[/bold blue]", classes="message-heading")
        else:
            yield Static(f"[bold green]AI Assistant:[/bold green]", classes="message-heading")
        
        # Render content as markdown for AI responses, plain text for user
        if self.role == "assistant":
            yield Markdown(self.content, classes="message-content")
        else:
            yield Static(self.content, classes="message-content")


class AIAssistantApp(App):
    """AI Assistant TUI application."""
    
    CSS_PATH = "tui_app.css"
    TITLE = "AI Assistant"
    
    # Reactive variables
    is_processing = reactive(False)
    
    def compose(self) -> ComposeResult:
        """Compose the UI."""
        yield Header()
        yield Footer()
        
        yield Container(
            Vertical(
                Label("AI Assistant", classes="title"),
                ScrollableContainer(
                    id="message_container",
                    classes="messages"
                ),
                Horizontal(
                    Input(placeholder="Enter your query here...", id="query_input"),
                    Button("Submit", id="submit_button", variant="primary"),
                    id="input_area"
                ),
                LoadingIndicator(id="loading", classes="hide"),
                id="main_container"
            )
        )
        
        # Add initial welcome message
        welcome_message = (
            "Welcome to the AI Assistant! I can help you with research, information gathering, "
            "and knowledge management tasks. You can ask me to search for information, analyze "
            "GitHub repositories, create knowledge graphs, and more."
        )
        self.add_message("assistant", welcome_message)
    
    def add_message(self, role: str, content: str) -> None:
        """Add a message to the conversation."""
        message = ResponseMessage(role, content)
        self.query_one("#message_container").mount(message)
        self.query_one("#message_container").scroll_end(animate=True)
    
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submission."""
        if event.input.id == "query_input" and not self.is_processing:
            self.submit_query(event.input.value)
            event.input.value = ""
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "submit_button" and not self.is_processing:
            query = self.query_one("#query_input").value
            if query.strip():
                self.submit_query(query)
                self.query_one("#query_input").value = ""
    
    def submit_query(self, query: str) -> None:
        """Submit a query to the AI assistant."""
        if not query.strip():
            return
        
        # Add user message to the conversation
        self.add_message("user", query)
        
        # Show loading indicator and disable input
        self.is_processing = True
        self.query_one("#loading").remove_class("hide")
        
        # Generate response in background
        self.generate_response_async(query)
    
    @work
    async def generate_response_async(self, query: str) -> None:
        """Generate a response in the background."""
        try:
            # Initialize credentials manager
            credentials_manager = CredentialsManager()
            
            # Generate response
            response = await generate_ai_response(query, credentials_manager)
            
            # Add response to the conversation
            self.add_message("assistant", response)
            
        except Exception as e:
            logger.error(f"Error generating response: {e}", exc_info=True)
            self.add_message("assistant", f"Error: {str(e)}")
            
        finally:
            # Hide loading indicator and enable input
            self.is_processing = False
            self.query_one("#loading").add_class("hide")
            self.query_one("#query_input").focus()


def ai_assistant():
    """
    Run a full-featured AI assistant in TUI mode.
    """
    app = AIAssistantApp()
    app.run()


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
    ai_assistant()