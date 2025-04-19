import logging
from utils.task_scheduler import TaskScheduler
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import (
    Header,
    Footer,
    Button,
    TextInput,
    Label,
    Panel,
    Markdown,
    ListView,
)

logger = logging.getLogger(__name__)

class ScheduledTasksApp(App):
    CSS_PATH = "tui_app.css"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.scheduler = TaskScheduler()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()
        yield Container(
            Horizontal(
                Vertical(
                    Label("Scheduled Tasks & Automation"),
                    Button("List Scheduled Tasks", id="list_tasks"),
                    Button("Create New Task", id="create_task"),
                    Button("Update Existing Task", id="update_task"),
                    Button("Delete Task", id="delete_task"),
                    Button("Run Task Now", id="run_task"),
                    Button("Return to Main Menu", id="return_main"),
                    id="left_panel",
                ),
                Vertical(
                    Panel(Markdown("## Task Details")),
                    ListView(id="task_list"),
                    id="right_panel",
                ),
                id="main_container",
            )
        )

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "list_tasks":
            await self.list_scheduled_tasks()
        elif event.button.id == "create_task":
            await self.create_scheduled_task()
        elif event.button.id == "update_task":
            await self.update_scheduled_task()
        elif event.button.id == "delete_task":
            await self.delete_scheduled_task()
        elif event.button.id == "run_task":
            await self.run_scheduled_task()
        elif event.button.id == "return_main":
            self.exit()

    async def list_scheduled_tasks(self):
        if not self.scheduler.is_crontab_available():
            self.query_one(ListView).append(Label("Crontab is not available on this system. Scheduled tasks cannot be managed."))
            return

        tasks = self.scheduler.list_scheduled_tasks()
        if not tasks:
            self.query_one(ListView).append(Label("No scheduled tasks found."))
        else:
            self.query_one(ListView).append(Label(f"Found {len(tasks)} scheduled tasks:"))
            for i, task in enumerate(tasks):
                self.query_one(ListView).append(Label(f"{i+1}. {task.get('id', 'Unknown')} - {task.get('schedule_description', 'Unknown schedule')}"))
                self.query_one(ListView).append(Label(f"   Next run: {task.get('next_run', 'Unknown')}"))
                self.query_one(ListView).append(Label(f"   Command: {task.get('command', 'Unknown')}"))

    async def create_scheduled_task(self):
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

            task_id = self.scheduler.create_scheduled_task(
                task_type, source_type, source_name, dataset_name, schedule_type,
                minute=minute, hour=hour, day=day, month=month, day_of_week=day_of_week
            )
        else:
            task_id = self.scheduler.create_scheduled_task(
                task_type, source_type, source_name, dataset_name, schedule_type
            )

        if task_id:
            self.query_one(ListView).append(Label(f"Scheduled task created successfully with ID: {task_id}"))
        else:
            self.query_one(ListView).append(Label("Failed to create scheduled task."))

    async def update_scheduled_task(self):
        task_id = input("Enter task ID to update: ")
        schedule_type = input("Enter new schedule type ('daily', 'weekly', 'biweekly', 'monthly', 'custom'): ")

        if schedule_type == "custom":
            minute = input("Enter minute (0-59): ")
            hour = input("Enter hour (0-23): ")
            day = input("Enter day of month (1-31 or *): ")
            month = input("Enter month (1-12 or *): ")
            day_of_week = input("Enter day of week (0-6 or *): ")

            success = self.scheduler.update_scheduled_task(
                task_id, schedule_type,
                minute=minute, hour=hour, day=day, month=month, day_of_week=day_of_week
            )
        else:
            success = self.scheduler.update_scheduled_task(task_id, schedule_type)

        if success:
            self.query_one(ListView).append(Label(f"Scheduled task {task_id} updated successfully."))
        else:
            self.query_one(ListView).append(Label(f"Failed to update scheduled task {task_id}."))

    async def delete_scheduled_task(self):
        task_id = input("Enter task ID to delete: ")
        success = self.scheduler.delete_scheduled_task(task_id)

        if success:
            self.query_one(ListView).append(Label(f"Scheduled task {task_id} deleted successfully."))
        else:
            self.query_one(ListView).append(Label(f"Failed to delete scheduled task {task_id}."))

    async def run_scheduled_task(self):
        task_id = input("Enter task ID to run now: ")
        success = self.scheduler.run_task_now(task_id)

        if success:
            self.query_one(ListView).append(Label(f"Scheduled task {task_id} executed successfully."))
        else:
            self.query_one(ListView).append(Label(f"Failed to execute scheduled task {task_id}."))

def scheduled_tasks():
    app = ScheduledTasksApp()
    app.run()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    scheduled_tasks()
