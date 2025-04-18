import logging
import json
import uuid
import asyncio
import os
from typing import Dict, List, Any, Optional
from fastapi import WebSocket
from datetime import datetime

from config.credentials_manager import CredentialsManager
from utils.llm_client import LLMClient
from knowledge_graph.graph_store import GraphStore
from github.client import GitHubClient
from utils.task_tracker import TaskTracker

logger = logging.getLogger(__name__)

class ChatHandler:
    """Handler for WebSocket chat connections."""
    
    def __init__(self, credentials_manager: CredentialsManager):
        """Initialize the chat handler."""
        self.active_connections: Dict[str, WebSocket] = {}
        self.credentials_manager = credentials_manager
        self.llm_client = None
        self.github_client = None
        self.graph_store = None
        self.task_tracker = TaskTracker()
        
        # Try to initialize clients
        self._initialize_clients()
    
    def _initialize_clients(self):
        """Initialize API clients based on available credentials."""
        # Initialize LLM client if OpenAI API key is available
        openai_key = self.credentials_manager.get_openai_key()
        if openai_key:
            try:
                self.llm_client = LLMClient(api_key=openai_key)
                logger.info("LLM client initialized with API key")
            except Exception as e:
                logger.error(f"Failed to initialize LLM client: {e}")
        else:
            # Check environment directly as a fallback
            openai_key_env = os.environ.get("OPENAI_API_KEY")
            if openai_key_env:
                try:
                    self.llm_client = LLMClient(api_key=openai_key_env)
                    logger.info("LLM client initialized with API key from environment")
                except Exception as e:
                    logger.error(f"Failed to initialize LLM client with env var: {e}")
            else:
                logger.warning("OpenAI API key not found, LLM features will be limited")
        
        # Initialize GitHub client if credentials are available
        try:
            self.github_client = GitHubClient()
            self.github_client.verify_credentials()
            logger.info("GitHub client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize GitHub client: {e}")
            self.github_client = None
        
        # Initialize Neo4j connection if credentials are available
        try:
            self.graph_store = GraphStore()
            if self.graph_store.test_connection():
                logger.info("Neo4j graph store initialized")
            else:
                logger.warning("Neo4j connection failed")
                self.graph_store = None
        except Exception as e:
            logger.error(f"Failed to initialize Neo4j graph store: {e}")
            self.graph_store = None
    
    async def connect(self, websocket: WebSocket, client_id: str):
        """Accept a new WebSocket connection."""
        await websocket.accept()
        self.active_connections[client_id] = websocket
        logger.info(f"Client #{client_id} connected. Active connections: {len(self.active_connections)}")
        
        # Send initial connection message
        await self._send_system_message(
            websocket,
            "Connected to Homework API Server",
            {
                "llm_available": self.llm_client is not None,
                "github_available": self.github_client is not None,
                "neo4j_available": self.graph_store is not None,
                "client_id": client_id
            }
        )
    
    async def disconnect(self, client_id: str):
        """Handle client disconnection."""
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            logger.info(f"Client #{client_id} disconnected. Active connections: {len(self.active_connections)}")
    
    async def process_message(self, message_text: str, websocket: WebSocket):
        """Process an incoming message from a client."""
        try:
            # Parse message as JSON
            message_data = json.loads(message_text)
            
            # Extract message type and content
            message_type = message_data.get("type", "text")
            content = message_data.get("content", "")
            client_id = message_data.get("client_id", "unknown")
            
            logger.info(f"Received {message_type} message from client #{client_id}")
            
            # Process based on message type
            if message_type == "text":
                await self._process_text_message(content, websocket, client_id)
            elif message_type == "command":
                await self._process_command(content, websocket, client_id)
            elif message_type == "task_status":
                await self._send_task_status(content, websocket)
            else:
                await self._send_error(websocket, f"Unknown message type: {message_type}")
                
        except json.JSONDecodeError:
            # If not JSON, treat as plain text
            await self._process_text_message(message_text, websocket, "unknown")
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}", exc_info=True)
            await self._send_error(websocket, f"Error processing message: {str(e)}")
    
    async def _process_text_message(self, content: str, websocket: WebSocket, client_id: str):
        """Process a text message, potentially using LLM."""
        # Try to initialize LLM client again if it's not available
        if not self.llm_client:
            try:
                # Try to get from credential manager first
                openai_key = self.credentials_manager.get_openai_key()
                
                # If not found, check environment directly
                if not openai_key:
                    openai_key = os.environ.get("OPENAI_API_KEY")
                    if openai_key:
                        logger.info("Using OpenAI API key from environment variables")
                
                if openai_key:
                    self.llm_client = LLMClient(api_key=openai_key)
                    logger.info("LLM client initialized on first message")
            except Exception as e:
                logger.error(f"Failed to initialize LLM client on demand: {e}")
                
        # Check if LLM is available after retry attempt
        if not self.llm_client:
            await self._send_error(
                websocket, 
                "OpenAI API key not configured. Please go to the Configuration page and set up your OpenAI API key."
            )
            return
        
        try:
            # Send "typing" indicator
            await self._send_system_message(websocket, "Thinking...", {"status": "typing"})
            
            # Process with LLM
            response = await self._generate_llm_response(content)
            
            # Send response
            await self._send_message(websocket, "assistant", response)
            
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}", exc_info=True)
            await self._send_error(websocket, f"Error generating response: {str(e)}")
    
    async def _generate_llm_response(self, user_message: str) -> str:
        """Generate a response using the LLM."""
        if not self.llm_client:
            return "LLM service is not available. Please configure your OpenAI API key in the Configuration page."
        
        try:
            # Call the async generate_response method directly if it exists
            if hasattr(self.llm_client, 'generate_response') and callable(self.llm_client.generate_response):
                if asyncio.iscoroutinefunction(self.llm_client.generate_response):
                    # If generate_response is already async
                    response = await self.llm_client.generate_response(user_message)
                else:
                    # If generate_response is synchronous, run in thread
                    response = await asyncio.to_thread(
                        self.llm_client.generate_response,
                        user_message
                    )
                return response
            else:
                logger.error("LLM client does not have a generate_response method")
                return "LLM service is misconfigured. Please check the logs."
        except Exception as e:
            logger.error(f"LLM error: {str(e)}", exc_info=True)
            return f"I encountered an error: {str(e)}"
    
    async def _process_command(self, command: str, websocket: WebSocket, client_id: str):
        """Process a command message."""
        command = command.strip().lower()
        
        # Split command and arguments
        parts = command.split(" ", 1)
        cmd = parts[0]
        args = parts[1] if len(parts) > 1 else ""
        
        # Command router
        if cmd == "help":
            await self._send_help(websocket)
        elif cmd == "github":
            await self._process_github_command(args, websocket)
        elif cmd == "graph":
            await self._process_graph_command(args, websocket)
        elif cmd == "task":
            await self._process_task_command(args, websocket)
        elif cmd == "status":
            await self._send_status(websocket)
        else:
            await self._send_error(websocket, f"Unknown command: {cmd}. Type 'help' for available commands.")
    
    async def _process_github_command(self, args: str, websocket: WebSocket):
        """Process GitHub related commands."""
        if not self.github_client:
            await self._send_error(
                websocket, 
                "GitHub client is not available. Please configure GitHub credentials in settings."
            )
            return
        
        # Split args into subcommand and parameters
        parts = args.split(" ", 1)
        subcmd = parts[0] if parts else ""
        params = parts[1] if len(parts) > 1 else ""
        
        try:
            if subcmd == "repos":
                # List repositories for a user or organization
                if not params:
                    await self._send_error(websocket, "Please specify a username or organization name.")
                    return
                
                await self._send_system_message(websocket, f"Fetching repositories for {params}...", {"status": "working"})
                
                repos = await asyncio.to_thread(
                    self.github_client.list_repositories,
                    params
                )
                
                if repos:
                    await self._send_system_message(
                        websocket, 
                        f"Found {len(repos)} repositories for {params}",
                        {"repos": repos, "status": "complete"}
                    )
                else:
                    await self._send_error(websocket, f"No repositories found for {params}")
            
            elif subcmd == "search":
                # Search for repositories
                if not params:
                    await self._send_error(websocket, "Please specify a search query.")
                    return
                
                await self._send_system_message(websocket, f"Searching for '{params}'...", {"status": "working"})
                
                results = await asyncio.to_thread(
                    self.github_client.search_repositories,
                    params
                )
                
                if results:
                    await self._send_system_message(
                        websocket, 
                        f"Found {len(results)} repositories matching '{params}'",
                        {"repos": results, "status": "complete"}
                    )
                else:
                    await self._send_error(websocket, f"No repositories found matching '{params}'")
            
            else:
                await self._send_error(
                    websocket, 
                    f"Unknown GitHub command: {subcmd}. Available: repos, search"
                )
        
        except Exception as e:
            logger.error(f"GitHub command error: {str(e)}", exc_info=True)
            await self._send_error(websocket, f"Error executing GitHub command: {str(e)}")
    
    async def _process_graph_command(self, args: str, websocket: WebSocket):
        """Process knowledge graph related commands."""
        if not self.graph_store:
            await self._send_error(
                websocket, 
                "Neo4j connection is not available. Please configure Neo4j in settings."
            )
            return
        
        # Split args into subcommand and parameters
        parts = args.split(" ", 1)
        subcmd = parts[0] if parts else ""
        params = parts[1] if len(parts) > 1 else ""
        
        try:
            if subcmd == "list":
                # List knowledge graphs
                await self._send_system_message(websocket, "Listing knowledge graphs...", {"status": "working"})
                
                graphs = await asyncio.to_thread(
                    self.graph_store.list_graphs
                )
                
                if graphs:
                    await self._send_system_message(
                        websocket, 
                        f"Found {len(graphs)} knowledge graphs",
                        {"graphs": graphs, "status": "complete"}
                    )
                else:
                    await self._send_system_message(
                        websocket, 
                        "No knowledge graphs found",
                        {"graphs": [], "status": "complete"}
                    )
            
            elif subcmd == "stats":
                # Get statistics for a graph
                if not params:
                    await self._send_error(websocket, "Please specify a graph name.")
                    return
                
                await self._send_system_message(websocket, f"Fetching statistics for graph '{params}'...", {"status": "working"})
                
                # Use a graph store instance for the specific graph
                specific_graph = GraphStore(graph_name=params)
                stats = await asyncio.to_thread(
                    specific_graph.get_statistics
                )
                
                if stats:
                    await self._send_system_message(
                        websocket, 
                        f"Statistics for graph '{params}'",
                        {"stats": stats, "status": "complete"}
                    )
                else:
                    await self._send_error(websocket, f"No statistics found for graph '{params}'")
            
            else:
                await self._send_error(
                    websocket, 
                    f"Unknown graph command: {subcmd}. Available: list, stats"
                )
        
        except Exception as e:
            logger.error(f"Graph command error: {str(e)}", exc_info=True)
            await self._send_error(websocket, f"Error executing graph command: {str(e)}")
    
    async def _process_task_command(self, args: str, websocket: WebSocket):
        """Process task related commands."""
        # Split args into subcommand and parameters
        parts = args.split(" ", 1)
        subcmd = parts[0] if parts else ""
        params = parts[1] if len(parts) > 1 else ""
        
        try:
            if subcmd == "list":
                # List tasks
                tasks = self.task_tracker.list_resumable_tasks()
                
                await self._send_system_message(
                    websocket, 
                    f"Found {len(tasks)} tasks",
                    {"tasks": tasks, "status": "complete"}
                )
            
            elif subcmd == "status":
                # Get task status
                if not params:
                    await self._send_error(websocket, "Please specify a task ID.")
                    return
                
                task = self.task_tracker.get_task(params)
                
                if task:
                    await self._send_system_message(
                        websocket, 
                        f"Status for task {params}: {task.get('status', 'unknown')}",
                        {"task": task, "status": "complete"}
                    )
                else:
                    await self._send_error(websocket, f"No task found with ID {params}")
            
            elif subcmd == "cancel":
                # Cancel a task
                if not params:
                    await self._send_error(websocket, "Please specify a task ID.")
                    return
                
                success = self.task_tracker.cancel_task(params)
                
                if success:
                    await self._send_system_message(
                        websocket, 
                        f"Task {params} cancelled successfully",
                        {"task_id": params, "status": "complete"}
                    )
                else:
                    await self._send_error(websocket, f"Failed to cancel task {params}")
            
            else:
                await self._send_error(
                    websocket, 
                    f"Unknown task command: {subcmd}. Available: list, status, cancel"
                )
        
        except Exception as e:
            logger.error(f"Task command error: {str(e)}", exc_info=True)
            await self._send_error(websocket, f"Error executing task command: {str(e)}")
    
    async def _send_task_status(self, task_id: str, websocket: WebSocket):
        """Send status updates for a specific task."""
        task = self.task_tracker.get_task(task_id)
        
        if task:
            await self._send_system_message(
                websocket, 
                f"Task {task_id} status: {task.get('status', 'unknown')}",
                {"task": task}
            )
        else:
            await self._send_error(websocket, f"No task found with ID {task_id}")
    
    async def _send_status(self, websocket: WebSocket):
        """Send system status information."""
        status = {
            "llm_available": self.llm_client is not None,
            "github_available": self.github_client is not None,
            "neo4j_available": self.graph_store is not None,
            "task_count": len(self.task_tracker.list_resumable_tasks()),
            "server_time": datetime.now().isoformat()
        }
        
        await self._send_system_message(
            websocket, 
            "System Status",
            {"status": status}
        )
    
    async def _send_help(self, websocket: WebSocket):
        """Send help information."""
        help_text = """
        Available commands:
        - help: Show this help message
        - status: Show system status
        - github repos <username>: List repositories for a user or organization
        - github search <query>: Search for repositories
        - graph list: List all knowledge graphs
        - graph stats <name>: Show statistics for a knowledge graph
        - task list: List all tasks
        - task status <id>: Show status for a specific task
        - task cancel <id>: Cancel a task
        
        Or simply type a message to chat with the assistant.
        """
        
        await self._send_system_message(websocket, help_text.strip(), {"type": "help"})
    
    async def _send_message(self, websocket: WebSocket, role: str, content: str):
        """Send a chat message to the client."""
        message = {
            "id": str(uuid.uuid4()),
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        }
        
        await websocket.send_text(json.dumps(message))
    
    async def _send_system_message(self, websocket: WebSocket, content: str, data: Dict[str, Any] = None):
        """Send a system message to the client."""
        message = {
            "id": str(uuid.uuid4()),
            "role": "system",
            "content": content,
            "data": data or {},
            "timestamp": datetime.now().isoformat()
        }
        
        await websocket.send_text(json.dumps(message))
    
    async def _send_error(self, websocket: WebSocket, error_message: str):
        """Send an error message to the client."""
        message = {
            "id": str(uuid.uuid4()),
            "role": "system",
            "content": error_message,
            "error": True,
            "timestamp": datetime.now().isoformat()
        }
        
        await websocket.send_text(json.dumps(message))
    
    async def broadcast(self, message: str, data: Dict[str, Any] = None):
        """Broadcast a message to all connected clients."""
        for client_id, websocket in self.active_connections.items():
            try:
                await self._send_system_message(websocket, message, data)
            except Exception as e:
                logger.error(f"Error broadcasting to client {client_id}: {str(e)}")