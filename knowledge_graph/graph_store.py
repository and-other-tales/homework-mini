import logging
import os
from typing import List, Dict, Any, Optional, Union, Tuple
from datetime import datetime
import json
from pathlib import Path
import uuid

from langchain_neo4j import Neo4jGraph
from langchain_core.documents import Document
from langchain_experimental.graph_transformers import LLMGraphTransformer
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

class GraphStore:
    """Neo4j-based knowledge graph store with support for multiple graphs."""

    def __init__(self, graph_name=None):
        """
        Initialize the graph store.
        
        Args:
            graph_name: Optional name of the graph to connect to
        """
        # Get Neo4j credentials from environment or CredentialsManager
        self.uri = os.environ.get("NEO4J_URI", None)
        self.username = os.environ.get("NEO4J_USERNAME", None)
        self.password = os.environ.get("NEO4J_PASSWORD", None)
        
        # Try to get credentials from CredentialsManager if not in environment
        if not all([self.uri, self.username, self.password]):
            try:
                from config.credentials_manager import CredentialsManager
                credentials_manager = CredentialsManager()
                neo4j_credentials = credentials_manager.get_neo4j_credentials()
                if neo4j_credentials:
                    self.uri = neo4j_credentials.get("uri", self.uri)
                    self.username = neo4j_credentials.get("username", self.username)
                    self.password = neo4j_credentials.get("password", self.password)
            except ImportError:
                logger.warning("CredentialsManager not available")
        
        # Set graph name
        self.graph_name = graph_name or "default"
        
        # Initialize Neo4j connection
        self.graph = None
        if all([self.uri, self.username, self.password]):
            try:
                self.graph = Neo4jGraph(
                    url=self.uri,
                    username=self.username,
                    password=self.password,
                    database=self.graph_name if self.graph_name != "default" else None,
                    refresh_schema=False
                )
                logger.info(f"Connected to Neo4j graph: {self.graph_name}")
            except Exception as e:
                logger.error(f"Failed to connect to Neo4j: {e}")
                self.graph = None
        else:
            logger.warning("Neo4j credentials not configured")
    
    def test_connection(self) -> bool:
        """Test the connection to the Neo4j database."""
        if not self.graph:
            return False
        
        try:
            # Execute a simple query to test the connection
            result = self.graph.query("RETURN 1 as test")
            return len(result) > 0 and result[0].get("test") == 1
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            return False
    
    def initialize_schema(self) -> bool:
        """Initialize the graph schema with necessary constraints and indexes."""
        if not self.graph:
            logger.error("Neo4j connection not available")
            return False
        
        try:
            # Create constraints for common node types
            # This ensures uniqueness and adds indexes for better performance
            schema_queries = [
                # Create constraints for documents
                "CREATE CONSTRAINT document_id IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE",
                
                # Create constraints for common entity types
                "CREATE CONSTRAINT person_id IF NOT EXISTS FOR (p:Person) REQUIRE p.id IS UNIQUE",
                "CREATE CONSTRAINT organization_id IF NOT EXISTS FOR (o:Organization) REQUIRE o.id IS UNIQUE",
                "CREATE CONSTRAINT concept_id IF NOT EXISTS FOR (c:Concept) REQUIRE c.id IS UNIQUE",
                "CREATE CONSTRAINT place_id IF NOT EXISTS FOR (p:Place) REQUIRE p.id IS UNIQUE",
                
                # Create graph metadata node if it doesn't exist
                f"""
                MERGE (g:KnowledgeGraph {{name: '{self.graph_name}'}})
                ON CREATE SET g.created_at = datetime(),
                              g.updated_at = datetime(),
                              g.description = 'Knowledge graph created by othertales homework'
                ON MATCH SET g.updated_at = datetime()
                """,
                
                # Create full-text search index for document content
                "CREATE FULLTEXT INDEX document_content IF NOT EXISTS FOR (d:Document) ON EACH [d.content]",
                
                # Create full-text search index for entity names
                "CREATE FULLTEXT INDEX entity_name IF NOT EXISTS FOR (e:Entity) ON EACH [e.name, e.id]"
            ]
            
            # Execute all schema setup queries
            for query in schema_queries:
                self.graph.query(query)
            
            logger.info(f"Knowledge graph schema initialized for {self.graph_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize schema: {e}")
            return False
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about the knowledge graph."""
        if not self.graph:
            logger.error("Neo4j connection not available")
            return {}
        
        try:
            # Query for graph statistics
            stats_query = f"""
            MATCH (g:KnowledgeGraph {{name: '{self.graph_name}'}})
            OPTIONAL MATCH (d:Document)
            WITH g, COUNT(d) as document_count
            OPTIONAL MATCH (c:Concept)
            WITH g, document_count, COUNT(c) as concept_count
            OPTIONAL MATCH (n)
            WITH g, document_count, concept_count, COUNT(n) as node_count
            OPTIONAL MATCH ()-[r]->()
            RETURN g.name as graph_name,
                   g.description as description,
                   g.created_at as created_at,
                   g.updated_at as updated_at,
                   node_count,
                   COUNT(r) as relationship_count,
                   document_count,
                   concept_count
            """
            
            result = self.graph.query(stats_query)
            
            if not result:
                return {}
                
            stats = result[0]
            
            # Format timestamps
            if "created_at" in stats and stats["created_at"]:
                stats["created_at"] = stats["created_at"].isoformat()
            if "updated_at" in stats and stats["updated_at"]:
                stats["updated_at"] = stats["updated_at"].isoformat()
                
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get graph statistics: {e}")
            return {}
    
    def list_graphs(self) -> List[Dict[str, Any]]:
        """List all available knowledge graphs."""
        if not self.graph:
            logger.error("Neo4j connection not available")
            return []
        
        try:
            # Query for all knowledge graphs
            graphs_query = """
            MATCH (g:KnowledgeGraph)
            RETURN g.name as name,
                   g.description as description,
                   g.created_at as created_at,
                   g.updated_at as updated_at
            ORDER BY g.name
            """
            
            result = self.graph.query(graphs_query)
            
            # Format timestamps
            for graph in result:
                if "created_at" in graph and graph["created_at"]:
                    graph["created_at"] = graph["created_at"].isoformat()
                if "updated_at" in graph and graph["updated_at"]:
                    graph["updated_at"] = graph["updated_at"].isoformat()
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to list graphs: {e}")
            return []
    
    def create_graph(self, name: str, description: str = None) -> bool:
        """
        Create a new knowledge graph.
        
        Args:
            name: Name of the graph to create
            description: Optional description
            
        Returns:
            bool: Whether creation was successful
        """
        if not self.graph:
            logger.error("Neo4j connection not available")
            return False
        
        try:
            # Create graph metadata node
            create_query = f"""
            MERGE (g:KnowledgeGraph {{name: '{name}'}})
            ON CREATE SET g.created_at = datetime(),
                          g.updated_at = datetime(),
                          g.description = $description
            RETURN g.name as name
            """
            
            result = self.graph.query(create_query, {"description": description or f"Knowledge graph: {name}"})
            
            if result and result[0].get("name") == name:
                logger.info(f"Created knowledge graph: {name}")
                return True
            else:
                logger.error(f"Failed to create knowledge graph: {name}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to create graph: {e}")
            return False
    
    def delete_graph(self, name: str) -> bool:
        """
        Delete a knowledge graph.
        
        Args:
            name: Name of the graph to delete
            
        Returns:
            bool: Whether deletion was successful
        """
        if not self.graph:
            logger.error("Neo4j connection not available")
            return False
        
        try:
            # Delete all nodes and relationships in the graph
            delete_query = f"""
            MATCH (n)
            WHERE n.graph_name = '{name}' OR n:KnowledgeGraph AND n.name = '{name}'
            DETACH DELETE n
            """
            
            self.graph.query(delete_query)
            logger.info(f"Deleted knowledge graph: {name}")
            return True
                
        except Exception as e:
            logger.error(f"Failed to delete graph: {e}")
            return False
    
    def add_document(self, document_data: Dict[str, Any]) -> Optional[str]:
        """
        Add a document to the knowledge graph.
        
        Args:
            document_data: Dictionary with document properties
            
        Returns:
            str: Document ID if successful, None otherwise
        """
        if not self.graph:
            logger.error("Neo4j connection not available")
            return None
        
        try:
            # Generate a unique ID if not provided
            doc_id = document_data.get("id", str(uuid.uuid4()))
            
            # Create document node
            create_query = f"""
            MERGE (d:Document {{id: $id}})
            ON CREATE SET d.created_at = datetime(),
                          d.graph_name = '{self.graph_name}',
                          d.url = $url,
                          d.title = $title,
                          d.content = $content,
                          d.description = $description,
                          d.fetched_at = $fetched_at
            ON MATCH SET d.updated_at = datetime(),
                         d.url = $url,
                         d.title = $title,
                         d.content = $content,
                         d.description = $description,
                         d.fetched_at = $fetched_at
            WITH d
            MATCH (g:KnowledgeGraph {{name: '{self.graph_name}'}})
            MERGE (g)-[:CONTAINS]->(d)
            RETURN d.id as id
            """
            
            params = {
                "id": doc_id,
                "url": document_data.get("url", ""),
                "title": document_data.get("title", "Untitled Document"),
                "content": document_data.get("content", ""),
                "description": document_data.get("description", ""),
                "fetched_at": document_data.get("fetched_at", datetime.now().isoformat())
            }
            
            result = self.graph.query(create_query, params)
            
            if result and result[0].get("id") == doc_id:
                logger.info(f"Added document to graph {self.graph_name}: {doc_id}")
                return doc_id
            else:
                logger.error(f"Failed to add document: {doc_id}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to add document: {e}")
            return None
    
    def extract_entities_from_documents(self, documents: List[Dict[str, Any]], llm_api_key: str = None) -> bool:
        """
        Extract entities and relationships from documents and add them to the graph.
        
        Args:
            documents: List of document dictionaries
            llm_api_key: Optional OpenAI API key
            
        Returns:
            bool: Whether extraction was successful
        """
        if not self.graph:
            logger.error("Neo4j connection not available")
            return False
        
        try:
            # Get OpenAI API key
            api_key = llm_api_key or os.environ.get("OPENAI_API_KEY")
            if not api_key:
                try:
                    from config.credentials_manager import CredentialsManager
                    credentials_manager = CredentialsManager()
                    api_key = credentials_manager.get_openai_key()
                except (ImportError, AttributeError):
                    pass
            
            if not api_key:
                logger.error("OpenAI API key not available")
                return False
            
            # Initialize LLM
            llm = ChatOpenAI(temperature=0, model_name="gpt-4-turbo", api_key=api_key)
            
            # Define allowed node types and relationships
            allowed_nodes = [
                "Person", 
                "Organization", 
                "Concept", 
                "Event", 
                "Location", 
                "Date", 
                "Topic",
                "Product",
                "Technology", 
                "Law", 
                "Regulation"
            ]
            
            allowed_relationships = [
                # Person relationships
                ("Person", "WORKS_FOR", "Organization"),
                ("Person", "KNOWS", "Person"),
                ("Person", "CREATED", "Concept"),
                ("Person", "PARTICIPATED_IN", "Event"),
                ("Person", "BORN_IN", "Location"),
                ("Person", "AUTHOR_OF", "Document"),
                
                # Organization relationships
                ("Organization", "LOCATED_IN", "Location"),
                ("Organization", "DEVELOPS", "Product"),
                ("Organization", "IMPLEMENTS", "Technology"),
                ("Organization", "PUBLISHES", "Document"),
                
                # Concept relationships
                ("Concept", "RELATED_TO", "Concept"),
                ("Concept", "MENTIONED_IN", "Document"),
                ("Concept", "PART_OF", "Topic"),
                
                # Legal relationships
                ("Law", "REGULATES", "Concept"),
                ("Law", "ENFORCED_BY", "Organization"),
                ("Regulation", "IMPLEMENTS", "Law"),
                
                # Generic relationships
                ("Topic", "CONTAINS", "Concept"),
                ("Document", "MENTIONS", "Concept"),
                ("Document", "DESCRIBES", "Event"),
                ("Document", "REFERENCES", "Document")
            ]
            
            # Create transformer
            llm_transformer = LLMGraphTransformer(
                llm=llm,
                allowed_nodes=allowed_nodes,
                allowed_relationships=allowed_relationships,
                node_properties=True
            )
            
            # Convert documents to LangChain format
            langchain_docs = []
            for doc in documents:
                langchain_docs.append(Document(
                    page_content=doc.get("content", ""),
                    metadata={
                        "id": doc.get("id", str(uuid.uuid4())),
                        "url": doc.get("url", ""),
                        "title": doc.get("title", "Untitled Document"),
                        "description": doc.get("description", ""),
                        "fetched_at": doc.get("fetched_at", datetime.now().isoformat())
                    }
                ))
            
            # Extract graph documents
            graph_documents = llm_transformer.convert_to_graph_documents(langchain_docs)
            
            # Add to graph
            for graph_doc in graph_documents:
                self.graph.add_graph_documents(
                    [graph_doc], 
                    baseEntityLabel=True, 
                    include_source=True
                )
                
                # Add graph name to all nodes
                self._add_graph_name_to_nodes(graph_doc)
            
            return True
                
        except Exception as e:
            logger.error(f"Failed to extract entities: {e}")
            return False
    
    def _add_graph_name_to_nodes(self, graph_doc):
        """Add graph name to all nodes to support multiple graphs."""
        try:
            # Add graph name to all nodes
            query = f"""
            MATCH (n)
            WHERE NOT n:KnowledgeGraph AND (n.graph_name IS NULL OR n.graph_name = '')
            SET n.graph_name = '{self.graph_name}'
            """
            
            self.graph.query(query)
            
        except Exception as e:
            logger.error(f"Failed to add graph name to nodes: {e}")
    
    def search_documents(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Search for documents in the knowledge graph.
        
        Args:
            query: Search query
            limit: Maximum number of results to return
            
        Returns:
            List of matching documents
        """
        if not self.graph:
            logger.error("Neo4j connection not available")
            return []
        
        try:
            # Use full-text search
            search_query = f"""
            CALL db.index.fulltext.queryNodes("document_content", $query) 
            YIELD node, score
            WHERE node.graph_name = '{self.graph_name}'
            RETURN node.id as id,
                   node.title as title,
                   node.url as url,
                   node.description as description,
                   node.fetched_at as fetched_at,
                   score
            ORDER BY score DESC
            LIMIT $limit
            """
            
            result = self.graph.query(search_query, {"query": query, "limit": limit})
            
            # Format timestamps
            for doc in result:
                if "fetched_at" in doc and doc["fetched_at"]:
                    # Convert to string if it's a datetime
                    if hasattr(doc["fetched_at"], "isoformat"):
                        doc["fetched_at"] = doc["fetched_at"].isoformat()
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to search documents: {e}")
            return []
    
    def get_document_by_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """
        Get document by ID.
        
        Args:
            doc_id: Document ID
            
        Returns:
            Document data if found, None otherwise
        """
        if not self.graph:
            logger.error("Neo4j connection not available")
            return None
        
        try:
            # Query for document
            query = f"""
            MATCH (d:Document {{id: $id, graph_name: '{self.graph_name}'}})
            RETURN d.id as id,
                   d.title as title,
                   d.url as url,
                   d.content as content,
                   d.description as description,
                   d.fetched_at as fetched_at,
                   d.created_at as created_at,
                   d.updated_at as updated_at
            """
            
            result = self.graph.query(query, {"id": doc_id})
            
            if not result:
                return None
                
            doc = result[0]
            
            # Format timestamps
            for ts_field in ["fetched_at", "created_at", "updated_at"]:
                if ts_field in doc and doc[ts_field] and hasattr(doc[ts_field], "isoformat"):
                    doc[ts_field] = doc[ts_field].isoformat()
            
            return doc
            
        except Exception as e:
            logger.error(f"Failed to get document: {e}")
            return None
    
    def get_document_entities(self, doc_id: str) -> List[Dict[str, Any]]:
        """
        Get entities related to a document.
        
        Args:
            doc_id: Document ID
            
        Returns:
            List of entities related to the document
        """
        if not self.graph:
            logger.error("Neo4j connection not available")
            return []
        
        try:
            # Query for entities related to document
            query = f"""
            MATCH (d:Document {{id: $id, graph_name: '{self.graph_name}'}})-[r]->(e)
            WHERE NOT e:Document AND NOT e:KnowledgeGraph
            RETURN e.id as id,
                   labels(e) as types,
                   e.name as name,
                   type(r) as relationship_type,
                   properties(e) as properties
            UNION
            MATCH (e)-[r]->(d:Document {{id: $id, graph_name: '{self.graph_name}'}})
            WHERE NOT e:Document AND NOT e:KnowledgeGraph
            RETURN e.id as id,
                   labels(e) as types,
                   e.name as name,
                   type(r) as relationship_type,
                   properties(e) as properties
            """
            
            result = self.graph.query(query, {"id": doc_id})
            
            # Clean up properties
            for entity in result:
                if "properties" in entity and entity["properties"]:
                    # Remove Neo4j internal properties
                    properties = entity["properties"]
                    for key in list(properties.keys()):
                        if key.startswith("_") or key in ["id", "name", "graph_name"]:
                            properties.pop(key, None)
                    entity["properties"] = properties
                
                # Use the first non-Entity type as primary type
                if "types" in entity and entity["types"]:
                    types = [t for t in entity["types"] if t != "Entity"]
                    if types:
                        entity["type"] = types[0]
                    else:
                        entity["type"] = "Entity"
                    entity.pop("types", None)
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to get document entities: {e}")
            return []
    
    def get_concept_map(self, concept_name: str, depth: int = 2) -> Dict[str, Any]:
        """
        Get a concept map for visualization.
        
        Args:
            concept_name: Name of the concept
            depth: Depth of relationships to include
            
        Returns:
            Dict with nodes and relationships
        """
        if not self.graph:
            logger.error("Neo4j connection not available")
            return {"nodes": [], "relationships": []}
        
        try:
            # Query for concept and related entities
            query = f"""
            MATCH path = (c {{name: $concept_name, graph_name: '{self.graph_name}'}})-[*1..{depth}]-(related)
            WHERE related.graph_name = '{self.graph_name}'
            WITH c, related, [rel in relationships(path) | type(rel)] AS rel_types
            RETURN c.id as source_id,
                   c.name as source_name,
                   labels(c) as source_types,
                   related.id as target_id,
                   related.name as target_name,
                   labels(related) as target_types,
                   rel_types
            """
            
            result = self.graph.query(query, {"concept_name": concept_name})
            
            # Transform results into nodes and relationships
            nodes = {}
            relationships = []
            
            for row in result:
                # Add source node
                source_id = row["source_id"]
                if source_id not in nodes:
                    nodes[source_id] = {
                        "id": source_id,
                        "name": row["source_name"],
                        "type": next((t for t in row["source_types"] if t != "Entity"), "Entity")
                    }
                
                # Add target node
                target_id = row["target_id"]
                if target_id not in nodes:
                    nodes[target_id] = {
                        "id": target_id,
                        "name": row["target_name"],
                        "type": next((t for t in row["target_types"] if t != "Entity"), "Entity")
                    }
                
                # Add relationship
                for rel_type in row["rel_types"]:
                    relationships.append({
                        "source": source_id,
                        "target": target_id,
                        "type": rel_type
                    })
            
            return {
                "nodes": list(nodes.values()),
                "relationships": relationships
            }
            
        except Exception as e:
            logger.error(f"Failed to get concept map: {e}")
            return {"nodes": [], "relationships": []}
    
    def execute_custom_query(self, query: str, params: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        Execute a custom Cypher query.
        
        Args:
            query: Cypher query
            params: Query parameters
            
        Returns:
            Query results
        """
        if not self.graph:
            logger.error("Neo4j connection not available")
            return []
        
        try:
            # Execute query with graph_name parameter
            if params is None:
                params = {}
            
            params["graph_name"] = self.graph_name
            
            # Replace graph_name placeholder with the actual parameter
            modified_query = query.replace("{graph_name}", "{graph_name}")
            
            result = self.graph.query(modified_query, params)
            return result
            
        except Exception as e:
            logger.error(f"Failed to execute custom query: {e}")
            return []