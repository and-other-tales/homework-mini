import sys
import os
import logging
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

from cli.scrape_crawl import scrape_crawl
from cli.github_dataset import github_dataset
from cli.manage_datasets import manage_datasets
from cli.resume_task import resume_task
from cli.scheduled_tasks import scheduled_tasks
from cli.web_ui import web_ui
from cli.configuration import configuration
from cli.ai_assistant import ai_assistant

# Global cancellation event for stopping ongoing tasks
global_cancellation_event = Event()

# Global logger
logger = logging.getLogger(__name__)

def main_menu():
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
            scrape_crawl()
        
        elif choice == "3":
            github_dataset()
        
        elif choice == "4":
            manage_datasets()
                
        # Resume Scraping Task (only available if there are resumable tasks)
        elif choice == "5" and resumable_tasks:
            resume_task()
        
        # Scheduled Tasks menu (position depends on whether Resume Dataset Creation is available)
        elif (choice == "5" and not resumable_tasks) or (choice == "6" and resumable_tasks):
            scheduled_tasks()
        
        # Web UI menu (position depends on whether Resume Dataset Creation is available)
        elif (choice == "6" and not resumable_tasks) or (choice == "7" and resumable_tasks):
            web_ui()
        
        # Configuration menu (position depends on whether Resume Dataset Creation is available)
        elif (choice == "7" and not resumable_tasks) or (choice == "8" and resumable_tasks):
            configuration()
                
        # Run AI Assistant (position depends on whether Resume Dataset Creation is available)
        elif (choice == "9" and not resumable_tasks) or (choice == "10" and resumable_tasks):
            ai_assistant()
        
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

