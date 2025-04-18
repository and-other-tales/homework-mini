import logging
from utils.task_scheduler import TaskScheduler

logger = logging.getLogger(__name__)

def scheduled_tasks():
    print("\n----- Scheduled Tasks & Automation -----")
    
    try:
        scheduler = TaskScheduler()
        
        if not scheduler.is_crontab_available():
            print("Crontab is not available on this system. Scheduled tasks cannot be managed.")
            return
        
        print("\nOptions:")
        print("1. List scheduled tasks")
        print("2. Create a new scheduled task")
        print("3. Update an existing scheduled task")
        print("4. Delete a scheduled task")
        print("5. Run a scheduled task now")
        print("6. Return to main menu")
        
        choice = input("\nEnter choice (1-6): ")
        
        if choice == "1":
            tasks = scheduler.list_scheduled_tasks()
            if not tasks:
                print("No scheduled tasks found.")
            else:
                print(f"\nFound {len(tasks)} scheduled tasks:")
                for i, task in enumerate(tasks):
                    print(f"{i+1}. {task.get('id', 'Unknown')} - {task.get('schedule_description', 'Unknown schedule')}")
                    print(f"   Next run: {task.get('next_run', 'Unknown')}")
                    print(f"   Command: {task.get('command', 'Unknown')}")
        
        elif choice == "2":
            task_type = input("Enter task type (e.g., 'update'): ")
            source_type = input("Enter source type ('repository' or 'organization'): ")
            source_name = input("Enter source name (repository URL or organization name): ")
            dataset_name = input("Enter dataset name: ")
            schedule_type = input("Enter schedule type ('daily', 'weekly', 'biweekly', 'monthly', 'custom'): ")
            
            if schedule_type == "custom":
                minute = input("Enter minute (0-59): ")
                hour = input("Enter hour (0-23): ")
                day = input("Enter day of month (1-31 or *): ")
                month = input("Enter month (1-12 or *): ")
                day_of_week = input("Enter day of week (0-6 or *): ")
                
                task_id = scheduler.create_scheduled_task(
                    task_type, source_type, source_name, dataset_name, schedule_type,
                    minute=minute, hour=hour, day=day, month=month, day_of_week=day_of_week
                )
            else:
                task_id = scheduler.create_scheduled_task(
                    task_type, source_type, source_name, dataset_name, schedule_type
                )
            
            if task_id:
                print(f"Scheduled task created successfully with ID: {task_id}")
            else:
                print("Failed to create scheduled task.")
        
        elif choice == "3":
            task_id = input("Enter task ID to update: ")
            schedule_type = input("Enter new schedule type ('daily', 'weekly', 'biweekly', 'monthly', 'custom'): ")
            
            if schedule_type == "custom":
                minute = input("Enter minute (0-59): ")
                hour = input("Enter hour (0-23): ")
                day = input("Enter day of month (1-31 or *): ")
                month = input("Enter month (1-12 or *): ")
                day_of_week = input("Enter day of week (0-6 or *): ")
                
                success = scheduler.update_scheduled_task(
                    task_id, schedule_type,
                    minute=minute, hour=hour, day=day, month=month, day_of_week=day_of_week
                )
            else:
                success = scheduler.update_scheduled_task(task_id, schedule_type)
            
            if success:
                print(f"Scheduled task {task_id} updated successfully.")
            else:
                print(f"Failed to update scheduled task {task_id}.")
        
        elif choice == "4":
            task_id = input("Enter task ID to delete: ")
            success = scheduler.delete_scheduled_task(task_id)
            
            if success:
                print(f"Scheduled task {task_id} deleted successfully.")
            else:
                print(f"Failed to delete scheduled task {task_id}.")
        
        elif choice == "5":
            task_id = input("Enter task ID to run now: ")
            success = scheduler.run_task_now(task_id)
            
            if success:
                print(f"Scheduled task {task_id} executed successfully.")
            else:
                print(f"Failed to execute scheduled task {task_id}.")
        
        elif choice == "6":
            return
        
        else:
            print("Invalid choice")
        
    except Exception as e:
        print(f"\nError managing scheduled tasks: {e}")
        logging.error(f"Error in scheduled tasks: {e}")
