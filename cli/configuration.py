import logging
from config.credentials_manager import CredentialsManager
from huggingface.dataset_manager import DatasetManager
from knowledge_graph.graph_store import GraphStore

logger = logging.getLogger(__name__)

def configuration():
    print("\n----- Configuration -----")
    print("1. Setup Wizard (Guided Configuration)")
    print("2. API Credentials")
    print("3. Server & Dataset Configuration")
    print("4. Knowledge Graph Configuration")
    print("5. Return to main menu")
    
    config_choice = input("\nEnter choice (1-5): ")
    
    if config_choice == "1":
        print("\n===== Setup Wizard =====")
        print("This wizard will guide you through setting up all necessary configurations.")
        print("Press Enter to use default values or skip optional settings.\n")
        
        try:
            print("\n--- Step 1: Hugging Face Credentials ---")
            print("Hugging Face credentials are required for dataset creation and management.")
            hf_username = input("Enter Hugging Face username: ")
            hf_token = input("Enter Hugging Face token (will not be shown): ")
            
            if hf_username and hf_token:
                credentials_manager.save_huggingface_credentials(hf_username, hf_token)
                print("✓ Hugging Face credentials saved successfully")
            else:
                print("⚠ Hugging Face credentials skipped")
            
            print("\n--- Step 2: GitHub Token (Optional) ---")
            print("GitHub token provides higher API rate limits and access to private repositories.")
            github_token = input("Enter GitHub token (optional, will not be shown): ")
            
            if github_token:
                # Save GitHub token to environment or configuration
                # This would require implementing a save_github_token method in credentials_manager
                os.environ["GITHUB_TOKEN"] = github_token
                print("✓ GitHub token set for this session")
                print("  Note: Add GITHUB_TOKEN to your environment variables for permanent configuration")
            else:
                print("⚠ GitHub token skipped")
            
            print("\n--- Step 3: OpenAI API Key (Optional) ---")
            print("OpenAI API key is used for AI-guided web crawling and repository scraping.")
            openai_key = input("Enter OpenAI API key (optional, will not be shown): ")
            
            if openai_key:
                credentials_manager.save_openai_key(openai_key)
                print("✓ OpenAI API key saved successfully")
            else:
                print("⚠ OpenAI API key skipped")
            
            print("\n--- Step 4: Neo4j Configuration (Optional) ---")
            print("Neo4j database is used for knowledge graph creation and querying.")
            configure_neo4j = input("Do you want to configure Neo4j connection? (y/n): ").lower()
            
            if configure_neo4j == 'y':
                neo4j_uri = input("Enter Neo4j URI (e.g., bolt://localhost:7687): ")
                neo4j_user = input("Enter Neo4j username: ")
                neo4j_password = input("Enter Neo4j password (will not be shown): ")
                
                if neo4j_uri and neo4j_user and neo4j_password:
                    credentials_manager.save_neo4j_credentials(neo4j_uri, neo4j_user, neo4j_password)
                    print("✓ Neo4j credentials saved successfully")
                else:
                    print("⚠ Neo4j configuration incomplete - missing required fields")
            else:
                print("⚠ Neo4j configuration skipped")
            
            print("\n--- Step 5: Server Configuration ---")
            port_input = input(f"Enter API server port (default: {credentials_manager.get_server_port()}): ")
            if port_input:
                try:
                    port = int(port_input)
                    if 1024 <= port <= 65535:
                        credentials_manager.save_server_port(port)
                        print(f"✓ Server port set to {port}")
                    else:
                        print("⚠ Invalid port number (must be between 1024-65535). Using default.")
                except ValueError:
                    print("⚠ Invalid port number. Using default.")
            else:
                print(f"✓ Using default server port: {credentials_manager.get_server_port()}")
            
            # Set temp directory
            temp_dir = input(f"Enter temporary directory path (default: {credentials_manager.get_temp_dir()}): ")
            if temp_dir:
                try:
                    path = Path(temp_dir)
                    credentials_manager.save_temp_dir(str(path.absolute()))
                    print(f"✓ Temporary directory set to {path.absolute()}")
                except Exception as e:
                    print(f"⚠ Error setting temporary directory: {e}")
            else:
                print(f"✓ Using default temporary directory: {credentials_manager.get_temp_dir()}")
            
            print("\n✓ Setup wizard complete!")
            print("You can update these settings individually from the configuration menu at any time.")
            input("\nPress Enter to continue...")
            
        except Exception as e:
            print(f"\nError during setup: {e}")
            print("Configuration wizard failed. You can configure individual settings from the menu.")
            input("\nPress Enter to continue...")
        
    elif config_choice == "2":
        print("\n--- API Credentials ---")
        print("1. Set Hugging Face Credentials")
        print("2. Set OpenAPI Key")
        print("3. Set Neo4j Graph Database Credentials")
        print("4. Set OpenAI API Key (for AI-guided crawling)")
        print("5. Return to previous menu")
        
        cred_choice = input("\nEnter choice (1-5): ")
        
        if cred_choice == "1":
            hf_username = input("Enter Hugging Face username: ")
            hf_token = input("Enter Hugging Face token (will not be shown): ")
            
            try:
                credentials_manager.save_huggingface_credentials(hf_username, hf_token)
                print("Hugging Face credentials saved successfully")
            except Exception as e:
                print(f"Error saving Hugging Face credentials: {e}")
        
        elif cred_choice == "2":
            openapi_key = input("Enter OpenAPI key (will not be shown): ")
            
            try:
                credentials_manager.save_openapi_key(openapi_key)
                print("OpenAPI key saved successfully")
            except Exception as e:
                print(f"Error saving OpenAPI key: {e}")
        
        elif cred_choice == "3":
            neo4j_uri = input("Enter Neo4j URI (e.g., bolt://localhost:7687): ")
            neo4j_user = input("Enter Neo4j username: ")
            neo4j_password = input("Enter Neo4j password (will not be shown): ")
            
            try:
                credentials_manager.save_neo4j_credentials(neo4j_uri, neo4j_user, neo4j_password)
                print("Neo4j credentials saved successfully")
            except Exception as e:
                print(f"Error saving Neo4j credentials: {e}")
                
        elif cred_choice == "4":
            openai_key = input("Enter OpenAI API key (will not be shown): ")
            
            try:
                credentials_manager.save_openai_key(openai_key)
                print("OpenAI API key saved successfully")
            except Exception as e:
                print(f"Error saving OpenAI API key: {e}")
        
        elif cred_choice == "5":
            return
        
        else:
            print("Invalid choice")
        
        # Return to configuration menu
        return configuration()
        
    elif config_choice == "3":
        print("\n--- Server & Dataset Configuration ---")
        
        # Show current settings
        server_port = credentials_manager.get_server_port()
        temp_dir = credentials_manager.get_temp_dir()
        cache_size = task_tracker.get_cache_size()
        
        print(f"1. Set API Server Port (current: {server_port})")
        print(f"2. Set Temporary Storage Location (current: {temp_dir})")
        print(f"3. Delete Cache & Temporary Files ({cache_size} MB)")
        print("4. Return to previous menu")
        
        server_choice = input("\nEnter choice (1-4): ")
        
        if server_choice == "1":
            try:
                new_port = int(input("Enter new server port (1024-65535): "))
                if 1024 <= new_port <= 65535:
                    if credentials_manager.save_server_port(new_port):
                        print(f"Server port updated to {new_port}")
                    else:
                        print("Failed to update server port")
                else:
                    print("Invalid port number. Must be between 1024 and 65535.")
            except ValueError:
                print("Invalid input. Port must be a number.")
        
        elif server_choice == "2":
            new_dir = input("Enter new temporary storage location: ")
            try:
                path = Path(new_dir)
                if credentials_manager.save_temp_dir(str(path.absolute())):
                    print(f"Temporary storage location updated to {path.absolute()}")
                else:
                    print("Failed to update temporary storage location")
            except Exception as e:
                print(f"Error updating temporary storage location: {e}")
        
        elif server_choice == "3":
            confirm = input(f"Are you sure you want to delete all cache and temporary files ({cache_size} MB)? (Y/N): ")
            if confirm.lower() == "y":
                if task_tracker.clear_cache():
                    print("Cache and temporary files deleted successfully")
                else:
                    print("Failed to delete cache and temporary files")
            else:
                print("Cache deletion cancelled")
        
        elif server_choice == "4":
            return configuration()
        
        else:
            print("Invalid choice")
    
    elif config_choice == "4":
        print("\n--- Knowledge Graph Configuration ---")
        
        print("1. Test Neo4j Connection")
        print("2. List Knowledge Graphs")
        print("3. Create New Knowledge Graph")
        print("4. View Graph Statistics")
        print("5. Delete Knowledge Graph")
        print("6. Return to previous menu")
        
        kg_choice = input("\nEnter choice (1-6): ")
        
        if kg_choice == "1":
            try:
                from knowledge_graph.graph_store import GraphStore
                
                # Initialize graph store
                graph_store = GraphStore()
                if graph_store.test_connection():
                    print("Successfully connected to Neo4j database")
                else:
                    print("Failed to connect to Neo4j database. Check your credentials.")
            except Exception as e:
                print(f"Error connecting to Neo4j: {e}")
        
        elif kg_choice == "2":
            try:
                from knowledge_graph.graph_store import GraphStore
                
                # Initialize graph store
                graph_store = GraphStore()
                
                # Check connection first
                if not graph_store.test_connection():
                    print("Failed to connect to Neo4j database. Check your credentials.")
                    return configuration()
                    
                # List graphs
                graphs = graph_store.list_graphs()
                
                if not graphs:
                    print("No knowledge graphs found.")
                    return configuration()
                    
                print(f"\nFound {len(graphs)} knowledge graphs:")
                for i, graph in enumerate(graphs):
                    print(f"{i+1}. {graph.get('name', 'Unknown')}")
                    print(f"   Description: {graph.get('description', 'No description')}")
                    print(f"   Created: {graph.get('created_at', 'Unknown')}")
                    print(f"   Updated: {graph.get('updated_at', 'Unknown')}")
                    print()
                    
            except Exception as e:
                print(f"Error listing knowledge graphs: {e}")
        
        elif kg_choice == "3":
            try:
                from knowledge_graph.graph_store import GraphStore
                
                # Initialize graph store
                graph_store = GraphStore()
                
                # Check connection first
                if not graph_store.test_connection():
                    print("Failed to connect to Neo4j database. Check your credentials.")
                    return configuration()
                
                # Get graph name and description
                graph_name = input("Enter name for the new knowledge graph: ")
                if not graph_name:
                    print("Graph name cannot be empty")
                    return configuration()
                    
                description = input("Enter description (optional): ")
                
                # Create the graph
                if graph_store.create_graph(graph_name, description):
                    print(f"Knowledge graph '{graph_name}' created successfully")
                    # Initialize schema
                    graph_store = GraphStore(graph_name=graph_name)
                    graph_store.initialize_schema()
                    print(f"Schema initialized for knowledge graph '{graph_name}'")
                else:
                    print(f"Failed to create knowledge graph '{graph_name}'")
                    
            except Exception as e:
                print(f"Error creating knowledge graph: {e}")
        
        elif kg_choice == "4":
            try:
                from knowledge_graph.graph_store import GraphStore
                
                # Get list of graphs first
                graph_store = GraphStore()
                
                # Check connection first
                if not graph_store.test_connection():
                    print("Failed to connect to Neo4j database. Check your credentials.")
                    return configuration()
                    
                # List graphs
                graphs = graph_store.list_graphs()
                
                if not graphs:
                    print("No knowledge graphs found.")
                    return configuration()
                    
                print(f"\nSelect a graph to view statistics:")
                for i, graph in enumerate(graphs):
                    print(f"{i+1}. {graph.get('name', 'Unknown')}")
                
                graph_index = int(input("\nEnter graph number (0 to cancel): ")) - 1
                
                if graph_index < 0:
                    return configuration()
                    
                if 0 <= graph_index < len(graphs):
                    selected_graph = graphs[graph_index]
                    graph_name = selected_graph.get('name')
                    
                    # Initialize graph store with selected graph
                    graph_store = GraphStore(graph_name=graph_name)
                    stats = graph_store.get_statistics()
                    
                    if stats:
                        print(f"\nStatistics for Knowledge Graph '{graph_name}':")
                        print(f"Nodes: {stats.get('node_count', 'Unknown')}")
                        print(f"Relationships: {stats.get('relationship_count', 'Unknown')}")
                        print(f"Document nodes: {stats.get('document_count', 'Unknown')}")
                        print(f"Concept nodes: {stats.get('concept_count', 'Unknown')}")
                        print(f"Created: {stats.get('created_at', 'Unknown')}")
                        print(f"Last updated: {stats.get('updated_at', 'Unknown')}")
                    else:
                        print(f"Failed to retrieve statistics for graph '{graph_name}'")
                else:
                    print("Invalid graph number")
                    
            except Exception as e:
                print(f"Error retrieving graph statistics: {e}")
        
        elif kg_choice == "5":
            try:
                from knowledge_graph.graph_store import GraphStore
                
                # Get list of graphs first
                graph_store = GraphStore()
                
                # Check connection first
                if not graph_store.test_connection():
                    print("Failed to connect to Neo4j database. Check your credentials.")
                    return configuration()
                    
                # List graphs
                graphs = graph_store.list_graphs()
                
                if not graphs:
                    print("No knowledge graphs found.")
                    return configuration()
                    
                print(f"\nSelect a graph to delete:")
                for i, graph in enumerate(graphs):
                    print(f"{i+1}. {graph.get('name', 'Unknown')} - {graph.get('description', 'No description')}")
                
                graph_index = int(input("\nEnter graph number (0 to cancel): ")) - 1
                
                if graph_index < 0:
                    return configuration()
                    
                if 0 <= graph_index < len(graphs):
                    selected_graph = graphs[graph_index]
                    graph_name = selected_graph.get('name')
                    
                    # Confirm deletion
                    confirm = input(f"Are you sure you want to delete knowledge graph '{graph_name}'? (yes/no): ")
                    if confirm.lower() != "yes":
                        print("Deletion cancelled")
                        return configuration()
                        
                    # Delete the graph
                    if graph_store.delete_graph(graph_name):
                        print(f"Knowledge graph '{graph_name}' deleted successfully")
                    else:
                        print(f"Failed to delete knowledge graph '{graph_name}'")
                else:
                    print("Invalid graph number")
                    
            except Exception as e:
                print(f"Error deleting knowledge graph: {e}")
        
        elif kg_choice == "6":
            return configuration()
        
        else:
            print("Invalid choice")
    
    elif config_choice == "5":
        return
    
    else:
        print("Invalid choice")
