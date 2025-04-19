"""LLM client module supporting the Bedrock LangChain integration."""

import logging
import os
from typing import Dict, Any, Optional, List, Union, Callable
import uuid

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from neo4j.graph_store import GraphStore
from github.client import GitHubClient
from utils.task_tracker import TaskTracker

# Configure logging
logger = logging.getLogger(__name__)

class LLMClient:
    """LLM client using LangChain and AWS Bedrock."""

    def __init__(self, credentials_manager=None):
        """
        Initialize the LLM client.
        
        Args:
            credentials_manager: Optional credentials manager to get credentials
        """
        self.credentials_manager = credentials_manager
        self.aws_region = "us-east-1"  # Default region, can be overridden
        self.model_id = "anthropic.claude-3-5-sonnet-20240620-v1:0"  # Default model
        
        # Try to get AWS credentials
        self._setup_aws_credentials()
        
        # Initialize components
        self.task_tracker = TaskTracker()

    def _setup_aws_credentials(self):
        """Set up AWS credentials for Bedrock."""
        # Check environment first
        aws_access_key = os.environ.get("AWS_ACCESS_KEY_ID")
        aws_secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
        aws_region = os.environ.get("AWS_REGION")
        
        # If credentials manager is provided, try to get credentials from it
        if not (aws_access_key and aws_secret_key) and self.credentials_manager:
            try:
                aws_creds = self.credentials_manager.get_aws_credentials()
                if aws_creds:
                    aws_access_key = aws_creds.get("access_key")
                    aws_secret_key = aws_creds.get("secret_key")
                    aws_region = aws_creds.get("region", self.aws_region)
                    
                    # Set environment variables for AWS SDK
                    if aws_access_key and aws_secret_key:
                        os.environ["AWS_ACCESS_KEY_ID"] = aws_access_key
                        os.environ["AWS_SECRET_ACCESS_KEY"] = aws_secret_key
                        if aws_region:
                            os.environ["AWS_REGION"] = aws_region
                            self.aws_region = aws_region
                            
                    logger.info("AWS credentials loaded from credentials manager")
            except Exception as e:
                logger.error(f"Error loading AWS credentials: {e}")
        
        # If we have credentials set in environment, consider setup successful
        self.has_credentials = bool(aws_access_key and aws_secret_key)
        if self.has_credentials:
            logger.info(f"AWS credentials configured with region: {self.aws_region}")
        else:
            logger.warning("AWS credentials not configured. Bedrock integration will not work.")

    def _get_llm(self) -> Optional[BaseChatModel]:
        """
        Get the LangChain chat model for Bedrock.
        
        Returns:
            BaseChatModel: The LangChain chat model or None if initialization fails
        """
        if not self.has_credentials:
            logger.warning("Cannot initialize Bedrock LLM without AWS credentials")
            return None
            
        try:
            from langchain_aws import ChatBedrockConverse
            
            # Initialize the ChatBedrockConverse model
            model = ChatBedrockConverse(
                model_id=self.model_id,
                region_name=self.aws_region,
                temperature=0.7,
                max_tokens=2000
            )
            
            return model
        except Exception as e:
            logger.error(f"Error initializing Bedrock LLM: {e}")
            return None

    async def generate_response(self, user_message: str) -> str:
        """
        Generate a response to the user's message.
        
        Args:
            user_message: The user's message
            
        Returns:
            str: The generated response
        """
        llm = self._get_llm()
        if not llm:
            return "AWS Bedrock integration is not available. Please check your AWS credentials."
        
        try:
            messages = [
                SystemMessage(content="You are a helpful AI assistant."),
                HumanMessage(content=user_message)
            ]
            
            # Invoke the model
            response = await llm.ainvoke(messages)
            
            # Log token usage if available
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                usage = response.usage_metadata
                logger.info(f"Token usage - Input: {usage.get('input_tokens', 0)}, Output: {usage.get('output_tokens', 0)}")
            
            return response.content
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return f"I encountered an error: {str(e)}"

    async def generate_knowledge_graph(self, 
                               source_text: str, 
                               graph_name: str = None) -> Dict[str, Any]:
        """
        Generate a knowledge graph from source text.
        
        Args:
            source_text: Text to analyze
            graph_name: Optional name for the knowledge graph
            
        Returns:
            Dict: Results of the operation
        """
        if not graph_name:
            graph_name = f"graph_{uuid.uuid4().hex[:8]}"
            
        llm = self._get_llm()
        if not llm:
            return {
                "success": False,
                "message": "AWS Bedrock integration is not available. Please check your AWS credentials."
            }
            
        try:
            # Initialize Neo4j graph store
            graph_store = GraphStore(graph_name=graph_name)
            if not graph_store.test_connection():
                return {
                    "success": False,
                    "message": "Could not connect to Neo4j database. Please check your Neo4j configuration."
                }
                
            # Create the graph
            if not graph_store.create_graph(graph_name, f"Knowledge graph for text analysis"):
                return {
                    "success": False,
                    "message": "Failed to create graph in Neo4j"
                }
                
            # Initialize schema
            graph_store.initialize_schema()
            
            # Create a system prompt for entity and relationship extraction
            system_prompt = """
            Extract entities and relationships from the given text. 
            Format as a JSON object with 'entities' and 'relationships' arrays.
            Each entity should have: 'id', 'type', 'name', and 'properties'.
            Each relationship should have: 'from', 'to', 'type', and 'properties'.
            
            Example format:
            {
              "entities": [
                {"id": "1", "type": "Person", "name": "John Doe", "properties": {"age": 30}}
              ],
              "relationships": [
                {"from": "1", "to": "2", "type": "WORKS_AT", "properties": {"since": "2020"}}
              ]
            }
            """
            
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"Extract entities and relationships from this text:\n\n{source_text}")
            ]
            
            # Get the structured extraction
            response = await llm.ainvoke(messages)
            
            # Process the response (assuming it's valid JSON)
            import json
            try:
                extraction = json.loads(response.content)
                entities = extraction.get("entities", [])
                relationships = extraction.get("relationships", [])
                
                # Add entities to graph
                for entity in entities:
                    graph_store.add_entity(
                        entity_id=entity["id"],
                        entity_type=entity["type"],
                        name=entity["name"],
                        properties=entity.get("properties", {})
                    )
                
                # Add relationships
                for rel in relationships:
                    graph_store.add_relationship(
                        from_id=rel["from"],
                        to_id=rel["to"],
                        relationship_type=rel["type"],
                        properties=rel.get("properties", {})
                    )
                
                return {
                    "success": True,
                    "message": f"Created graph '{graph_name}' with {len(entities)} entities and {len(relationships)} relationships",
                    "data": {
                        "graph_name": graph_name,
                        "entity_count": len(entities),
                        "relationship_count": len(relationships)
                    }
                }
                
            except json.JSONDecodeError:
                return {
                    "success": False,
                    "message": "Failed to parse extracted entities and relationships",
                    "data": None
                }
                
        except Exception as e:
            logger.error(f"Error generating knowledge graph: {e}")
            return {
                "success": False,
                "message": f"Error: {str(e)}",
                "data": None
            }