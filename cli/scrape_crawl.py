import logging
from config.credentials_manager import CredentialsManager
from huggingface.dataset_manager import DatasetManager
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

class ScrapeCrawlApp(App):
    CSS_PATH = "tui_app.css"

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()
        yield Container(
            Horizontal(
                Vertical(
                    Label("Scrape & Crawl"),
                    TextInput(placeholder="Enter the URL to scrape..."),
                    Button("Submit", id="submit_button"),
                    id="left_panel",
                ),
                Vertical(
                    Panel(Markdown("## Scrape & Crawl Status")),
                    ListView(id="status_list"),
                    id="right_panel",
                ),
                id="main_container",
            )
        )

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "submit_button":
            url = self.query_one(TextInput).value
            await self.scrape_crawl(url)

    async def scrape_crawl(self, url: str) -> None:
        self.query_one(ListView).append(Label(f"Starting scrape of: {url}"))

        try:
            credentials_manager = CredentialsManager()
            hf_username, huggingface_token = credentials_manager.get_huggingface_credentials()
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

            dataset_name = "example_dataset"
            description = "Example dataset description"
            result = dataset_creator.create_dataset_from_url(
                url=url,
                dataset_name=dataset_name,
                description=description,
                recursive=True,
                progress_callback=progress_callback,
                update_existing=False
            )

            if result.get("success"):
                self.query_one(ListView).append(Label(f"Dataset '{dataset_name}' created successfully!"))
            else:
                self.query_one(ListView).append(Label("Failed to create dataset."))

        except Exception as e:
            self.query_one(ListView).append(Label(f"Error creating dataset: {e}"))
            logging.error(f"Error in scrape and crawl: {e}")

def scrape_crawl():
    app = ScrapeCrawlApp()
    app.run()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    scrape_crawl()
