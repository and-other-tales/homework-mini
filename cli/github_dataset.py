import logging
from config.credentials_manager import CredentialsManager
from github.client import GitHubClient
from huggingface.dataset_creator import DatasetCreator
from knowledge_graph.graph_store import GraphStore
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

class GitHubDatasetApp(App):
    CSS_PATH = "tui_app.css"

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()
        yield Container(
            Horizontal(
                Vertical(
                    Label("GitHub Dataset Creation"),
                    TextInput(placeholder="Enter GitHub repository URL..."),
                    Button("Submit", id="submit_button"),
                    id="left_panel",
                ),
                Vertical(
                    Panel(Markdown("## Dataset Creation Status")),
                    ListView(id="status_list"),
                    id="right_panel",
                ),
                id="main_container",
            )
        )

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "submit_button":
            repo_url = self.query_one(TextInput).value
            await self.create_github_dataset(repo_url)

    async def create_github_dataset(self, repo_url: str) -> None:
        if not repo_url.startswith("https://github.com/"):
            self.query_one(ListView).append(Label("Invalid GitHub repository URL. Must start with 'https://github.com/'"))
            return

        self.query_one(ListView).append(Label(f"Fetching GitHub repository: {repo_url}"))

        try:
            credentials_manager = CredentialsManager()
            _, huggingface_token = credentials_manager.get_huggingface_credentials()
            if not huggingface_token:
                self.query_one(ListView).append(Label("Error: Hugging Face token not found. Please set your credentials first."))
                return

            dataset_creator = DatasetCreator(huggingface_token=huggingface_token)

            def progress_callback(percent, message=None):
                if percent % 10 == 0 or percent == 100:
                    status = f"Progress: {percent:.0f}%"
                    if message:
                        status += f" - {message}"
                    self.query_one(ListView).append(Label(status))

            content_fetcher = ContentFetcher(github_token=None)
            content_files = content_fetcher.fetch_single_repository(repo_url, progress_callback=progress_callback)

            if not content_files:
                self.query_one(ListView).append(Label("No content found in repository or error occurred during fetch."))
                return

            dataset_name = "example_dataset"
            description = "Example dataset description"
            result = dataset_creator.create_and_push_dataset(
                file_data_list=content_files,
                dataset_name=dataset_name,
                description=description,
                source_info=repo_url,
                progress_callback=lambda p: progress_callback(p, "Creating and uploading dataset"),
                update_existing=False
            )

            if result[0]:
                self.query_one(ListView).append(Label(f"Dataset '{dataset_name}' created successfully!"))
            else:
                self.query_one(ListView).append(Label("Failed to create dataset."))

        except Exception as e:
            self.query_one(ListView).append(Label(f"Error creating dataset from GitHub repository: {e}"))
            logging.error(f"Error in GitHub repository workflow: {e}")

def github_dataset():
    app = GitHubDatasetApp()
    app.run()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    github_dataset()
