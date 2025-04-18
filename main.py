import sys
import os
import logging
import argparse
import signal
import traceback
import time
from pathlib import Path
from utils.logging_config import setup_logging
from config.credentials_manager import CredentialsManager
from huggingface.dataset_manager import DatasetManager
from utils.task_tracker import TaskTracker
from utils.task_scheduler import TaskScheduler
from api.server import start_server, stop_server, is_server_running, get_server_info, start_server_with_ui
from threading import Event, current_thread

# Global cancellation event for stopping ongoing tasks
global_cancellation_event = Event()

# Global logger
logger = logging.getLogger(__name__)


def run_cli():
    """Run the command-line interface."""
    from huggingface.dataset_manager import DatasetManager
    
    print("\n===== othertales homework =====")
    print("CLI mode\n")
    print("Press Ctrl+C at any time to safely exit the application")
    
    # Initialize managers and clients
    credentials_manager = CredentialsManager()
    _, huggingface_token = credentials_manager.get_huggingface_credentials()
    dataset_manager = DatasetManager(huggingface_token=huggingface_token, credentials_manager=credentials_manager) if huggingface_token else None
    task_tracker = TaskTracker()
    web_crawler = None
    dataset_creator = None
    
    print("Initialization successful")
    
    # Reset cancellation event at the start
    global_cancellation_event.clear()
    
    while not global_cancellation_event.is_set() and not getattr(current_thread(), 'exit_requested', False):
        # Show dynamic menu based on server status and available resumable tasks
        server_running = is_server_running()
        resumable_tasks = task_tracker.list_resumable_tasks()
        
        print("\nMain Menu:")
        if server_running:
            print("1. Stop OpenAPI Endpoints")
        else:
            print("1. Start OpenAPI Endpoints")
        print("2. Scrape & Crawl")
        print("3. Create Dataset from GitHub Repository")
        print("4. Manage Existing Datasets")
        
        # Only show Resume Dataset Creation if there are resumable tasks
        if resumable_tasks:
            print("5. Resume Scraping Task")
            print("6. Scheduled Tasks & Automation")
            print("7. Launch Web UI")
            print("8. Configuration")
            print("9. Exit")
            print("10. Run AI Assistant (full functionality)")
            max_choice = 10
        else:
            print("5. Scheduled Tasks & Automation")
            print("6. Launch Web UI")
            print("7. Configuration")
            print("8. Exit")
            print("9. Run AI Assistant (full functionality)")
            max_choice = 9
        
        choice = input(f"\nEnter your choice (1-{max_choice}): ")
        
        if choice == "1":
            # Handle OpenAPI server
            if server_running:
                print("\n----- Stopping OpenAPI Endpoints -----")
                if stop_server():
                    print("OpenAPI Endpoints stopped successfully")
                else:
                    print("Failed to stop OpenAPI Endpoints")
            else:
                print("\n----- Starting OpenAPI Endpoints -----")
                # Get OpenAPI key
                api_key = credentials_manager.get_openapi_key()
                
                if not api_key:
                    print("OpenAPI key not configured. Please set an API key.")
                    api_key = input("Enter new OpenAPI key: ")
                    if credentials_manager.save_openapi_key(api_key):
                        print("OpenAPI key saved successfully")
                    else:
                        print("Failed to save OpenAPI key")
                        continue
                
                # Get configured server port
                server_port = credentials_manager.get_server_port()
                
                if start_server(api_key, port=server_port):
                    print("OpenAPI Endpoints started successfully")
                    print(f"Server running at: http://0.0.0.0:{server_port}")
                    print(f"API Documentation: http://0.0.0.0:{server_port}/docs")
                    print(f"OpenAPI Schema: http://0.0.0.0:{server_port}/openapi.json")
                else:
                    print("Failed to start OpenAPI Endpoints")
        
        elif choice == "2":
            print("\n----- Scrape & Crawl -----")
            
            # Get initial URL
            initial_url = input("Enter the URL to scrape: ")
            
            # Scrape options
            print("\nScrape Options:")
            print("1. Scrape just this URL")
            print("2. Recursively scrape the URL and all linked pages")
            print("3. Use AI-guided crawling (with detailed instructions)")
            
            scrape_option = input("Enter choice (1-3): ")
            
            if scrape_option not in ["1", "2", "3"]:
                print("Invalid choice")
                continue
                
            # Get AI instructions if needed
            user_instructions = None
            use_ai_guidance = scrape_option == "3"
            
            if use_ai_guidance:
                print("\nWhat information / data are you looking to scrape?")
                print("You could give an overview of your intended end-use for better results.")
                user_instructions = input("\nEnter your requirements: ")
                
                if not user_instructions:
                    print("AI guidance requires a description of what to scrape. Using standard recursive crawling instead.")
                    use_ai_guidance = False
                    scrape_option = "2"  # Default to recursive crawling
                
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
                from huggingface.dataset_manager import DatasetManager
                
                # Get credentials
                _, huggingface_token = credentials_manager.get_huggingface_credentials()
                if not huggingface_token:
                    print("\nError: Hugging Face token not found. Please set your credentials first.")
                    continue
                
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
                        continue
            else:
                print("Invalid choice")
                continue
            
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
                    from knowledge_graph.graph_store import GraphStore
                    
                    # Initialize graph store
                    graph_store = GraphStore()
                    
                    # Test connection first
                    if not graph_store.test_connection():
                        print("Failed to connect to Neo4j database. Check your credentials.")
                        # Ask if user wants to proceed without graph export
                        proceed = input("Proceed without exporting to knowledge graph? (y/n): ")
                        if proceed.lower() != "y":
                            continue
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
                continue
            
            try:
                from web.crawler import WebCrawler
                from huggingface.dataset_creator import DatasetCreator
                
                # Initialize clients
                if web_crawler is None:
                    web_crawler = WebCrawler()
                
                if dataset_creator is None:
                    hf_username, huggingface_token = credentials_manager.get_huggingface_credentials()
                    if not huggingface_token:
                        print("\nError: Hugging Face token not found. Please set your credentials first.")
                        continue
                    dataset_creator = DatasetCreator(huggingface_token=huggingface_token)
                
                print(f"\nStarting scrape of: {initial_url}")
                
                # Display progress callback function
                def progress_callback(percent, message=None):
                    if percent % 10 == 0 or percent == 100:
                        status = f"Progress: {percent:.0f}%"
                        if message:
                            status += f" - {message}"
                        print(status)
                
                # Determine if recursive scraping
                recursive = scrape_option == "2" or scrape_option == "3"
                
                # Start crawling and create dataset
                result = dataset_creator.create_dataset_from_url(
                    url=initial_url,
                    dataset_name=dataset_name,
                    description=description,
                    recursive=recursive,
                    progress_callback=progress_callback,
                    update_existing=update_existing,
                    export_to_knowledge_graph=export_to_graph,
                    graph_name=graph_name,
                    user_instructions=user_instructions,
                    use_ai_guidance=use_ai_guidance
                )
                
                if result.get("success"):
                    print(f"\nDataset '{dataset_name}' created successfully")
                else:
                    print(f"\nFailed to create dataset: {result.get('message', 'Unknown error')}")
                    
            except Exception as e:
                print(f"\nError creating dataset: {e}")
                logging.error(f"Error in scrape and crawl: {e}")
                
        elif choice == "3":
            print("\n----- Create Dataset from GitHub Repository -----")
            
            try:
                # Get GitHub repository URL
                repo_url = input("Enter GitHub repository URL: ")
                if not repo_url.startswith("https://github.com/"):
                    print("Invalid GitHub repository URL. Must start with 'https://github.com/'")
                    continue
                
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
                    from huggingface.dataset_manager import DatasetManager
                    
                    # Get credentials
                    _, huggingface_token = credentials_manager.get_huggingface_credentials()
                    if not huggingface_token:
                        print("\nError: Hugging Face token not found. Please set your credentials first.")
                        continue
                    
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
                            continue
                else:
                    print("Invalid choice")
                    continue
                
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
                        from knowledge_graph.graph_store import GraphStore
                        
                        # Initialize graph store
                        graph_store = GraphStore()
                        
                        # Test connection first
                        if not graph_store.test_connection():
                            print("Failed to connect to Neo4j database. Check your credentials.")
                            # Ask if user wants to proceed without graph export
                            proceed = input("Proceed without exporting to knowledge graph? (y/n): ")
                            if proceed.lower() != "y":
                                continue
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
                    continue
                
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
                        continue
                        
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
                        continue
                    
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
        
        elif choice == "4":
            print("\n----- Manage Datasets -----")
            
            try:
                _, huggingface_token = credentials_manager.get_huggingface_credentials()
                
                if not huggingface_token:
                    print("\nError: Hugging Face token not found. Please set your credentials first.")
                    continue
                
                # Initialize dataset manager if needed
                if dataset_manager is None:
                    if not huggingface_token:
                        print("\nError: Hugging Face token not found. Please set your credentials first.")
                        continue
                        
                    from huggingface.dataset_manager import DatasetManager
                    dataset_manager = DatasetManager(huggingface_token=huggingface_token,
                                                   credentials_manager=credentials_manager)
                
                print("\nFetching your datasets from Hugging Face...")
                datasets = dataset_manager.list_datasets()
                
                if not datasets:
                    print("No datasets found for your account.")
                    continue
                
                # Display datasets and options
                print(f"\nFound {len(datasets)} datasets:")
                for i, dataset in enumerate(datasets):
                    print(f"{i+1}. {dataset.get('id', 'Unknown')} - {dataset.get('lastModified', 'Unknown date')}")
                
                print("\nOptions:")
                print("1. View dataset details")
                print("2. Download dataset metadata")
                print("3. Delete a dataset")
                print("4. Return to main menu")
                
                manage_choice = input("\nEnter choice (1-4): ")
                
                if manage_choice == "1":
                    dataset_index = int(input("Enter dataset number to view: ")) - 1
                    
                    if 0 <= dataset_index < len(datasets):
                        dataset_id = datasets[dataset_index].get('id')
                        info = dataset_manager.get_dataset_info(dataset_id)
                        
                        if info:
                            print(f"\n----- Dataset: {info.id} -----")
                            print(f"Description: {info.description}")
                            print(f"Created: {info.created_at}")
                            print(f"Last modified: {info.last_modified}")
                            print(f"Downloads: {info.downloads}")
                            print(f"Likes: {info.likes}")
                            print(f"Tags: {', '.join(info.tags) if info.tags else 'None'}")
                        else:
                            print(f"Error retrieving details for dataset {dataset_id}")
                    else:
                        print("Invalid dataset number")
                
                elif manage_choice == "2":
                    dataset_index = int(input("Enter dataset number to download metadata: ")) - 1
                    
                    if 0 <= dataset_index < len(datasets):
                        dataset_id = datasets[dataset_index].get('id')
                        success = dataset_manager.download_dataset_metadata(dataset_id)
                        
                        if success:
                            print(f"\nMetadata for dataset '{dataset_id}' downloaded successfully")
                            print(f"Saved to ./dataset_metadata/{dataset_id}/")
                        else:
                            print(f"Error downloading metadata for dataset {dataset_id}")
                    else:
                        print("Invalid dataset number")
                
                elif manage_choice == "3":
                    dataset_index = int(input("Enter dataset number to delete: ")) - 1
                    
                    if 0 <= dataset_index < len(datasets):
                        dataset_id = datasets[dataset_index].get('id')
                        
                        confirm = input(f"Are you sure you want to delete dataset '{dataset_id}'? (yes/no): ")
                        if confirm.lower() == "yes":
                            success = dataset_manager.delete_dataset(dataset_id)
                            
                            if success:
                                print(f"\nDataset '{dataset_id}' deleted successfully")
                            else:
                                print(f"Error deleting dataset {dataset_id}")
                        else:
                            print("Deletion cancelled")
                    else:
                        print("Invalid dataset number")
                
                elif manage_choice == "4":
                    continue
                
                else:
                    print("Invalid choice")
                
            except Exception as e:
                print(f"\nError managing datasets: {e}")
                logging.error(f"Error in manage datasets: {e}")
                
        # Resume Scraping Task (only available if there are resumable tasks)
        elif choice == "5" and resumable_tasks:
            print("\n----- Resume Scraping Task -----")
            
            try:
                # Display resumable tasks
                print("\nAvailable tasks to resume:")
                for i, task in enumerate(resumable_tasks):
                    # Format task description nicely
                    task_desc = task.get("description", "Unknown task")
                    progress = task.get("progress", 0)
                    updated = task.get("updated_ago", "unknown time")
                    
                    print(f"{i+1}. {task_desc} ({progress:.0f}% complete, updated {updated})")
                
                # Get task selection
                task_index = int(input("\nEnter task number to resume (0 to cancel): ")) - 1
                
                if task_index < 0:
                    print("Resumption cancelled")
                    continue
                    
                if 0 <= task_index < len(resumable_tasks):
                    selected_task = resumable_tasks[task_index]
                    task_id = selected_task["id"]
                    task_type = selected_task["type"]
                    task_params = selected_task["params"]
                    
                    # Confirm resumption
                    confirm = input(f"Resume task: {selected_task['description']}? (yes/no): ")
                    if confirm.lower() != "yes":
                        print("Resumption cancelled")
                        continue
                    
                    print(f"\nResuming task {task_id}...")
                    
                    # Create cancellation event
                    cancellation_event = Event()
                    
                    # Handle different task types
                    if task_type == "scrape":
                        # Initialize required components
                        from web.crawler import WebCrawler
                        from huggingface.dataset_creator import DatasetCreator
                        
                        # Initialize clients if needed
                        hf_username, huggingface_token = credentials_manager.get_huggingface_credentials()
                        if not huggingface_token:
                            print("\nError: Hugging Face token not found. Please set your credentials first.")
                            continue
                            
                        web_crawler = WebCrawler()
                        dataset_creator = DatasetCreator(huggingface_token=huggingface_token)
                        
                        # Progress callback function
                        def progress_callback(percent, message=None):
                            if percent % 10 == 0 or percent == 100:
                                status = f"Progress: {percent:.0f}%"
                                if message:
                                    status += f" - {message}"
                                print(status)
                        
                        # Resume repository task
                        url = task_params.get("url")
                        dataset_name = task_params.get("dataset_name")
                        description = task_params.get("description")
                        recursive = task_params.get("recursive", False)
                        
                        print(f"Resuming dataset creation from URL: {url}")
                        
                        result = dataset_creator.create_dataset_from_url(
                            url=url,
                            dataset_name=dataset_name,
                            description=description,
                            recursive=recursive,
                            progress_callback=progress_callback,
                            _cancellation_event=cancellation_event,
                            task_id=task_id,
                            resume_from=selected_task.get("current_stage")
                        )
                        
                        if result.get("success"):
                            print(f"\nDataset '{dataset_name}' creation resumed and completed successfully")
                        else:
                            print(f"\nFailed to resume dataset creation: {result.get('message', 'Unknown error')}")
                    
                    # Handle other task types when implemented
                    else:
                        print(f"Unsupported task type: {task_type}")
                        
                else:
                    print("Invalid task number")
                
            except Exception as e:
                print(f"\nError resuming task: {e}")
                logging.error(f"Error resuming task: {e}")
        
        # Scheduled Tasks menu (position depends on whether Resume Dataset Creation is available)
        elif (choice == "5" and not resumable_tasks) or (choice == "6" and resumable_tasks):
            print("\n----- Scheduled Tasks & Automation -----")
            
            try:
                # Initialize task scheduler
                task_scheduler = TaskScheduler()
                
                # Check if crontab is available
                if not task_scheduler.is_crontab_available():
                    print("Error: Crontab is not available on this system.")
                    print("Scheduled tasks require crontab to be installed and accessible.")
                    continue
                
                # Show scheduled tasks submenu
                print("\nScheduled Tasks Options:")
                print("1. List Scheduled Tasks")
                print("2. Add New Scheduled Task")
                print("3. Edit Scheduled Task")
                print("4. Delete Scheduled Task")
                print("5. Run Scheduled Task Now")
                print("6. Return to Main Menu")
                
                sched_choice = input("\nEnter choice (1-6): ")
                
                if sched_choice == "1":
                    # List scheduled tasks
                    tasks = task_scheduler.list_scheduled_tasks()
                    
                    if not tasks:
                        print("\nNo scheduled tasks found.")
                        continue
                    
                    print(f"\nFound {len(tasks)} scheduled tasks:")
                    for i, task in enumerate(tasks):
                        dataset = task.get("dataset_name", "Unknown")
                        schedule = task.get("schedule_description", "Unknown schedule")
                        next_run = task.get("next_run", "Unknown")
                        source = task.get("source_name", "Unknown")
                        source_type = task.get("source_type", "Unknown")
                        
                        print(f"{i+1}. {dataset} - {source_type}: {source}")
                        print(f"   Schedule: {schedule}")
                        print(f"   Next run: {next_run}")
                        print()
                
                elif sched_choice == "2":
                    # Add new scheduled task
                    print("\n--- Add New Scheduled Task ---")
                    
                    # Get URL and dataset info
                    url = input("Enter website URL to scrape: ")
                    
                    # Get scrape type
                    print("\nScrape Type:")
                    print("1. Scrape just this URL")
                    print("2. Recursively scrape the URL and all linked pages")
                    source_type_choice = input("Enter choice (1-2): ")
                    
                    if source_type_choice == "1":
                        source_type = "url"
                        recursive = False
                    elif source_type_choice == "2":
                        source_type = "recursive_url"
                        recursive = True
                    else:
                        print("Invalid choice")
                        continue
                    
                    # Get dataset name
                    dataset_name = input("Enter dataset name to update: ")
                    if not dataset_name:
                        print("Dataset name cannot be empty")
                        continue
                    
                    # Get schedule type
                    print("\nSchedule Type:")
                    print("1. Daily (midnight)")
                    print("2. Weekly (Sunday midnight)")
                    print("3. Bi-weekly (1st and 15th of month)")
                    print("4. Monthly (1st of month)")
                    print("5. Custom schedule")
                    schedule_choice = input("Enter choice (1-5): ")
                    
                    schedule_type = None
                    custom_params = {}
                    
                    if schedule_choice == "1":
                        schedule_type = "daily"
                    elif schedule_choice == "2":
                        schedule_type = "weekly"
                    elif schedule_choice == "3":
                        schedule_type = "biweekly"
                    elif schedule_choice == "4":
                        schedule_type = "monthly"
                    elif schedule_choice == "5":
                        schedule_type = "custom"
                        print("\nEnter custom schedule (cron format):")
                        custom_params["minute"] = input("Minute (0-59): ")
                        custom_params["hour"] = input("Hour (0-23): ")
                        custom_params["day"] = input("Day of month (1-31, * for all): ")
                        custom_params["month"] = input("Month (1-12, * for all): ")
                        custom_params["day_of_week"] = input("Day of week (0-6, 0=Sunday, * for all): ")
                    else:
                        print("Invalid choice")
                        continue
                    
                    # Create the scheduled task
                    task_id = task_scheduler.create_scheduled_task(
                        task_type="update",
                        source_type=source_type,
                        source_name=url,
                        dataset_name=dataset_name,
                        schedule_type=schedule_type,
                        recursive=recursive,
                        **custom_params
                    )
                    
                    if task_id:
                        print(f"\nScheduled task created successfully (ID: {task_id})")
                    else:
                        print("\nFailed to create scheduled task")
                
                elif sched_choice == "3":
                    # Edit scheduled task
                    tasks = task_scheduler.list_scheduled_tasks()
                    
                    if not tasks:
                        print("\nNo scheduled tasks found.")
                        continue
                    
                    print(f"\nSelect a task to edit:")
                    for i, task in enumerate(tasks):
                        dataset = task.get("dataset_name", "Unknown")
                        schedule = task.get("schedule_description", "Unknown schedule")
                        source = task.get("source_name", "Unknown")
                        
                        print(f"{i+1}. {dataset} - {source} ({schedule})")
                    
                    task_index = int(input("\nEnter task number (0 to cancel): ")) - 1
                    
                    if task_index < 0:
                        print("Edit cancelled")
                        continue
                        
                    if 0 <= task_index < len(tasks):
                        selected_task = tasks[task_index]
                        task_id = selected_task["id"]
                        
                        # Get new schedule type
                        print("\nSelect new schedule type:")
                        print("1. Daily (midnight)")
                        print("2. Weekly (Sunday midnight)")
                        print("3. Bi-weekly (1st and 15th of month)")
                        print("4. Monthly (1st of month)")
                        print("5. Custom schedule")
                        schedule_choice = input("Enter choice (1-5): ")
                        
                        schedule_type = None
                        custom_params = {}
                        
                        if schedule_choice == "1":
                            schedule_type = "daily"
                        elif schedule_choice == "2":
                            schedule_type = "weekly"
                        elif schedule_choice == "3":
                            schedule_type = "biweekly"
                        elif schedule_choice == "4":
                            schedule_type = "monthly"
                        elif schedule_choice == "5":
                            schedule_type = "custom"
                            print("\nEnter custom schedule (cron format):")
                            custom_params["minute"] = input("Minute (0-59): ")
                            custom_params["hour"] = input("Hour (0-23): ")
                            custom_params["day"] = input("Day of month (1-31, * for all): ")
                            custom_params["month"] = input("Month (1-12, * for all): ")
                            custom_params["day_of_week"] = input("Day of week (0-6, 0=Sunday, * for all): ")
                        else:
                            print("Invalid choice")
                            continue
                        
                        # Update the scheduled task
                        if task_scheduler.update_scheduled_task(task_id, schedule_type, **custom_params):
                            print(f"\nScheduled task updated successfully")
                        else:
                            print("\nFailed to update scheduled task")
                    else:
                        print("Invalid task number")
                
                elif sched_choice == "4":
                    # Delete scheduled task
                    tasks = task_scheduler.list_scheduled_tasks()
                    
                    if not tasks:
                        print("\nNo scheduled tasks found.")
                        continue
                    
                    print(f"\nSelect a task to delete:")
                    for i, task in enumerate(tasks):
                        dataset = task.get("dataset_name", "Unknown")
                        schedule = task.get("schedule_description", "Unknown schedule")
                        source = task.get("source_name", "Unknown")
                        
                        print(f"{i+1}. {dataset} - {source} ({schedule})")
                    
                    task_index = int(input("\nEnter task number (0 to cancel): ")) - 1
                    
                    if task_index < 0:
                        print("Deletion cancelled")
                        continue
                        
                    if 0 <= task_index < len(tasks):
                        selected_task = tasks[task_index]
                        task_id = selected_task["id"]
                        
                        # Confirm deletion
                        confirm = input(f"Are you sure you want to delete this scheduled task? (yes/no): ")
                        if confirm.lower() != "yes":
                            print("Deletion cancelled")
                            continue
                        
                        # Delete the scheduled task
                        if task_scheduler.delete_scheduled_task(task_id):
                            print(f"\nScheduled task deleted successfully")
                        else:
                            print("\nFailed to delete scheduled task")
                    else:
                        print("Invalid task number")
                
                elif sched_choice == "5":
                    # Run scheduled task now
                    tasks = task_scheduler.list_scheduled_tasks()
                    
                    if not tasks:
                        print("\nNo scheduled tasks found.")
                        continue
                    
                    print(f"\nSelect a task to run now:")
                    for i, task in enumerate(tasks):
                        dataset = task.get("dataset_name", "Unknown")
                        source = task.get("source_name", "Unknown")
                        source_type = task.get("source_type", "Unknown")
                        
                        print(f"{i+1}. {dataset} - {source_type}: {source}")
                    
                    task_index = int(input("\nEnter task number (0 to cancel): ")) - 1
                    
                    if task_index < 0:
                        print("Run cancelled")
                        continue
                        
                    if 0 <= task_index < len(tasks):
                        selected_task = tasks[task_index]
                        task_id = selected_task["id"]
                        
                        print(f"\nRunning task in the background. Check logs for progress.")
                        if task_scheduler.run_task_now(task_id):
                            print(f"Task started successfully")
                        else:
                            print(f"Failed to start task")
                    else:
                        print("Invalid task number")
                
                elif sched_choice == "6":
                    continue
                
                else:
                    print("Invalid choice")
                
            except Exception as e:
                print(f"\nError managing scheduled tasks: {e}")
                logging.error(f"Error in scheduled tasks menu: {e}")
        
        # Web UI menu (position depends on whether Resume Dataset Creation is available)
        elif (choice == "6" and not resumable_tasks) or (choice == "7" and resumable_tasks):
            print("\n----- Launch Web UI -----")
            
            # Check if server is already running
            if is_server_running():
                server_info = get_server_info()
                print(f"Server is already running.")
                
                # Ask if user wants to re-launch with web UI
                relaunch = input("Do you want to stop the current server and relaunch with web UI? (y/n): ")
                if relaunch.lower() == 'y':
                    print("Stopping current server...")
                    stop_server()
                    
                    # Choose HTTP or HTTPS
                    print("\nConnection Security:")
                    print("1. HTTP (standard, no security)")
                    print("2. HTTPS with self-signed certificates")
                    
                    security_choice = input("Enter choice (1-2): ")
                    use_https = security_choice == "2"
                    
                    if use_https:
                        # Ask about certificate generation
                        print("\nCertificate Options:")
                        print("1. Generate new self-signed certificates")
                        print("2. Use existing certificates")
                        
                        cert_choice = input("Enter choice (1-2): ")
                        generate_cert = cert_choice == "1"
                        
                        cert_file = None
                        key_file = None
                        
                        # If using existing certificates, get file paths
                        if not generate_cert:
                            cert_file = input("Enter path to certificate file: ")
                            key_file = input("Enter path to key file: ")
                    else:
                        # HTTP mode
                        use_https = False
                        generate_cert = False
                        cert_file = None
                        key_file = None
                    
                    # Launch web UI with selected options
                    if run_web_ui(
                        use_https=use_https,
                        cert_file=cert_file,
                        key_file=key_file,
                        generate_cert=generate_cert
                    ):
                        # Return to menu
                        continue
                    else:
                        print("Failed to start web UI")
                else:
                    print("Continuing with current server")
            else:
                # Choose HTTP or HTTPS
                print("\nConnection Security:")
                print("1. HTTP (standard, no security)")
                print("2. HTTPS with self-signed certificates")
                
                security_choice = input("Enter choice (1-2): ")
                use_https = security_choice == "2"
                
                if use_https:
                    # Ask about certificate generation
                    print("\nCertificate Options:")
                    print("1. Generate new self-signed certificates")
                    print("2. Use existing certificates")
                    
                    cert_choice = input("Enter choice (1-2): ")
                    generate_cert = cert_choice == "1"
                    
                    cert_file = None
                    key_file = None
                    
                    # If using existing certificates, get file paths
                    if not generate_cert:
                        cert_file = input("Enter path to certificate file: ")
                        key_file = input("Enter path to key file: ")
                else:
                    # HTTP mode
                    use_https = False
                    generate_cert = False
                    cert_file = None
                    key_file = None
                
                # Launch web UI with selected options
                if run_web_ui(
                    use_https=use_https,
                    cert_file=cert_file,
                    key_file=key_file,
                    generate_cert=generate_cert
                ):
                    # Ask if user wants to continue in CLI mode
                    cli_continue = input("\nWeb UI is now running. Do you want to continue in CLI mode? (y/n): ")
                    if cli_continue.lower() != 'y':
                        print("Exiting CLI mode. The web UI will continue running in the background.")
                        break
                else:
                    print("Failed to start web UI")
        
        # Configuration menu (position depends on whether Resume Dataset Creation is available)
        elif (choice == "7" and not resumable_tasks) or (choice == "8" and resumable_tasks):
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
                    continue
                    
                else:
                    print("Invalid choice")
                    
                # Return to configuration menu
                continue
                
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
                    continue
                
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
                            continue
                            
                        # List graphs
                        graphs = graph_store.list_graphs()
                        
                        if not graphs:
                            print("No knowledge graphs found.")
                            continue
                            
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
                            continue
                        
                        # Get graph name and description
                        graph_name = input("Enter name for the new knowledge graph: ")
                        if not graph_name:
                            print("Graph name cannot be empty")
                            continue
                            
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
                            continue
                            
                        # List graphs
                        graphs = graph_store.list_graphs()
                        
                        if not graphs:
                            print("No knowledge graphs found.")
                            continue
                            
                        print(f"\nSelect a graph to view statistics:")
                        for i, graph in enumerate(graphs):
                            print(f"{i+1}. {graph.get('name', 'Unknown')}")
                        
                        graph_index = int(input("\nEnter graph number (0 to cancel): ")) - 1
                        
                        if graph_index < 0:
                            continue
                            
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
                            continue
                            
                        # List graphs
                        graphs = graph_store.list_graphs()
                        
                        if not graphs:
                            print("No knowledge graphs found.")
                            continue
                            
                        print(f"\nSelect a graph to delete:")
                        for i, graph in enumerate(graphs):
                            print(f"{i+1}. {graph.get('name', 'Unknown')} - {graph.get('description', 'No description')}")
                        
                        graph_index = int(input("\nEnter graph number (0 to cancel): ")) - 1
                        
                        if graph_index < 0:
                            continue
                            
                        if 0 <= graph_index < len(graphs):
                            selected_graph = graphs[graph_index]
                            graph_name = selected_graph.get('name')
                            
                            # Confirm deletion
                            confirm = input(f"Are you sure you want to delete knowledge graph '{graph_name}'? (yes/no): ")
                            if confirm.lower() != "yes":
                                print("Deletion cancelled")
                                continue
                                
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
                    continue
                
                else:
                    print("Invalid choice")
            
            elif config_choice == "5":
                continue
                
            else:
                print("Invalid choice")
                
        # Run AI Assistant (position depends on whether Resume Dataset Creation is available)
        elif (choice == "9" and not resumable_tasks) or (choice == "10" and resumable_tasks):
            print("\nStarting AI Assistant...")
            from ai.assistant import run_full_ai_assistant
            run_full_ai_assistant()
        
        # Exit application (position depends on whether Resume Dataset Creation is available)
        elif (choice == "8" and not resumable_tasks) or (choice == "9" and resumable_tasks):
            # Check if the server is running before exiting
            if is_server_running():
                print("\nStopping OpenAPI Endpoints before exiting...")
                stop_server()
            print("\nExiting application. Goodbye!")
            break
            
        else:
            # Dynamic message based on max_choice
            print(f"Invalid choice. Please enter a number between 1 and {max_choice}.")


def run_update(args):
    """
    Run an automatic update task based on command line arguments.
    Used for scheduled updates.
    
    Args:
        args: Command line arguments
        
    Returns:
        int: Exit code (0 for success, 1 for failure)
    """
    logger = logging.getLogger("update")
    logger.info(f"Starting automatic update with args: {args}")
    
    # Reset cancellation event at the start
    global_cancellation_event.clear()
    
    # Create a local cancellation event that links to the global one
    cancellation_event = Event()
    
    # Function to check for cancellation
    def check_cancelled():
        if global_cancellation_event.is_set():
            cancellation_event.set()
            return True
        return False
    
    try:
        # Initialize required components
        credentials_manager = CredentialsManager()
        task_tracker = TaskTracker()
        
        # Create task to track progress
        task_id = args.task_id if args.task_id else None
        
        # Check for Hugging Face credentials
        hf_username, huggingface_token = credentials_manager.get_huggingface_credentials()
        if not huggingface_token:
            logger.error("Hugging Face token not found. Please set credentials first.")
            return 1
            
        # Initialize crawler and dataset creator
        from web.crawler import WebCrawler
        from huggingface.dataset_creator import DatasetCreator
        
        web_crawler = WebCrawler()
        dataset_creator = DatasetCreator(huggingface_token=huggingface_token)
        
        # Handle URL update
        if args.url:
            url = args.url
            dataset_name = args.dataset_name
            recursive = args.recursive
            
            logger.info(f"Updating dataset '{dataset_name}' from URL: {url}")
            
            # Create task for tracking
            if not task_id:
                task_id = task_tracker.create_task(
                    "url_update",
                    {"url": url, "dataset_name": dataset_name, "recursive": recursive},
                    f"Updating dataset '{dataset_name}' from URL {url}"
                )
                
            # Define progress callback
            def progress_callback(percent, message=None):
                # Check for cancellation
                if check_cancelled():
                    if message:
                        logger.info(f"Cancelled at {percent:.0f}% - {message}")
                    else:
                        logger.info(f"Cancelled at {percent:.0f}%")
                    return
                
                if message:
                    logger.info(f"Progress: {percent:.0f}% - {message}")
                else:
                    logger.info(f"Progress: {percent:.0f}%")
                    
                if task_id:
                    task_tracker.update_task_progress(task_id, percent)
            
            # Create or update dataset
            result = dataset_creator.create_dataset_from_url(
                url=url,
                dataset_name=dataset_name,
                description=f"Documentation scraped from {url}",
                recursive=recursive,
                progress_callback=progress_callback,
                _cancellation_event=cancellation_event,
                update_existing=True
            )
            
            # Check for cancellation
            if check_cancelled():
                logger.info("Operation cancelled by user")
                if task_id:
                    task_tracker.cancel_task(task_id)
                return 1
            
            if result.get("success"):
                logger.info(f"Dataset '{dataset_name}' updated successfully")
                if task_id:
                    task_tracker.complete_task(task_id, success=True)
                return 0
            else:
                logger.error(f"Failed to update dataset: {result.get('message', 'Unknown error')}")
                if task_id:
                    task_tracker.complete_task(task_id, success=False, 
                                          result={"error": result.get('message', 'Unknown error')})
                return 1
                
        else:
            logger.error("No URL specified")
            return 1
            
    except Exception as e:
        logger.error(f"Error during update: {e}", exc_info=True)
        if task_id:
            task_tracker.complete_task(task_id, success=False, result={"error": str(e)})
        return 1

def setup_signal_handlers():
    """Setup signal handlers for graceful shutdown."""
    
    def signal_handler(sig, frame):
        """Handle signals like CTRL+C by setting the cancellation event."""
        if sig == signal.SIGINT:
            print("\n\nReceived interrupt signal (Ctrl+C). Cancelling operations and shutting down...")
        elif sig == signal.SIGTERM:
            print("\n\nReceived termination signal. Cancelling operations and shutting down...")
        
        # Set the cancellation event to stop ongoing tasks
        global_cancellation_event.set()
        
        # Set a flag to exit after current operation
        current_thread().exit_requested = True
        
        # Make sure we don't handle the same signal again (let default handler take over if needed)
        signal.signal(sig, signal.SIG_DFL)
        
        # Don't exit immediately - let the application handle the shutdown gracefully
        # The application will check the cancellation event and exit cleanly
    
    # Set up the signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Add an exit flag to the main thread
    current_thread().exit_requested = False

def clean_shutdown():
    """Perform a clean shutdown of the application."""
    logger.info("Performing clean shutdown...")
    
    # Stop server if running
    if is_server_running():
        print("\nStopping OpenAPI Endpoints...")
        stop_server()
    
    # Cancel any running background threads
    from web.crawler import shutdown_executor
    shutdown_executor()
    
    print("\nApplication has been shut down.")

def run_web_ui(use_https=False, cert_file=None, key_file=None, generate_cert=False):
    """Run the web UI interface with optional HTTPS support.
    
    Args:
        use_https: Whether to use HTTPS
        cert_file: Path to SSL certificate file
        key_file: Path to SSL key file
        generate_cert: Whether to generate self-signed certificates
    """
    
    # Initialize credentials and other required components
    credentials_manager = CredentialsManager()
    port = credentials_manager.get_server_port()
    
    # Get OpenAPI key
    api_key = credentials_manager.get_openapi_key()
    
    if not api_key:
        print("\nOpenAPI key not configured. Setting temporary key for this session.")
        api_key = "temporary_key_" + str(time.time())
    
    # Handle HTTPS setup
    if use_https:
        if generate_cert:
            print("\nGenerating self-signed SSL certificates...")
            try:
                from utils.generate_cert import generate_self_signed_cert
                
                # Create certs directory in project root
                certs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "certs")
                hostname = "localhost"
                
                # Generate certificates
                cert_path, key_path = generate_self_signed_cert(
                    output_dir=certs_dir,
                    days=365,
                    hostname=hostname
                )
                
                # Use the generated certificates
                cert_file = cert_path
                key_file = key_path
                
                print(f"Self-signed certificates generated successfully.")
                print(f"Certificate file: {cert_file}")
                print(f"Key file: {key_file}")
                
            except Exception as e:
                print(f"Error generating self-signed certificates: {e}")
                print("Falling back to HTTP.")
                use_https = False
        
        # Verify certificate and key files
        if use_https and (not cert_file or not key_file):
            print("\nHTTPS requested but certificate or key file not provided.")
            print("You can specify --cert-file and --key-file, or use --generate-cert to create self-signed certificates.")
            print("Falling back to HTTP.")
            use_https = False
        
        if use_https and (not os.path.exists(cert_file) or not os.path.exists(key_file)):
            print(f"\nCertificate file ({cert_file}) or key file ({key_file}) not found.")
            print("Falling back to HTTP.")
            use_https = False
    
    # Start server with UI enabled (no static/templates needed)
    protocol = "HTTPS" if use_https else "HTTP"
    print(f"\nStarting web UI on port {port} with {protocol}...")
    
    server_info = start_server_with_ui(
        api_key=api_key, 
        port=port,
        use_https=use_https,
        cert_file=cert_file,
        key_file=key_file
    )
    
    if server_info:
        print(f"Backend API running at: {server_info['web_ui_url']}")
        print(f"API Documentation: {server_info['api_docs_url']}")
        print(f"Frontend should be started separately with 'cd frontend && npm run dev'")
        
        if use_https:
            print("\nNote: Since you're using self-signed certificates, you may need to:")
            print("1. Accept the security warning in your browser when accessing the API")
            print("2. Configure your frontend to trust this certificate or disable certificate validation for development")
        
        return True
    else:
        print("Failed to start web UI")
        return False

def main():
    """Main entry point for the application."""
    setup_logging()
    
    # Setup signal handlers
    setup_signal_handlers()
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="othertales homework")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Update command
    update_parser = subparsers.add_parser("update", help="Update an existing dataset")
    update_parser.add_argument("--url", help="URL to scrape")
    update_parser.add_argument("--dataset-name", required=True, help="Dataset name to update")
    update_parser.add_argument("--recursive", action="store_true", help="Recursively crawl all linked pages")
    update_parser.add_argument("--task-id", help="Task ID for tracking")
    
    # Web UI command
    web_ui_parser = subparsers.add_parser("web", help="Start the web UI")
    web_ui_parser.add_argument("--https", action="store_true", help="Enable HTTPS with self-signed certificates")
    web_ui_parser.add_argument("--cert-file", help="Path to SSL certificate file")
    web_ui_parser.add_argument("--key-file", help="Path to SSL key file")
    web_ui_parser.add_argument("--generate-cert", action="store_true", help="Generate self-signed certificates")
    
    # Parse arguments
    args = parser.parse_args()
    
    try:
        # Handle command-line mode
        if args.command == "update":
            result = run_update(args)
            clean_shutdown()
            return result
        elif args.command == "web":
            # Run the web UI with HTTPS if requested
            run_web_ui(
                use_https=args.https,
                cert_file=args.cert_file,
                key_file=args.key_file,
                generate_cert=args.generate_cert
            )
            
            # Keep the main thread alive to handle signals properly
            while not getattr(current_thread(), 'exit_requested', False):
                time.sleep(1)
                
            clean_shutdown()
            return 0
        else:
            # No command or unknown command, run interactive CLI
            run_cli()
            clean_shutdown()
            return 0
    except KeyboardInterrupt:
        # This should now be caught by our signal handler first,
        # but keep this as a fallback
        logger.info("KeyboardInterrupt received in main()")
        clean_shutdown()
        print("\nApplication terminated by user.")
        return 0
    except Exception as e:
        print(f"\nError: Application failed: {e}")
        logger.critical(f"Application failed with error: {e}")
        logger.debug(f"Traceback: {traceback.format_exc()}")
        clean_shutdown()
        return 1


if __name__ == "__main__":
    sys.exit(main())