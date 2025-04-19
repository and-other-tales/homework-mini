import logging
from config.credentials_manager import CredentialsManager
from huggingface.dataset_manager import DatasetManager
from utils.task_tracker import TaskTracker
from web.crawler import WebCrawler
from huggingface.dataset_creator import DatasetCreator
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

class ResumeTaskApp(App):
    CSS_PATH = "tui_app.css"

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()
        yield Container(
            Horizontal(
                Vertical(
                    Label("Resume Scraping Task"),
                    ListView(id="task_list"),
                    Button("Resume Task", id="resume_button"),
                    Button("Return to Main Menu", id="return_main"),
                    id="left_panel",
                ),
                Vertical(
                    Panel(Markdown("## Task Details")),
                    ListView(id="task_details"),
                    id="right_panel",
                ),
                id="main_container",
            )
        )

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "resume_button":
            await self.resume_task()
        elif event.button.id == "return_main":
            self.exit()

    async def resume_task(self):
        task_index = int(input("Enter task number to resume: ")) - 1
        tasks = self.tasks

        if 0 <= task_index < len(tasks):
            selected_task = tasks[task_index]
            task_id = selected_task["id"]
            task_type = selected_task["type"]
            task_params = selected_task["params"]

            confirm = input(f"Resume task: {selected_task['description']}? (yes/no): ")
            if confirm.lower() != "yes":
                self.query_one(ListView).append(Label("Resumption cancelled"))
                return

            self.query_one(ListView).append(Label(f"\nResuming task {task_id}..."))

            cancellation_event = Event()

            if task_type == "scrape":
                hf_username, huggingface_token = self.credentials_manager.get_huggingface_credentials()
                if not huggingface_token:
                    self.query_one(ListView).append(Label("\nError: Hugging Face token not found. Please set your credentials first."))
                    return

                web_crawler = WebCrawler()
                dataset_creator = DatasetCreator(huggingface_token=huggingface_token)

                def progress_callback(percent, message=None):
                    if percent % 10 == 0 or percent == 100:
                        status = f"Progress: {percent:.0f}%"
                        if message:
                            status += f" - {message}"
                        self.query_one(ListView).append(Label(status))

                url = task_params.get("url")
                dataset_name = task_params.get("dataset_name")
                description = task_params.get("description")
                recursive = task_params.get("recursive", False)

                self.query_one(ListView).append(Label(f"Resuming dataset creation from URL: {url}"))

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
                    self.query_one(ListView).append(Label(f"\nDataset '{dataset_name}' creation resumed and completed successfully"))
                else:
                    self.query_one(ListView).append(Label(f"\nFailed to resume dataset creation: {result.get('message', 'Unknown error')}"))

            else:
                self.query_one(ListView).append(Label(f"Unsupported task type: {task_type}"))

        else:
            self.query_one(ListView).append(Label("Invalid task number"))

    async def on_mount(self) -> None:
        self.credentials_manager = CredentialsManager()
        self.task_tracker = TaskTracker()
        self.tasks = self.task_tracker.list_resumable_tasks()

        if not self.tasks:
            self.query_one(ListView).append(Label("No resumable tasks found."))
            return

        self.query_one(ListView).append(Label("Available tasks to resume:"))
        for i, task in enumerate(self.tasks):
            task_desc = task.get("description", "Unknown task")
            progress = task.get("progress", 0)
            updated = task.get("updated_ago", "unknown time")
            self.query_one(ListView).append(Label(f"{i+1}. {task_desc} ({progress:.0f}% complete, updated {updated})"))

def resume_task():
    app = ResumeTaskApp()
    app.run()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    resume_task()
