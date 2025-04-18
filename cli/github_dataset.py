import logging
from config.credentials_manager import CredentialsManager
from github.client import GitHubClient
from huggingface.dataset_creator import DatasetCreator
from knowledge_graph.graph_store import GraphStore

logger = logging.getLogger(__name__)

def github_dataset():
    print("\n----- Create Dataset from GitHub Repository -----")
    
    try:
        # Get GitHub repository URL
        repo_url = input("Enter GitHub repository URL: ")
        if not repo_url.startswith("https://github.com/"):
            print("Invalid GitHub repository URL. Must start with 'https://github.com/'")
            return
        
        # Repository fetch options
        print("\nRepository Fetch Options:")
        print("1. Fetch default repository content")
        print("2. Use AI-guided repository fetching")
        
        fetch_option = input("Enter choice (1-2): ")
        
        # Get AI instructions if needed
        user_instructions = None
        use_ai_guidance = fetch_option == "2"
        
        if use_ai_guidance:
            print("\nWhat information / data are you looking to extract from this repository?")
            print("Provide details about file types, directories, and content you're interested in.")
            user_instructions = input("\nEnter your requirements: ")
            
            if not user_instructions:
                print("AI guidance requires a description of what to extract. Using default repository fetching instead.")
                use_ai_guidance = False
        
        # Dataset options
        print("\nDataset Options:")
        print("1. Create new dataset")
        print("2. Add to existing dataset")
        
        dataset_option = input("Enter choice (1-2): ")
        
        update_existing = False
        dataset_name = ""
        
        if dataset_option == "1":
            # Get dataset name for new dataset
            dataset_name = input("Enter new dataset name: ")
        elif dataset_option == "2":
            # Initialize dataset manager to list existing datasets
            credentials_manager = CredentialsManager()
            _, huggingface_token = credentials_manager.get_huggingface_credentials()
            if not huggingface_token:
                print("\nError: Hugging Face token not found. Please set your credentials first.")
                return
            
            dataset_manager = DatasetManager(huggingface_token=huggingface_token,
                                           credentials_manager=credentials_manager)
            
            # Fetch datasets
            print("\nFetching your datasets from Hugging Face...")
            datasets = dataset_manager.list_datasets()
            
            if not datasets:
                print("No datasets found. You need to create a new dataset.")
                dataset_name = input("Enter new dataset name: ")
            else:
                # Display datasets
                print(f"\nFound {len(datasets)} datasets:")
                for i, dataset in enumerate(datasets):
                    print(f"{i+1}. {dataset.get('id', 'Unknown')} - {dataset.get('lastModified', 'Unknown date')}")
                
                # Select dataset
                dataset_index = int(input("\nEnter dataset number to add to (0 to create new): ")) - 1
                
                if dataset_index < 0:
                    # Create new dataset
                    dataset_name = input("Enter new dataset name: ")
                elif 0 <= dataset_index < len(datasets):
                    # Use existing dataset
                    dataset_name = datasets[dataset_index].get('id')
                    update_existing = True
                    print(f"Adding to existing dataset: {dataset_name}")
                else:
                    print("Invalid dataset number")
                    return
        else:
            print("Invalid choice")
            return
        
        # Get dataset description
        description = input("Enter dataset description: ")
        
        # Knowledge graph options
        print("\nKnowledge Graph Options:")
        print("1. Don't export to knowledge graph")
        print("2. Export to default knowledge graph")
        print("3. Export to specific knowledge graph")
        
        graph_option = input("Enter choice (1-3): ")
        
        export_to_graph = True
        graph_name = None
        
        if graph_option == "1":
            export_to_graph = False
        elif graph_option == "2":
            # Use default graph
            export_to_graph = True
        elif graph_option == "3":
            # Get or create specific graph
            try:
                # Initialize graph store
                graph_store = GraphStore()
                
                # Test connection first
                if not graph_store.test_connection():
                    print("Failed to connect to Neo4j database. Check your credentials.")
                    # Ask if user wants to proceed without graph export
                    proceed = input("Proceed without exporting to knowledge graph? (y/n): ")
                    if proceed.lower() != "y":
                        return
                    export_to_graph = False
                else:
                    # List existing graphs
                    graphs = graph_store.list_graphs()
                    
                    print("\nKnowledge Graph Selection:")
                    print("1. Create new knowledge graph")
                    if graphs:
                        print("2. Use existing knowledge graph")
                        kg_select = input("Enter choice (1-2): ")
                    else:
                        print("No existing knowledge graphs found.")
                        kg_select = "1"
                    
                    if kg_select == "1":
                        # Create new graph
                        graph_name = input("Enter name for new knowledge graph: ")
                        graph_desc = input("Enter description for knowledge graph (optional): ")
                        
                        if graph_store.create_graph(graph_name, graph_desc):
                            print(f"Knowledge graph '{graph_name}' created successfully")
                            # Initialize schema
                            graph_store = GraphStore(graph_name=graph_name)
                            graph_store.initialize_schema()
                        else:
                            print(f"Failed to create knowledge graph. Proceeding without graph export.")
                            export_to_graph = False
                    elif kg_select == "2" and graphs:
                        # Select existing graph
                        print(f"\nFound {len(graphs)} knowledge graphs:")
                        for i, graph in enumerate(graphs):
                            print(f"{i+1}. {graph.get('name', 'Unknown')}")
                            print(f"   Description: {graph.get('description', 'No description')}")
                        
                        graph_index = int(input("\nEnter graph number: ")) - 1
                        
                        if 0 <= graph_index < len(graphs):
                            graph_name = graphs[graph_index].get('name')
                            print(f"Using knowledge graph: {graph_name}")
                        else:
                            print("Invalid graph number. Proceeding without graph export.")
                            export_to_graph = False
                    else:
                        print("Invalid choice. Proceeding without graph export.")
                        export_to_graph = False
            except Exception as e:
                print(f"Error configuring knowledge graph: {e}")
                print("Proceeding without graph export.")
                export_to_graph = False
        else:
            print("Invalid choice")
            return
        
        try:
            # Use relative imports to avoid conflicts with PyGithub
            import sys
            from pathlib import Path
            sys.path.insert(0, str(Path(__file__).parent))
            from github.content_fetcher import ContentFetcher
            from huggingface.dataset_creator import DatasetCreator
            
            # Get GitHub token if available
            github_token = None  # Default to using authenticated API
            
            # Initialize clients
            content_fetcher = ContentFetcher(github_token=github_token)
            
            # Get HF token
            hf_username, huggingface_token = credentials_manager.get_huggingface_credentials()
            if not huggingface_token:
                print("\nError: Hugging Face token not found. Please set your credentials first.")
                return
                
            dataset_creator = DatasetCreator(huggingface_token=huggingface_token)
            
            print(f"\nFetching GitHub repository: {repo_url}")
            
            # Display progress callback function
            def progress_callback(percent, message=None):
                if percent % 10 == 0 or percent == 100:
                    status = f"Progress: {percent:.0f}%"
                    if message:
                        status += f" - {message}"
                    print(status)
            
            # Fetch the repository content with AI guidance if requested
            print("Fetching repository metadata and files...")
            
            # Check if this is an organization URL
            import re
            is_org_url = bool(re.match(r"https?://github\.com/([^/]+)/?$", repo_url))
            if is_org_url:
                print(f"Detected GitHub organization URL: {repo_url}")
                print("Will fetch content from all repositories in the organization.")
            
            if use_ai_guidance:
                print("Using AI-guided repository fetching with your requirements...")
                content_files = content_fetcher.fetch_single_repository(
                    repo_url, 
                    progress_callback=progress_callback,
                    user_instructions=user_instructions,
                    use_ai_guidance=True
                )
            else:
                content_files = content_fetcher.fetch_single_repository(
                    repo_url, 
                    progress_callback=progress_callback
                )
            
            if not content_files:
                if is_org_url:
                    print("No content found in any repository or error occurred during fetch.")
                else:
                    print("No content found in repository or error occurred during fetch.")
                return
            
            print(f"\nCreating dataset '{dataset_name}' from {len(content_files)} files...")
            
            # Create the dataset
            result = dataset_creator.create_and_push_dataset(
                file_data_list=content_files,
                dataset_name=dataset_name,
                description=description,
                source_info=repo_url,
                progress_callback=lambda p: progress_callback(p, "Creating and uploading dataset"),
                update_existing=update_existing
            )
            
            if result[0]:  # Check success flag
                print(f"\nDataset '{dataset_name}' created successfully!")
                
                # Export to knowledge graph if requested
                if export_to_graph:
                    print("\nExporting to knowledge graph...")
                    # Here you would add code to export to graph
                    # Similar to the web crawling implementation
            else:
                print(f"\nFailed to create dataset.")
                
        except Exception as e:
            print(f"\nError creating dataset from GitHub repository: {e}")
            logging.error(f"Error in GitHub repository workflow: {e}")
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        logging.error(f"Unexpected error in GitHub repository workflow: {e}")
