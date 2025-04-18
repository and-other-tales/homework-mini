import os
import sys
import logging
import json
import datetime
import subprocess
from pathlib import Path
from crontab import CronTab
from config.settings import APP_DIR

logger = logging.getLogger(__name__)

# Directory for storing scheduled task configurations
SCHEDULES_DIR = APP_DIR / "schedules"
SCHEDULES_DIR.mkdir(exist_ok=True, parents=True)

class TaskScheduler:
    """Manages scheduled tasks for automatic dataset updates."""
    
    def __init__(self, username=None):
        """
        Initialize the task scheduler.
        
        Args:
            username (str, optional): System username for crontab access
        """
        self.username = username or os.getenv('USER') or os.getenv('USERNAME')
        self.schedules_dir = SCHEDULES_DIR
        
        try:
            # Try to access user's crontab
            self.crontab = CronTab(user=self.username)
            logger.debug(f"Crontab initialized for user: {self.username}")
        except Exception as e:
            logger.error(f"Failed to initialize crontab: {e}")
            self.crontab = None
    
    def list_scheduled_tasks(self):
        """
        List all scheduled tasks.
        
        Returns:
            list: List of scheduled task configurations
        """
        scheduled_tasks = []
        
        # Read all task configuration files
        for task_file in self.schedules_dir.glob("*.json"):
            try:
                with open(task_file, "r") as f:
                    task_data = json.load(f)
                    
                # Add human-readable next run time
                task_id = task_data.get("id")
                if task_id and self.crontab:
                    for job in self.crontab:
                        if f"--task-id {task_id}" in job.command:
                            # Calculate next run time
                            schedule = job.schedule(date_from=datetime.datetime.now())
                            next_run = schedule.get_next()
                            if next_run:
                                task_data["next_run"] = next_run.strftime("%Y-%m-%d %H:%M:%S")
                            
                            # Get schedule description
                            task_data["schedule_description"] = self._get_schedule_description(job)
                            break
                
                scheduled_tasks.append(task_data)
            except Exception as e:
                logger.error(f"Error reading task file {task_file.name}: {e}")
        
        # Sort by next run time
        scheduled_tasks.sort(key=lambda x: x.get("next_run", "9999-12-31"))
        return scheduled_tasks
    
    def _get_schedule_description(self, cron_job):
        """
        Get a human-readable description of a cron schedule.
        
        Args:
            cron_job: CronTab job object
            
        Returns:
            str: Human-readable schedule description
        """
        minute, hour, day, month, day_of_week = str(cron_job).split(" ")[:5]
        
        # Common patterns
        if minute == "0" and hour == "0" and day == "*" and month == "*" and day_of_week == "*":
            return "Daily at midnight"
        elif minute == "0" and hour == "0" and day == "*" and month == "*" and day_of_week == "0":
            return "Weekly on Sunday at midnight"
        elif minute == "0" and hour == "0" and day == "1" and month == "*" and day_of_week == "*":
            return "Monthly on the 1st at midnight"
        elif minute == "0" and hour == "0" and day == "1" and month == "1" and day_of_week == "*":
            return "Yearly on January 1st at midnight"
        elif day == "*" and month == "*" and day_of_week == "*":
            return f"Daily at {hour}:{minute}"
        elif day == "*" and month == "*":
            weekdays = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
            if day_of_week in "0123456":
                return f"Weekly on {weekdays[int(day_of_week)]} at {hour}:{minute.zfill(2)}"
            
        # Default to cron expression
        return f"Custom schedule: {str(cron_job)}"
    
    def create_scheduled_task(self, task_type, source_type, source_name, dataset_name, schedule_type, **kwargs):
        """
        Create a scheduled task for automatic dataset updates.
        
        Args:
            task_type (str): Type of task (e.g., 'update')
            source_type (str): Type of source ('repository' or 'organization')
            source_name (str): Name of the source (repository URL or organization name)
            dataset_name (str): Name of the dataset to update
            schedule_type (str): Type of schedule ('daily', 'weekly', 'biweekly', 'monthly', 'custom')
            **kwargs: Additional parameters for custom scheduling
            
        Returns:
            str: Task ID if successful, None otherwise
        """
        if not self.crontab:
            logger.error("Crontab not initialized properly")
            return None
        
        # Generate a unique task ID
        task_id = f"scheduled_{task_type}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Get the absolute path to the main script
        script_path = Path(sys.executable).resolve()
        main_script = Path(__file__).resolve().parent.parent / "main.py"
        
        # Build the command to execute
        if source_type == "repository":
            command = f"{script_path} {main_script} update --repository \"{source_name}\" --dataset-name \"{dataset_name}\" --task-id {task_id}"
        elif source_type == "organization":
            command = f"{script_path} {main_script} update --organization \"{source_name}\" --dataset-name \"{dataset_name}\" --task-id {task_id}"
        else:
            logger.error(f"Invalid source type: {source_type}")
            return None
        
        # Create the cron job based on schedule type
        job = self.crontab.new(command=command, comment=f"Dataset update: {dataset_name}")
        
        # Set schedule
        if schedule_type == "daily":
            # Run daily at midnight
            job.setall("0 0 * * *")
            schedule_desc = "Daily at midnight"
        elif schedule_type == "weekly":
            # Run weekly on Sunday at midnight
            job.setall("0 0 * * 0")
            schedule_desc = "Weekly on Sunday at midnight"
        elif schedule_type == "biweekly":
            # Run every other Sunday at midnight
            job.setall("0 0 1,15 * *")
            schedule_desc = "Twice monthly (1st and 15th) at midnight"
        elif schedule_type == "monthly":
            # Run monthly on the 1st at midnight
            job.setall("0 0 1 * *")
            schedule_desc = "Monthly on the 1st at midnight"
        elif schedule_type == "custom":
            # Custom schedule using provided values
            minute = kwargs.get("minute", "0")
            hour = kwargs.get("hour", "0")
            day = kwargs.get("day", "*")
            month = kwargs.get("month", "*")
            day_of_week = kwargs.get("day_of_week", "*")
            
            job.setall(f"{minute} {hour} {day} {month} {day_of_week}")
            schedule_desc = f"Custom schedule: {minute} {hour} {day} {month} {day_of_week}"
        else:
            logger.error(f"Invalid schedule type: {schedule_type}")
            return None
        
        # Save the crontab
        try:
            self.crontab.write()
            logger.info(f"Added cron job for task {task_id}: {schedule_desc}")
        except Exception as e:
            logger.error(f"Failed to write crontab: {e}")
            return None
        
        # Create task configuration file
        task_data = {
            "id": task_id,
            "type": task_type,
            "source_type": source_type,
            "source_name": source_name,
            "dataset_name": dataset_name,
            "schedule_type": schedule_type,
            "schedule_description": schedule_desc,
            "created_at": datetime.datetime.now().isoformat(),
            "command": command,
            "status": "active"
        }
        
        # Add custom schedule parameters if provided
        if schedule_type == "custom" and kwargs:
            task_data["schedule_params"] = {
                "minute": kwargs.get("minute", "0"),
                "hour": kwargs.get("hour", "0"),
                "day": kwargs.get("day", "*"),
                "month": kwargs.get("month", "*"),
                "day_of_week": kwargs.get("day_of_week", "*")
            }
        
        # Save task configuration
        task_file = self.schedules_dir / f"{task_id}.json"
        try:
            with open(task_file, "w") as f:
                json.dump(task_data, f, indent=2)
            logger.info(f"Saved task configuration to {task_file}")
            return task_id
        except Exception as e:
            logger.error(f"Failed to save task configuration: {e}")
            # Try to remove the cron job if config save fails
            self.crontab.remove_all(comment=f"Dataset update: {dataset_name}")
            self.crontab.write()
            return None
    
    def delete_scheduled_task(self, task_id):
        """
        Delete a scheduled task.
        
        Args:
            task_id (str): ID of the task to delete
            
        Returns:
            bool: Success status
        """
        if not self.crontab:
            logger.error("Crontab not initialized properly")
            return False
        
        # Find and remove the cron job
        found = False
        for job in self.crontab:
            if f"--task-id {task_id}" in job.command:
                self.crontab.remove(job)
                found = True
                break
        
        if found:
            try:
                self.crontab.write()
                logger.info(f"Removed cron job for task {task_id}")
            except Exception as e:
                logger.error(f"Failed to write crontab after removing job: {e}")
                return False
        
        # Delete the task configuration file
        task_file = self.schedules_dir / f"{task_id}.json"
        if task_file.exists():
            try:
                task_file.unlink()
                logger.info(f"Deleted task configuration file: {task_file}")
                return True
            except Exception as e:
                logger.error(f"Failed to delete task configuration file: {e}")
                return False
        
        return found
    
    def update_scheduled_task(self, task_id, schedule_type, **kwargs):
        """
        Update the schedule of an existing task.
        
        Args:
            task_id (str): ID of the task to update
            schedule_type (str): New schedule type
            **kwargs: Additional parameters for custom scheduling
            
        Returns:
            bool: Success status
        """
        if not self.crontab:
            logger.error("Crontab not initialized properly")
            return False
        
        # Find the existing task configuration
        task_file = self.schedules_dir / f"{task_id}.json"
        if not task_file.exists():
            logger.error(f"Task configuration not found: {task_id}")
            return False
        
        try:
            with open(task_file, "r") as f:
                task_data = json.load(f)
        except Exception as e:
            logger.error(f"Failed to read task configuration: {e}")
            return False
        
        # Find and update the cron job
        found = False
        for job in self.crontab:
            if f"--task-id {task_id}" in job.command:
                # Update schedule based on type
                if schedule_type == "daily":
                    job.setall("0 0 * * *")
                    schedule_desc = "Daily at midnight"
                elif schedule_type == "weekly":
                    job.setall("0 0 * * 0")
                    schedule_desc = "Weekly on Sunday at midnight"
                elif schedule_type == "biweekly":
                    job.setall("0 0 1,15 * *")
                    schedule_desc = "Twice monthly (1st and 15th) at midnight"
                elif schedule_type == "monthly":
                    job.setall("0 0 1 * *")
                    schedule_desc = "Monthly on the 1st at midnight"
                elif schedule_type == "custom":
                    minute = kwargs.get("minute", "0")
                    hour = kwargs.get("hour", "0")
                    day = kwargs.get("day", "*")
                    month = kwargs.get("month", "*")
                    day_of_week = kwargs.get("day_of_week", "*")
                    
                    job.setall(f"{minute} {hour} {day} {month} {day_of_week}")
                    schedule_desc = f"Custom schedule: {minute} {hour} {day} {month} {day_of_week}"
                else:
                    logger.error(f"Invalid schedule type: {schedule_type}")
                    return False
                
                found = True
                break
        
        if not found:
            logger.error(f"No cron job found for task {task_id}")
            return False
        
        # Save the updated crontab
        try:
            self.crontab.write()
            logger.info(f"Updated cron job for task {task_id}: {schedule_desc}")
        except Exception as e:
            logger.error(f"Failed to write crontab after updating job: {e}")
            return False
        
        # Update task configuration
        task_data["schedule_type"] = schedule_type
        task_data["schedule_description"] = schedule_desc
        task_data["updated_at"] = datetime.datetime.now().isoformat()
        
        # Update custom schedule parameters if provided
        if schedule_type == "custom" and kwargs:
            task_data["schedule_params"] = {
                "minute": kwargs.get("minute", "0"),
                "hour": kwargs.get("hour", "0"),
                "day": kwargs.get("day", "*"),
                "month": kwargs.get("month", "*"),
                "day_of_week": kwargs.get("day_of_week", "*")
            }
        elif "schedule_params" in task_data:
            del task_data["schedule_params"]
        
        # Save updated task configuration
        try:
            with open(task_file, "w") as f:
                json.dump(task_data, f, indent=2)
            logger.info(f"Updated task configuration: {task_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to save updated task configuration: {e}")
            return False
    
    def get_task_details(self, task_id):
        """
        Get details of a scheduled task.
        
        Args:
            task_id (str): ID of the task
            
        Returns:
            dict: Task details or None if not found
        """
        task_file = self.schedules_dir / f"{task_id}.json"
        if not task_file.exists():
            logger.warning(f"Task configuration not found: {task_id}")
            return None
        
        try:
            with open(task_file, "r") as f:
                task_data = json.load(f)
                
            # Add next run time if available
            if self.crontab:
                for job in self.crontab:
                    if f"--task-id {task_id}" in job.command:
                        schedule = job.schedule(date_from=datetime.datetime.now())
                        next_run = schedule.get_next()
                        if next_run:
                            task_data["next_run"] = next_run.strftime("%Y-%m-%d %H:%M:%S")
                        break
                
            return task_data
        except Exception as e:
            logger.error(f"Error reading task file for {task_id}: {e}")
            return None
    
    def is_crontab_available(self):
        """
        Check if crontab is available on the system.
        
        Returns:
            bool: True if crontab is available, False otherwise
        """
        return self.crontab is not None
    
    def run_task_now(self, task_id):
        """
        Run a scheduled task immediately.
        
        Args:
            task_id (str): ID of the task to run
            
        Returns:
            bool: Success status
        """
        task_data = self.get_task_details(task_id)
        if not task_data:
            return False
        
        command = task_data.get("command")
        if not command:
            logger.error(f"No command found for task {task_id}")
            return False
        
        try:
            # Run the command in the background
            subprocess.Popen(command, shell=True, 
                            stdout=subprocess.PIPE, 
                            stderr=subprocess.PIPE)
            logger.info(f"Executed task {task_id} manually")
            return True
        except Exception as e:
            logger.error(f"Failed to execute task {task_id}: {e}")
            return False