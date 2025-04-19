import logging
from config.credentials_manager import CredentialsManager
from huggingface.dataset_manager import DatasetManager
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

class ManageDatasetsApp(App):
    CSS_PATH = "tui_app.css"

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()
        yield Container(
            Horizontal(
                Vertical(
                    Label("Manage Datasets"),
                    Button("View Dataset Details", id="view_details"),
                    Button("Download Dataset Metadata", id="download_metadata"),
                    Button("Delete Dataset", id="delete_dataset"),
                    Button("Return to Main Menu", id="return_main"),
                    id="left_panel",
                ),
                Vertical(
                    Panel(Markdown("## Dataset Management Options")),
                    ListView(id="dataset_list"),
                    id="right_panel",
                ),
                id="main_container",
            )
        )

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "view_details":
            await self.view_dataset_details()
        elif event.button.id == "download_metadata":
            await self.download_dataset_metadata()
        elif event.button.id == "delete_dataset":
            await self.delete_dataset()
        elif event.button.id == "return_main":
            self.exit()

    async def view_dataset_details(self):
        dataset_index = int(input("Enter dataset number to view: ")) - 1
        datasets = self.datasets

        if 0 <= dataset_index < len(datasets):
            dataset_id = datasets[dataset_index].get('id')
            info = self.dataset_manager.get_dataset_info(dataset_id)

            if info:
                self.query_one(ListView).append(Label(f"\n----- Dataset: {info.id} -----"))
                self.query_one(ListView).append(Label(f"Description: {info.description}"))
                self.query_one(ListView).append(Label(f"Created: {info.created_at}"))
                self.query_one(ListView).append(Label(f"Last modified: {info.last_modified}"))
                self.query_one(ListView).append(Label(f"Downloads: {info.downloads}"))
                self.query_one(ListView).append(Label(f"Likes: {info.likes}"))
                self.query_one(ListView).append(Label(f"Tags: {', '.join(info.tags) if info.tags else 'None'}"))
            else:
                self.query_one(ListView).append(Label(f"Error retrieving details for dataset {dataset_id}"))
        else:
            self.query_one(ListView).append(Label("Invalid dataset number"))

    async def download_dataset_metadata(self):
        dataset_index = int(input("Enter dataset number to download metadata: ")) - 1
        datasets = self.datasets

        if 0 <= dataset_index < len(datasets):
            dataset_id = datasets[dataset_index].get('id')
            success = self.dataset_manager.download_dataset_metadata(dataset_id)

            if success:
                self.query_one(ListView).append(Label(f"\nMetadata for dataset '{dataset_id}' downloaded successfully"))
                self.query_one(ListView).append(Label(f"Saved to ./dataset_metadata/{dataset_id}/"))
            else:
                self.query_one(ListView).append(Label(f"Error downloading metadata for dataset {dataset_id}"))
        else:
            self.query_one(ListView).append(Label("Invalid dataset number"))

    async def delete_dataset(self):
        dataset_index = int(input("Enter dataset number to delete: ")) - 1
        datasets = self.datasets

        if 0 <= dataset_index < len(datasets):
            dataset_id = datasets[dataset_index].get('id')

            confirm = input(f"Are you sure you want to delete dataset '{dataset_id}'? (yes/no): ")
            if confirm.lower() == "yes":
                success = self.dataset_manager.delete_dataset(dataset_id)

                if success:
                    self.query_one(ListView).append(Label(f"\nDataset '{dataset_id}' deleted successfully"))
                else:
                    self.query_one(ListView).append(Label(f"Error deleting dataset {dataset_id}"))
            else:
                self.query_one(ListView).append(Label("Deletion cancelled"))
        else:
            self.query_one(ListView).append(Label("Invalid dataset number"))

    async def on_mount(self) -> None:
        self.credentials_manager = CredentialsManager()
        _, self.huggingface_token = self.credentials_manager.get_huggingface_credentials()

        if not self.huggingface_token:
            self.query_one(ListView).append(Label("\nError: HuggingFace token not found. Please set your credentials first."))
            return

        self.dataset_manager = DatasetManager(huggingface_token=self.huggingface_token,
                                              credentials_manager=self.credentials_manager)

        self.query_one(ListView).append(Label("\nFetching your datasets from HuggingFace..."))
        self.datasets = self.dataset_manager.list_datasets()

        if not self.datasets:
            self.query_one(ListView).append(Label("No datasets found for your account."))
            return

        self.query_one(ListView).append(Label(f"\nFound {len(self.datasets)} datasets:"))
        for i, dataset in enumerate(self.datasets):
            self.query_one(ListView).append(Label(f"{i+1}. {dataset.get('id', 'Unknown')} - {dataset.get('lastModified', 'Unknown date')}"))

def manage_datasets():
    app = ManageDatasetsApp()
    app.run()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    manage_datasets()
