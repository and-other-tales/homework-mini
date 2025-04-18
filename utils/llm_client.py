"""LLM client module supporting OpenAI models and Agents SDK."""

import json
import os
import logging
import requests
import asyncio
import time
from typing import Dict, Any, Optional, List, Union, Callable
import traceback

# Setup logging
logger = logging.getLogger(__name__)

# Import OpenAI Agents SDK (lazy import)
def get_agents_sdk():
    """Lazily import the agents SDK to avoid hard dependency."""
    try:
        import agents
        return agents
    except ImportError:
        logger.warning("OpenAI Agents SDK not installed. Install with: pip install openai-agents")
        return None

class LLMClient:
    """LLM client for generating chat responses using OpenAI API and Agents SDK."""

    def __init__(self, api_key: str = None, credentials_manager = None):
        """
        Initialize the LLM client.
        
        Args:
            api_key: The OpenAI API key
            credentials_manager: Optional credentials manager to get credentials
        """
        # First check if API key was provided directly
        self.api_key = api_key
        self.model = "gpt-3.5-turbo"  # Default model
        self._agents_mode = False  # Whether to use the Agents SDK
        self.credentials_manager = credentials_manager
        
        # If no API key was provided, try to get it from environment
        if not self.api_key:
            # Force load environment variables again to ensure we get the latest
            from utils.env_loader import load_environment_variables
            load_environment_variables()
            
            # Check environment directly
            env_key = os.environ.get("OPENAI_API_KEY")
            if env_key:
                logger.info("Using OpenAI API key from environment")
                self.api_key = env_key
        
        # If still no API key, try credentials manager
        if not self.api_key and credentials_manager:
            try:
                self.api_key = credentials_manager.get_openai_key()
                if self.api_key:
                    logger.info("Using OpenAI API key from credentials manager")
            except Exception as e:
                logger.error(f"Error getting OpenAI key from credentials manager: {e}")
        
        # If still no API key, try to read .env file directly (last resort)
        if not self.api_key:
            try:
                # Try to find .env file in common locations
                import re
                from pathlib import Path
                
                env_paths = [
                    Path(".env"),
                    Path("../.env"),
                    Path(os.path.join(os.path.dirname(__file__), "../../.env")),
                    Path(os.path.expanduser("~/.env")),
                ]
                
                for env_path in env_paths:
                    if env_path.exists():
                        logger.info(f"Reading .env file directly from {env_path}")
                        env_content = env_path.read_text()
                        key_match = re.search(r'OPENAI_API_KEY=(.+)', env_content)
                        
                        if key_match:
                            self.api_key = key_match.group(1).strip()
                            logger.info("Found OpenAI API key directly in .env file")
                            break
            except Exception as e:
                logger.error(f"Error reading .env file directly: {e}")
        
        if not self.api_key:
            logger.warning("No OpenAI API key provided. Many features will not work.")
        else:
            logger.info("LLM client initialized with API key")
            # Set the API key in the environment for Agents SDK
            os.environ["OPENAI_API_KEY"] = self.api_key
            
            # Log a masked version of the key for debugging
            masked_key = self.api_key[:4] + "..." + self.api_key[-4:] if len(self.api_key) > 8 else "***"
            logger.info(f"Using API key starting with {masked_key}")
                
            # Try to initialize the Agents SDK
            agents_sdk = get_agents_sdk()
            if agents_sdk:
                self._agents_mode = True
                logger.info("OpenAI Agents SDK initialized successfully")
            else:
                logger.warning("OpenAI Agents SDK not available, falling back to basic API")

    @property
    def has_agents_sdk(self) -> bool:
        """Check if the Agents SDK is available."""
        return self._agents_mode and get_agents_sdk() is not None

    def _create_crawler_tool(self):
        """Create a function tool for the web crawler."""
        agents = get_agents_sdk()
        if not agents:
            return None
            
        # Import crawler functionality
        try:
            from web.crawler import WebCrawler
            
            @agents.function_tool
            async def crawl_website(url: str, recursive: bool = False, max_pages: int = 10, 
                                   user_instructions: str = None, max_depth: int = None,
                                   content_filters: list = None, url_patterns: list = None) -> str:
                """
                Crawl a website to extract information.
                
                Args:
                    url: The URL to start crawling from
                    recursive: Whether to follow links on the page
                    max_pages: Maximum number of pages to crawl
                    user_instructions: Description of what to look for or extract
                    max_depth: Maximum link depth to crawl (None for unlimited)
                    content_filters: List of keywords to filter content by (only keep pages containing these terms)
                    url_patterns: List of regex patterns to filter URLs (only follow URLs matching these patterns)
                
                Returns:
                    A summary of the crawled content
                """
                logger.info(f"Agent calling crawl_website with URL: {url}")
                try:
                    crawler = WebCrawler()
                    
                    # Progress tracking function (not used in async mode)
                    def progress_callback(percent, message):
                        pass
                    
                    # Crawl with AI guidance when user instructions are provided
                    use_ai = user_instructions is not None and len(user_instructions) > 0
                    
                    results = crawler.crawl_website(
                        start_url=url,
                        recursive=recursive,
                        max_pages=max_pages,
                        progress_callback=progress_callback,
                        user_instructions=user_instructions,
                        use_ai_guidance=use_ai,
                        max_depth=max_depth,
                        content_filters=content_filters,
                        url_patterns=url_patterns
                    )
                    
                    # Summarize the results
                    summary = f"Crawled {len(results)} pages from {url}.\n\n"
                    
                    if len(results) > 0:
                        # Extract key information
                        titles = [page.get("title", "Untitled") for page in results if page.get("title")]
                        summary += f"Found pages with titles: {', '.join(titles[:5])}"
                        
                        if len(titles) > 5:
                            summary += f" and {len(titles) - 5} more."
                        summary += "\n\n"
                        
                        # Include first page content as sample
                        if "markdown" in results[0]:
                            content_sample = results[0]["markdown"]
                            # Truncate if too long
                            if len(content_sample) > 1000:
                                content_sample = content_sample[:1000] + "...[truncated]"
                            summary += f"Sample content from first page:\n{content_sample}"
                    
                    return summary
                except Exception as e:
                    logger.error(f"Error in crawl_website tool: {str(e)}")
                    return f"Error crawling website: {str(e)}"
            
            return crawl_website
        except ImportError:
            logger.error("Failed to import WebCrawler")
            return None
        except Exception as e:
            logger.error(f"Error creating crawler tool: {e}")
            return None

    def _create_dataset_creation_tool(self):
        """Create a function tool for dataset creation."""
        agents = get_agents_sdk()
        if not agents:
            return None
            
        try:
            from huggingface.dataset_creator import DatasetCreator
            
            @agents.function_tool
            async def create_dataset(name: str, description: str, source_type: str, 
                                    source_url: str) -> str:
                """
                Create a dataset from a GitHub repository or web content.
                
                Args:
                    name: The name for the dataset
                    description: A description of the dataset
                    source_type: Either 'repository', 'organization', or 'website'
                    source_url: The URL of the source (GitHub repo URL or website URL)
                
                Returns:
                    A status message about the created dataset
                """
                logger.info(f"Agent calling create_dataset for {source_type}: {source_url}")
                
                try:
                    # Validate inputs
                    if source_type not in ["repository", "organization", "website"]:
                        return f"Invalid source_type: {source_type}. Must be 'repository', 'organization', or 'website'."
                    
                    # Get credentials from credentials manager
                    from config.credentials_manager import CredentialsManager
                    creds_manager = CredentialsManager()
                    
                    # Get HuggingFace token
                    hf_username, hf_token = creds_manager.get_huggingface_credentials()
                    if not hf_token:
                        return "Error: Hugging Face token not configured. Please set up your Hugging Face credentials."
                    
                    # Initialize the dataset creator
                    dataset_creator = DatasetCreator(huggingface_token=hf_token)
                    
                    # Process based on source type
                    if source_type == "website":
                        # Create dataset from website
                        from web.crawler import WebCrawler
                        crawler = WebCrawler()
                        
                        # Crawl the website
                        crawled_data = crawler.crawl_website(
                            start_url=source_url,
                            recursive=True,
                            max_pages=50
                        )
                        
                        # Prepare data for dataset
                        file_data_list = crawler.prepare_data_for_dataset(crawled_data)
                        
                        # Create and push dataset
                        success, dataset = dataset_creator.create_and_push_dataset(
                            file_data_list=file_data_list,
                            dataset_name=name,
                            description=description,
                            source_info=source_url
                        )
                        
                        if success:
                            return f"Successfully created dataset '{name}' from website {source_url} with {len(file_data_list)} files."
                        else:
                            return f"Failed to create dataset from website {source_url}."
                    
                    elif source_type == "repository":
                        # Create dataset from repository
                        result = dataset_creator.create_dataset_from_repository(
                            repo_url=source_url,
                            dataset_name=name,
                            description=description
                        )
                        
                        if result.get("success"):
                            return f"Successfully created dataset '{name}' from repository {source_url}."
                        else:
                            return f"Failed to create dataset: {result.get('message', 'Unknown error')}"
                    
                    elif source_type == "organization":
                        # Import content fetcher
                        from github.content_fetcher import ContentFetcher
                        
                        # Get GitHub token
                        github_token = creds_manager.get_github_token()
                        
                        # Initialize content fetcher
                        content_fetcher = ContentFetcher(github_token=github_token)
                        
                        # Fetch repositories from organization
                        repos = content_fetcher.fetch_org_repositories(source_url)
                        
                        if not repos:
                            return f"No repositories found for organization: {source_url}"
                        
                        # Fetch content from all repositories
                        content = content_fetcher.fetch_multiple_repositories(source_url)
                        
                        if not content:
                            return f"No content found in repositories for organization: {source_url}"
                        
                        # Create and push dataset
                        success, dataset = dataset_creator.create_and_push_dataset(
                            file_data_list=content,
                            dataset_name=name,
                            description=description,
                            source_info=source_url
                        )
                        
                        if success:
                            return f"Successfully created dataset '{name}' from organization {source_url} with {len(repos)} repositories and {len(content)} files."
                        else:
                            return f"Failed to create dataset from organization {source_url}."
                    
                    return f"Unknown source type: {source_type}"
                
                except Exception as e:
                    logger.error(f"Error in create_dataset tool: {str(e)}")
                    logger.error(traceback.format_exc())
                    return f"Error creating dataset: {str(e)}"
            
            return create_dataset
        except ImportError:
            logger.error("Failed to import DatasetCreator")
            return None
        except Exception as e:
            logger.error(f"Error creating dataset creation tool: {e}")
            return None

    def _create_knowledge_graph_tool(self):
        """Create a function tool for knowledge graph operations."""
        agents = get_agents_sdk()
        if not agents:
            return None
            
        try:
            from knowledge_graph.graph_store import GraphStore
            
            @agents.function_tool
            async def manage_knowledge_graph(action: str, graph_name: str, 
                                           description: str = None) -> str:
                """
                Create, view, or manage a knowledge graph.
                
                Args:
                    action: The action to perform ('create', 'list', 'view', 'delete')
                    graph_name: The name of the knowledge graph
                    description: A description of the graph (for create action)
                
                Returns:
                    A status message about the knowledge graph operation
                """
                logger.info(f"Agent calling manage_knowledge_graph with action: {action}")
                
                try:
                    # Initialize graph store
                    graph_store = GraphStore()
                    
                    # Check connection
                    if not graph_store.test_connection():
                        return "Failed to connect to Neo4j database. Check database configuration."
                    
                    # Process action
                    action = action.lower()
                    
                    if action == "list":
                        graphs = graph_store.list_graphs()
                        return f"Found {len(graphs)} knowledge graphs: {', '.join(graphs)}" if graphs else "No knowledge graphs found."
                    
                    elif action == "create":
                        if not graph_name:
                            return "Graph name is required for create action."
                        
                        # Create the graph
                        success = graph_store.create_graph(graph_name, description)
                        
                        if success:
                            # Initialize schema on the new graph
                            specific_graph = GraphStore(graph_name=graph_name)
                            specific_graph.initialize_schema()
                            
                            return f"Knowledge graph '{graph_name}' created successfully."
                        else:
                            return f"Failed to create knowledge graph '{graph_name}'."
                    
                    elif action == "view":
                        if not graph_name:
                            return "Graph name is required for view action."
                        
                        # Get statistics for the specified graph
                        specific_graph = GraphStore(graph_name=graph_name)
                        stats = specific_graph.get_statistics()
                        
                        if stats:
                            return f"Statistics for graph '{graph_name}': {json.dumps(stats)}"
                        else:
                            return f"Failed to retrieve statistics for graph '{graph_name}'."
                    
                    elif action == "delete":
                        if not graph_name:
                            return "Graph name is required for delete action."
                        
                        # Delete the graph
                        success = graph_store.delete_graph(graph_name)
                        
                        if success:
                            return f"Knowledge graph '{graph_name}' deleted successfully."
                        else:
                            return f"Failed to delete knowledge graph '{graph_name}'."
                    
                    else:
                        return f"Invalid action: {action}. Must be 'create', 'list', 'view', or 'delete'."
                
                except Exception as e:
                    logger.error(f"Error in manage_knowledge_graph tool: {str(e)}")
                    return f"Error managing knowledge graph: {str(e)}"
            
            return manage_knowledge_graph
        except ImportError:
            logger.error("Failed to import GraphStore")
            return None
        except Exception as e:
            logger.error(f"Error creating knowledge graph tool: {e}")
            return None

    async def _create_agent(self, user_message: str = None) -> Any:
        """
        Create and configure an OpenAI Agent with the appropriate tools.
        
        Args:
            user_message: Optional message to determine if need for specialized tools
        
        Returns:
            An OpenAI Agent object or None if failed
        """
        agents = get_agents_sdk()
        if not agents:
            return None
            
        try:
            # Determine what tools to include based on the message content
            tools = []
            
            # Always include web search
            web_search_tool = agents.WebSearchTool()
            tools.append(web_search_tool)
            
            # Check if message indicates need for crawling or dataset tools
            crawler_terms = ["crawl", "scrape", "extract", "website", "webpage", "web page"]
            dataset_terms = ["dataset", "create dataset", "hugging face", "huggingface"]
            knowledge_graph_terms = ["knowledge graph", "graph", "neo4j"]
            
            # Make user_message case-insensitive
            message_lower = user_message.lower() if user_message else ""
            
            # Check if we need crawler tool
            if user_message and any(term in message_lower for term in crawler_terms):
                logger.info("Adding crawler tool based on user message")
                crawler_tool = self._create_crawler_tool()
                if crawler_tool:
                    tools.append(crawler_tool)
            
            # Check if we need dataset creation tool
            if user_message and any(term in message_lower for term in dataset_terms):
                logger.info("Adding dataset creation tool based on user message")
                dataset_tool = self._create_dataset_creation_tool()
                if dataset_tool:
                    tools.append(dataset_tool)
            
            # Check if we need knowledge graph tool
            if user_message and any(term in message_lower for term in knowledge_graph_terms):
                logger.info("Adding knowledge graph tool based on user message")
                knowledge_graph_tool = self._create_knowledge_graph_tool()
                if knowledge_graph_tool:
                    tools.append(knowledge_graph_tool)
            
            # Create the main agent
            agent = agents.Agent(
                name="Homework Assistant",
                instructions=(
                    "You are a helpful assistant for the Homework project. "
                    "Your primary focus is helping users gather and organize information "
                    "through web searching, web crawling, and dataset creation. "
                    "You can search the web, crawl websites, create datasets from GitHub repositories "
                    "or web content, and manage knowledge graphs. "
                    "For web crawling tasks, try to understand what specific information the user is looking for "
                    "and provide detailed instructions to the crawler. "
                    "For dataset creation, help the user understand the structure of the source repository or "
                    "organization, and explain how the data will be organized. "
                    "Always be clear about what you're doing and why."
                ),
                tools=tools
            )
            
            return agent
        except Exception as e:
            logger.error(f"Error creating agent: {e}")
            logger.error(traceback.format_exc())
            return None

    async def run_agent(self, message: str, progress_callback: Callable = None, options: Dict = None) -> Dict:
        """
        Run an agent with automatic tool selection.
        
        Args:
            message: The user message to process
            progress_callback: Optional callback for progress updates
            options: Additional options for the agent
            
        Returns:
            Dictionary with the agent result
        """
        if not self.api_key:
            return {
                "success": False,
                "message": "OpenAI API key not configured",
                "data": None
            }
            
        if not self.has_agents_sdk:
            return {
                "success": False,
                "message": "OpenAI Agents SDK not available",
                "data": None
            }
            
        try:
            # Create agent with appropriate tools based on message
            agent = await self._create_agent(message)
            if not agent:
                return {
                    "success": False,
                    "message": "Failed to initialize agent",
                    "data": None
                }
                
            # Track progress
            if progress_callback:
                progress_callback(10, "Agent initialized")
                
            # Run the agent
            agents = get_agents_sdk()
            logger.info(f"Running agent with message: {message}")
            
            # Run the agent with progress tracking
            result = await agents.Runner.run(agent, message)
            
            # Update progress
            if progress_callback:
                progress_callback(100, "Agent task completed")
                
            if result and hasattr(result, 'final_output'):
                return {
                    "success": True,
                    "message": "Agent task completed successfully",
                    "data": {
                        "response": result.final_output,
                        "tool_calls": [
                            {"tool": tc.tool_name, "input": tc.tool_input, "output": tc.tool_output}
                            for tc in (result.tool_calls if hasattr(result, 'tool_calls') else [])
                        ]
                    }
                }
            else:
                return {
                    "success": False,
                    "message": "Agent returned invalid response",
                    "data": None
                }
                
        except Exception as e:
            logger.error(f"Error running agent: {e}")
            logger.error(traceback.format_exc())
            
            return {
                "success": False,
                "message": f"Error: {str(e)}",
                "data": None
            }
            
    async def run_web_agent(self, message: str, url_patterns: List[str] = None,
                         max_depth: int = 3, content_filters: List[str] = None,
                         progress_callback: Callable = None, export_to_graph: bool = False,
                         graph_name: str = None, dataset_name: str = None,
                         description: str = None) -> Dict:
        """
        Run an agent specialized for web crawling.
        
        Args:
            message: User message with instructions
            url_patterns: Optional patterns to filter URLs
            max_depth: Maximum crawl depth
            content_filters: Optional content filters
            progress_callback: Optional callback for progress updates
            export_to_graph: Whether to export results to a knowledge graph
            graph_name: Name of the knowledge graph to export to
            dataset_name: Name for the dataset
            description: Description for the dataset
            
        Returns:
            Dictionary with the agent result
        """
        if not self.api_key:
            return {
                "success": False,
                "message": "OpenAI API key not configured",
                "data": None
            }
            
        if not self.has_agents_sdk:
            return {
                "success": False,
                "message": "OpenAI Agents SDK not available",
                "data": None
            }
            
        try:
            # Create crawler agent
            agents = get_agents_sdk()
            
            # Create tools
            crawler_tool = self._create_crawler_tool()
            web_search_tool = agents.WebSearchTool()
            dataset_tool = self._create_dataset_creation_tool() if dataset_name else None
            knowledge_graph_tool = self._create_knowledge_graph_tool() if export_to_graph else None
            
            tools = [web_search_tool, crawler_tool]
            if dataset_tool:
                tools.append(dataset_tool)
            if knowledge_graph_tool:
                tools.append(knowledge_graph_tool)
                
            # Create specialized crawler agent
            agent = agents.Agent(
                name="Web Crawler Assistant",
                instructions=(
                    "You are a specialized web crawler assistant. "
                    "Your primary task is to analyze the user's request, find relevant websites, "
                    "and extract the requested information by crawling websites. "
                    "Follow these steps:\n"
                    "1. Analyze the user's message to understand what they want to find\n"
                    "2. Use web search to identify the most relevant websites\n"
                    "3. Crawl those websites to extract information, paying attention to any special instructions\n"
                    f"4. {('Create a dataset named ' + dataset_name + ' with the extracted content') if dataset_name else 'Summarize the findings'}\n"
                    f"5. {('Export the data to the knowledge graph named ' + graph_name) if export_to_graph and graph_name else 'Provide a concise summary of the results'}\n"
                    "\nWhen crawling websites, be thoughtful about the depth and scope. Use the supplied options for URL patterns, "
                    "max depth, and content filters."
                ),
                tools=tools
            )
            
            # Track progress
            if progress_callback:
                progress_callback(10, "Web crawler agent initialized")
                
            # Create specialized system message with task details
            system_prompt = (
                f"Task: Web crawling to extract information\n"
                f"User message: {message}\n"
                f"Options:\n"
                f"- URL patterns: {', '.join(url_patterns) if url_patterns else 'None'}\n"
                f"- Max depth: {max_depth}\n"
                f"- Content filters: {', '.join(content_filters) if content_filters else 'None'}\n"
                f"- Dataset name: {dataset_name if dataset_name else 'None'}\n"
                f"- Export to graph: {graph_name if export_to_graph else 'No'}\n"
                f"\nPlease process this web crawling task according to these specifications."
            )
            
            # Run the agent with progress tracking
            # Use periodic updates for progress callback
            if progress_callback:
                progress_callback(20, "Starting web crawling task")
                
                async def update_progress():
                    progress = 20
                    while progress < 90:
                        await asyncio.sleep(3)  # Update every 3 seconds
                        progress += 5
                        progress_callback(progress, "Processing web crawling task")
                
                # Start progress updates in background
                progress_task = asyncio.create_task(update_progress())
                
            # Run the agent
            result = await agents.Runner.run(agent, system_prompt)
            
            # Update progress
            if progress_callback:
                progress_callback(100, "Web crawling task completed")
                
            if result and hasattr(result, 'final_output'):
                return {
                    "success": True,
                    "message": "Web crawling task completed successfully",
                    "data": {
                        "response": result.final_output,
                        "tool_calls": [
                            {"tool": tc.tool_name, "input": tc.tool_input, "output": tc.tool_output}
                            for tc in (result.tool_calls if hasattr(result, 'tool_calls') else [])
                        ],
                        "dataset_name": dataset_name,
                        "graph_name": graph_name if export_to_graph else None
                    }
                }
            else:
                return {
                    "success": False,
                    "message": "Web crawling agent returned invalid response",
                    "data": None
                }
                
        except Exception as e:
            logger.error(f"Error running web agent: {e}")
            logger.error(traceback.format_exc())
            
            return {
                "success": False,
                "message": f"Error: {str(e)}",
                "data": None
            }
            
    async def run_github_agent(self, message: str, progress_callback: Callable = None,
                             export_to_graph: bool = False, graph_name: str = None,
                             dataset_name: str = None, description: str = None) -> Dict:
        """
        Run an agent specialized for GitHub operations.
        
        Args:
            message: User message with instructions
            progress_callback: Optional callback for progress updates
            export_to_graph: Whether to export results to a knowledge graph
            graph_name: Name of the knowledge graph to export to
            dataset_name: Name for the dataset
            description: Description for the dataset
            
        Returns:
            Dictionary with the agent result
        """
        if not self.api_key:
            return {
                "success": False,
                "message": "OpenAI API key not configured",
                "data": None
            }
            
        if not self.has_agents_sdk:
            return {
                "success": False,
                "message": "OpenAI Agents SDK not available",
                "data": None
            }
            
        try:
            # Create GitHub agent
            agents = get_agents_sdk()
            
            # Create tools
            web_search_tool = agents.WebSearchTool()
            dataset_tool = self._create_dataset_creation_tool()
            knowledge_graph_tool = self._create_knowledge_graph_tool() if export_to_graph else None
            
            tools = [web_search_tool, dataset_tool]
            if knowledge_graph_tool:
                tools.append(knowledge_graph_tool)
                
            # Create specialized GitHub agent
            agent = agents.Agent(
                name="GitHub Assistant",
                instructions=(
                    "You are a specialized GitHub assistant. "
                    "Your primary task is to analyze the user's request, find relevant GitHub repositories, "
                    "and create datasets from these repositories. "
                    "Follow these steps:\n"
                    "1. Analyze the user's message to understand what GitHub content they need\n"
                    "2. Use web search to identify the most relevant GitHub repositories or organizations\n"
                    "3. Create a dataset with the content from these repositories\n"
                    f"4. {('Export the data to the knowledge graph named ' + graph_name) if export_to_graph and graph_name else 'Provide a concise summary of the results'}\n"
                    "\nBe thorough in your analysis and dataset creation."
                ),
                tools=tools
            )
            
            # Track progress
            if progress_callback:
                progress_callback(10, "GitHub agent initialized")
                
            # Create specialized system message with task details
            system_prompt = (
                f"Task: GitHub dataset creation\n"
                f"User message: {message}\n"
                f"Options:\n"
                f"- Dataset name: {dataset_name if dataset_name else 'Auto-generated name'}\n"
                f"- Dataset description: {description if description else 'Auto-generated description'}\n"
                f"- Export to graph: {graph_name if export_to_graph else 'No'}\n"
                f"\nPlease process this GitHub task according to these specifications."
            )
            
            # Run the agent with progress tracking
            # Use periodic updates for progress callback
            if progress_callback:
                progress_callback(20, "Starting GitHub task")
                
                async def update_progress():
                    progress = 20
                    while progress < 90:
                        await asyncio.sleep(3)  # Update every 3 seconds
                        progress += 5
                        progress_callback(progress, "Processing GitHub task")
                
                # Start progress updates in background
                progress_task = asyncio.create_task(update_progress())
                
            # Run the agent
            result = await agents.Runner.run(agent, system_prompt)
            
            # Update progress
            if progress_callback:
                progress_callback(100, "GitHub task completed")
                
            if result and hasattr(result, 'final_output'):
                return {
                    "success": True,
                    "message": "GitHub task completed successfully",
                    "data": {
                        "response": result.final_output,
                        "tool_calls": [
                            {"tool": tc.tool_name, "input": tc.tool_input, "output": tc.tool_output}
                            for tc in (result.tool_calls if hasattr(result, 'tool_calls') else [])
                        ],
                        "dataset_name": dataset_name,
                        "graph_name": graph_name if export_to_graph else None
                    }
                }
            else:
                return {
                    "success": False,
                    "message": "GitHub agent returned invalid response",
                    "data": None
                }
                
        except Exception as e:
            logger.error(f"Error running GitHub agent: {e}")
            logger.error(traceback.format_exc())
            
            return {
                "success": False,
                "message": f"Error: {str(e)}",
                "data": None
            }
            
    async def run_knowledge_graph_agent(self, message: str, graph_name: str = None,
                                      progress_callback: Callable = None) -> Dict:
        """
        Run an agent specialized for knowledge graph operations.
        
        Args:
            message: User message with instructions
            graph_name: Name of the knowledge graph
            progress_callback: Optional callback for progress updates
            
        Returns:
            Dictionary with the agent result
        """
        if not self.api_key:
            return {
                "success": False,
                "message": "OpenAI API key not configured",
                "data": None
            }
            
        if not self.has_agents_sdk:
            return {
                "success": False,
                "message": "OpenAI Agents SDK not available",
                "data": None
            }
            
        try:
            # Create knowledge graph agent
            agents = get_agents_sdk()
            
            # Create tools
            web_search_tool = agents.WebSearchTool()
            knowledge_graph_tool = self._create_knowledge_graph_tool()
            
            tools = [web_search_tool, knowledge_graph_tool]
                
            # Create specialized knowledge graph agent
            agent = agents.Agent(
                name="Knowledge Graph Assistant",
                instructions=(
                    "You are a specialized knowledge graph assistant. "
                    "Your primary task is to analyze the user's request and manage knowledge graphs. "
                    "You can create, view, list, or delete knowledge graphs, as well as provide "
                    "information about knowledge graph structure and usage. "
                    "Be thorough in your analysis and knowledge graph operations. "
                    "Always explain what you're doing and why in clear terms."
                ),
                tools=tools
            )
            
            # Track progress
            if progress_callback:
                progress_callback(10, "Knowledge graph agent initialized")
                
            # Create specialized system message with task details
            system_prompt = (
                f"Task: Knowledge graph operation\n"
                f"User message: {message}\n"
                f"Options:\n"
                f"- Graph name: {graph_name if graph_name else 'Not specified'}\n"
                f"\nPlease process this knowledge graph task according to these specifications."
            )
            
            # Run the agent with progress tracking
            # Use periodic updates for progress callback
            if progress_callback:
                progress_callback(20, "Starting knowledge graph task")
                
                async def update_progress():
                    progress = 20
                    while progress < 90:
                        await asyncio.sleep(2)  # Update every 2 seconds
                        progress += 10
                        progress_callback(progress, "Processing knowledge graph task")
                
                # Start progress updates in background
                progress_task = asyncio.create_task(update_progress())
                
            # Run the agent
            result = await agents.Runner.run(agent, system_prompt)
            
            # Update progress
            if progress_callback:
                progress_callback(100, "Knowledge graph task completed")
                
            if result and hasattr(result, 'final_output'):
                return {
                    "success": True,
                    "message": "Knowledge graph task completed successfully",
                    "data": {
                        "response": result.final_output,
                        "tool_calls": [
                            {"tool": tc.tool_name, "input": tc.tool_input, "output": tc.tool_output}
                            for tc in (result.tool_calls if hasattr(result, 'tool_calls') else [])
                        ],
                        "graph_name": graph_name
                    }
                }
            else:
                return {
                    "success": False,
                    "message": "Knowledge graph agent returned invalid response",
                    "data": None
                }
                
        except Exception as e:
            logger.error(f"Error running knowledge graph agent: {e}")
            logger.error(traceback.format_exc())
            
            return {
                "success": False,
                "message": f"Error: {str(e)}",
                "data": None
            }

    async def generate_response(self, user_message: str) -> str:
        """
        Generate a chat response to the user's message.
        
        Args:
            user_message: The user's message
            
        Returns:
            str: The generated response
        """
        # If no API key, return a specific error message
        if not self.api_key:
            return "I need an OpenAI API key to respond to messages. Please set up your OpenAI API key in the Configuration page."
        
        # Check if we should use the Agents SDK
        if self.has_agents_sdk:
            return await self._generate_response_with_agents(user_message)
        else:
            # Fall back to basic API
            return await self._generate_response_with_api(user_message)

    async def _generate_response_with_agents(self, user_message: str) -> str:
        """
        Generate a response using the OpenAI Agents SDK.
        
        Args:
            user_message: The user's message
            
        Returns:
            str: The generated response
        """
        agents = get_agents_sdk()
        if not agents:
            return "OpenAI Agents SDK is not available. Falling back to basic API."
            
        try:
            # Create agent with appropriate tools
            agent = await self._create_agent(user_message)
            if not agent:
                return "Failed to initialize OpenAI Agent. Falling back to basic API."
            
            # Run the agent
            logger.info(f"Running OpenAI Agent with message: {user_message}")
            result = await agents.Runner.run(agent, user_message)
            
            if result and hasattr(result, 'final_output'):
                logger.info("Successfully generated response with OpenAI Agent")
                return result.final_output
            else:
                logger.warning("OpenAI Agent returned empty or invalid response")
                return "I apologize, but I couldn't generate a proper response. Please try again or rephrase your question."
        except Exception as e:
            logger.error(f"Error running OpenAI Agent: {e}")
            logger.error(traceback.format_exc())
            
            # Return error message
            return f"I encountered an error while processing your message with the AI Agent: {str(e)}"

    async def _generate_response_with_api(self, user_message: str) -> str:
        """
        Generate a response using the basic OpenAI API.
        
        Args:
            user_message: The user's message
            
        Returns:
            str: The generated response
        """
        try:
            # Make actual API call to OpenAI
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            data = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": user_message}
                ],
                "temperature": 0.7,
                "max_tokens": 500
            }
            
            logger.info(f"Sending request to OpenAI API with model {self.model}")
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=data,
                timeout=30
            )
            
            # Handle API response
            if response.status_code == 200:
                result = response.json()
                message_content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                if message_content:
                    logger.info("Successfully generated response from OpenAI")
                    return message_content
                else:
                    logger.warning("Empty response from OpenAI")
                    return "I received an empty response. Please try again."
            else:
                error_info = response.json().get("error", {})
                error_message = error_info.get("message", "Unknown error")
                logger.error(f"OpenAI API error: {response.status_code} - {error_message}")
                
                # Return a more specific error message for common issues
                if response.status_code == 401:
                    return "Authentication error: The OpenAI API key seems to be invalid. Please check your configuration."
                elif response.status_code == 429:
                    return "Rate limit exceeded: The OpenAI API request was rate limited. Please try again later."
                else:
                    return f"OpenAI API error: {error_message}"
                
        except requests.exceptions.Timeout:
            logger.error("Request to OpenAI API timed out")
            return "The request to the OpenAI API timed out. Please try again later."
        except requests.exceptions.ConnectionError:
            logger.error("Connection error when calling OpenAI API")
            return "Could not connect to the OpenAI API. Please check your internet connection."
        except Exception as e:
            logger.error(f"Error generating chat response: {e}")
            return f"I encountered an error while processing your message: {str(e)}"