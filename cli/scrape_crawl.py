import sys
import logging
from config.credentials_manager import CredentialsManager
from huggingface.dataset_manager import DatasetManager
from utils.task_tracker import TaskTracker
from web.crawler import WebCrawler
from huggingface.dataset_creator import DatasetCreator
from knowledge_graph.graph_store import GraphStore

logger = logging.getLogger(__name__)

def scrape_crawl():
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
        return
        
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
        # Initialize clients
        web_crawler = WebCrawler()
        credentials_manager = CredentialsManager()
        hf_username, huggingface_token = credentials_manager.get_huggingface_credentials()
        if not huggingface_token:
            print("\nError: Hugging Face token not found. Please set your credentials first.")
            return
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
