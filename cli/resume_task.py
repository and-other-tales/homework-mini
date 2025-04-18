import logging
from config.credentials_manager import CredentialsManager
from huggingface.dataset_manager import DatasetManager
from utils.task_tracker import TaskTracker
from web.crawler import WebCrawler
from huggingface.dataset_creator import DatasetCreator

logger = logging.getLogger(__name__)

def resume_task():
    print("\n----- Resume Scraping Task -----")
    
    try:
        credentials_manager = CredentialsManager()
        task_tracker = TaskTracker()
        resumable_tasks = task_tracker.list_resumable_tasks()
        
        if not resumable_tasks:
            print("No resumable tasks found.")
            return
        
        # Display resumable tasks
        print("\nAvailable tasks to resume:")
        for i, task in enumerate(resumable_tasks):
            task_desc = task.get("description", "Unknown task")
            progress = task.get("progress", 0)
            updated = task.get("updated_ago", "unknown time")
            print(f"{i+1}. {task_desc} ({progress:.0f}% complete, updated {updated})")
        
        # Get task selection
        task_index = int(input("\nEnter task number to resume (0 to cancel): ")) - 1
        
        if task_index < 0:
            print("Resumption cancelled")
            return
            
        if 0 <= task_index < len(resumable_tasks):
            selected_task = resumable_tasks[task_index]
            task_id = selected_task["id"]
            task_type = selected_task["type"]
            task_params = selected_task["params"]
            
            # Confirm resumption
            confirm = input(f"Resume task: {selected_task['description']}? (yes/no): ")
            if confirm.lower() != "yes":
                print("Resumption cancelled")
                return
            
            print(f"\nResuming task {task_id}...")
            
            # Create cancellation event
            cancellation_event = Event()
            
            # Handle different task types
            if task_type == "scrape":
                hf_username, huggingface_token = credentials_manager.get_huggingface_credentials()
                if not huggingface_token:
                    print("\nError: Hugging Face token not found. Please set your credentials first.")
                    return
                    
                web_crawler = WebCrawler()
                dataset_creator = DatasetCreator(huggingface_token=huggingface_token)
                
                def progress_callback(percent, message=None):
                    if percent % 10 == 0 or percent == 100:
                        status = f"Progress: {percent:.0f}%"
                        if message:
                            status += f" - {message}"
                        print(status)
                
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
            
            else:
                print(f"Unsupported task type: {task_type}")
                
        else:
            print("Invalid task number")
    
    except Exception as e:
        print(f"\nError resuming task: {e}")
        logging.error(f"Error resuming task: {e}")
