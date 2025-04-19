import sys
import logging
import asyncio
from utils.llm_client import LLMClient
from config.credentials_manager import CredentialsManager
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import (
    Header,
    Footer,
    Button,
    TextInput,
    Label,
    Panel,
    Markdown,
    ListView,
)

# Setup logger
logger = logging.getLogger(__name__)

class AIAssistantApp(App):
    CSS_PATH = "tui_app.css"

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()
        yield Container(
            Horizontal(
                Vertical(
                    Label("AI Assistant"),
                    TextInput(placeholder="Enter your query here..."),
                    Button("Submit", id="submit_button"),
                    id="left_panel",
                ),
                Vertical(
                    Panel(Markdown("## AI Assistant Responses")),
                    ListView(id="response_list"),
                    id="right_panel",
                ),
                id="main_container",
            )
        )

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "submit_button":
            query = self.query_one(TextInput).value
            response = await self.get_ai_response(query)
            self.query_one(ListView).append(Label(response))

    async def get_ai_response(self, query: str) -> str:
        # Placeholder for AI response logic
        return f"Response to: {query}"

def ai_assistant():
    """
    Run a full-featured AI assistant in TUI mode, supporting all capabilities
    available in the web interface.
    """
    app = AIAssistantApp()
    app.run()

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
    ai_assistant()
