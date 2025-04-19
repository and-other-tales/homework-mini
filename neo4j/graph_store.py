import logging
import os
from typing import List, Dict, Any, Optional, Union, Tuple
from datetime import datetime
import json
from pathlib import Path
import uuid
import hashlib

# Import core Neo4j driver
import neo4j
from neo4j import GraphDatabase

# Import LangChain libraries directly
from langchain_core.documents import Document
from langchain_aws import ChatBedrockConverse

logger = logging.getLogger(__name__)

class Node:
    """Represents a node in a graph with associated properties."""
    
    def __init__(self, id: Union[str, int], type: str = "Node", properties: dict = None):
        self.id = id
        self.type = type
        self.properties = properties or {}

class Relationship:
    """Represents a directed relationship between two nodes in a graph."""
    
    def __init__(self, source: Node, target: Node, type: str, properties: dict = None):
        self.source = source
        self.target = target 
        self.type = type
        self.properties = properties or {}

class GraphDocument:
    """Represents a graph document consisting of nodes and relationships."""
    
    def __init__(self, nodes: List[Node], relationships: List[Relationship], source: Optional[Document] = None):
        self.nodes = nodes
        self.relationships = relationships
        self.source = source


def _remove_backticks(text: str) -> str:
    """Remove backticks from text."""
    return text.replace("`", "")


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
        
        # Set graph name (database)
        self.graph_name = graph_name or "neo4j"
        
        # Initialize Neo4j connection
        self._driver = None
        if all([self.uri, self.username, self.password]):
            try:
                self._driver = GraphDatabase.driver(
                    self.uri, 
                    auth=(self.username, self.password)
                )
                logger.info(f"Connected to Neo4j graph: {self.graph_name}")
            except Exception as e:
                logger.error(f"Failed to connect to Neo4j: {e}")
                self._driver = None
        else:
            logger.warning("Neo4j credentials not configured")

    def test_connection(self) -> bool:
        """Test the connection to the Neo4j database."""
        if not self._driver:
            return False
        
        try:
            # Execute a simple query to test the connection
            result = self.query("RETURN 1 as test")
            return len(result) > 0 and result[0].get("test") == 1
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            return False
    
    def query(self, query: str, params: dict = None) -> List[Dict[str, Any]]:
        """Query Neo4j database.

        Args:
            query (str): The Cypher query to execute.
            params (dict): The parameters to pass to the query.

        Returns:
            List[Dict[str, Any]]: The list of dictionaries containing the query results.
        """
        if not self._driver:
            logger.error("Neo4j connection not available")
            return []
        
        if params is None:
            params = {}
        
        try:
            with self._driver.session(database=self.graph_name) as session:
                result = session.run(query, params)
                return [record.data() for record in result]
        except Exception as e:
            logger.error(f"Failed to execute query: {e}")
            return []

    def initialize_schema(self) -> bool:
        """Initialize the graph schema with necessary constraints and indexes."""
        if not self._driver:
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
                self.query(query)
            
            logger.info(f"Knowledge graph schema initialized for {self.graph_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize schema: {e}")
            return False
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about the knowledge graph."""
        if not self._driver:
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
            
            result = self.query(stats_query)
            
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
        if not self._driver:
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
            
            result = self.query(graphs_query)
            
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
        if not self._driver:
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
            
            result = self.query(create_query, {"description": description or f"Knowledge graph: {name}"})
            
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
        if not self._driver:
            logger.error("Neo4j connection not available")
            return False
        
        try:
            # Delete all nodes and relationships in the graph
            delete_query = f"""
            MATCH (n)
            WHERE n.graph_name = '{name}' OR n:KnowledgeGraph AND n.name = '{name}'
            DETACH DELETE n
            """
            
            self.query(delete_query)
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
        if not self._driver:
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
            
            result = self.query(create_query, params)
            
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
        if not self._driver:
            logger.error("Neo4j connection not available")
            return False
        
        try:
            # Initialize LLM with Bedrock
            llm = ChatBedrockConverse(
                model_id="anthropic.claude-3-5-sonnet-20240620-v1:0",
                region_name="us-east-1",
                temperature=0,
                max_tokens=1000
            )
            
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

            # Process each document to extract entities
            for doc in documents:
                doc_id = doc.get("id", str(uuid.uuid4()))
                doc_content = doc.get("content", "")
                doc_title = doc.get("title", "Untitled Document")
                
                # Skip empty documents
                if not doc_content:
                    continue

                # Extract entities and relationships using LLM
                prompt = f"""
                Extract entities and relationships from the following document:
                
                Title: {doc_title}
                
                Content:
                {doc_content[:4000]}  # Limit content size
                
                Return ONLY a JSON structure with no explanations:
                
                {{
                    "entities": [
                        {{
                            "id": "unique-id-1",
                            "type": "Person|Organization|Concept|...",
                            "name": "Entity name",
                            "properties": {{
                                "property1": "value1",
                                "property2": "value2"
                            }}
                        }},
                        ...
                    ],
                    "relationships": [
                        {{
                            "source_id": "unique-id-1",
                            "target_id": "unique-id-2",
                            "type": "RELATIONSHIP_TYPE",
                            "properties": {{
                                "property1": "value1",
                                "property2": "value2"
                            }}
                        }},
                        ...
                    ]
                }}
                
                Entity types must be one of: {allowed_nodes}
                """
                
                try:
                    # Call LLM to extract entities
                    response = llm.invoke(prompt)
                    extraction_text = response.content
                    
                    # Extract JSON part from the response
                    start_idx = extraction_text.find('{')
                    end_idx = extraction_text.rfind('}')
                    if start_idx != -1 and end_idx != -1:
                        json_str = extraction_text[start_idx:end_idx+1]
                        extraction = json.loads(json_str)
                    else:
                        logger.error(f"Could not extract JSON from LLM response for document {doc_id}")
                        continue
                    
                    # Create document node
                    self.add_document(doc)
                    
                    # Create entity nodes
                    for entity in extraction.get("entities", []):
                        entity_id = entity.get("id", str(uuid.uuid4()))
                        entity_type = entity.get("type")
                        
                        # Skip entities with invalid types
                        if entity_type not in allowed_nodes:
                            continue
                        
                        # Create entity node
                        create_entity_query = f"""
                        MERGE (e:{entity_type} {{id: $id}})
                        ON CREATE SET e.created_at = datetime(),
                                    e.graph_name = '{self.graph_name}',
                                    e.name = $name
                        ON MATCH SET e.updated_at = datetime(),
                                   e.name = $name
                        
                        WITH e
                        
                        MATCH (d:Document {{id: $doc_id}})
                        MERGE (d)-[:MENTIONS]->(e)
                        
                        RETURN e.id as id
                        """
                        
                        entity_params = {
                            "id": entity_id,
                            "name": entity.get("name", f"Unnamed {entity_type}"),
                            "doc_id": doc_id
                        }
                        
                        # Add properties
                        for prop_key, prop_value in entity.get("properties", {}).items():
                            entity_params[prop_key] = prop_value
                            create_entity_query = create_entity_query.replace(
                                "ON CREATE SET", f"ON CREATE SET e.{prop_key} = ${prop_key},")
                            create_entity_query = create_entity_query.replace(
                                "ON MATCH SET", f"ON MATCH SET e.{prop_key} = ${prop_key},")
                        
                        # Create entity
                        self.query(create_entity_query, entity_params)
                    
                    # Create relationships
                    for rel in extraction.get("relationships", []):
                        source_id = rel.get("source_id")
                        target_id = rel.get("target_id")
                        rel_type = rel.get("type", "RELATED_TO").upper().replace(" ", "_")
                        
                        # Skip relationships without source or target
                        if not source_id or not target_id:
                            continue
                        
                        # Create relationship
                        create_rel_query = f"""
                        MATCH (source {{id: $source_id}})
                        MATCH (target {{id: $target_id}})
                        MERGE (source)-[r:{rel_type}]->(target)
                        
                        ON CREATE SET r.created_at = datetime()
                        
                        RETURN type(r) as type
                        """
                        
                        rel_params = {
                            "source_id": source_id,
                            "target_id": target_id
                        }
                        
                        # Add properties
                        for prop_key, prop_value in rel.get("properties", {}).items():
                            rel_params[prop_key] = prop_value
                            create_rel_query = create_rel_query.replace(
                                "ON CREATE SET", f"ON CREATE SET r.{prop_key} = ${prop_key},")
                        
                        # Create relationship
                        self.query(create_rel_query, rel_params)
                    
                except Exception as e:
                    logger.error(f"Failed to extract entities from document {doc_id}: {e}")
                    continue
            
            return True
                
        except Exception as e:
            logger.error(f"Failed to extract entities: {e}")
            return False
    
    def search_documents(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Search for documents in the knowledge graph.
        
        Args:
            query: Search query
            limit: Maximum number of results to return
            
        Returns:
            List of matching documents
        """
        if not self._driver:
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
            
            result = self.query(search_query, {"query": query, "limit": limit})
            
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
        if not self._driver:
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
            
            result = self.query(query, {"id": doc_id})
            
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
        if not self._driver:
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
            
            result = self.query(query, {"id": doc_id})
            
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
        if not self._driver:
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
            
            result = self.query(query, {"concept_name": concept_name})
            
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
        if not self._driver:
            logger.error("Neo4j connection not available")
            return []
        
        try:
            # Execute query with graph_name parameter
            if params is None:
                params = {}
            
            params["graph_name"] = self.graph_name
            
            # Replace graph_name placeholder with the actual parameter
            modified_query = query.replace("{graph_name}", "{graph_name}")
            
            result = self.query(modified_query, params)
            return result
            
        except Exception as e:
            logger.error(f"Failed to execute custom query: {e}")
            return []
    
    def close(self) -> None:
        """Close the Neo4j driver connection."""
        if self._driver:
            self._driver.close()
            self._driver = None

    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    def __del__(self):
        self.close()