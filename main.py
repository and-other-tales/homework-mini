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
from api.server import start_server, stop_server, is_server_running, get_server_info
from threading import Event, current_thread
from ui.main_menu import main_menu
from ui.tui_app import TUIApp

# Global cancellation event for stopping ongoing tasks
global_cancellation_event = Event()

# Global logger
logger = logging.getLogger(__name__)


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
        
        # Check for HuggingFace credentials
        hf_username, huggingface_token = credentials_manager.get_huggingface_credentials()
        if not huggingface_token:
            logger.error("HuggingFace token not found. Please set credentials first.")
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
    
    
    # Parse arguments
    args = parser.parse_args()
    
    try:
        # Handle command-line mode
        if args.command == "update":
            result = run_update(args)
            clean_shutdown()
            return result
        else:
            # No command or unknown command, run TUI application
            TUIApp().run()
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
