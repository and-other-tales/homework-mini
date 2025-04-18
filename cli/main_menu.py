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
    Status,
    ListView,
    Checkbox,
    Frame,
)

# Global cancellation event for stopping ongoing tasks
global_cancellation_event = Event()

# Global logger
logger = logging.getLogger(__name__)

class MainMenuApp(App):
    CSS_PATH = "tui_app.css"

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()
        yield Container(
            Horizontal(
                Vertical(
                    Label("Main Menu"),
                    Button("Start OpenAPI Endpoints", id="start_server"),
                    Button("Stop OpenAPI Endpoints", id="stop_server"),
                    Button("Scrape & Crawl", id="scrape_crawl"),
                    Button("Create Dataset from GitHub Repository", id="github_dataset"),
                    Button("Manage Existing Datasets", id="manage_datasets"),
                    Button("Resume Scraping Task", id="resume_task"),
                    Button("Scheduled Tasks & Automation", id="scheduled_tasks"),
                    Button("Launch Web UI", id="web_ui"),
                    Button("Configuration", id="configuration"),
                    Button("Run AI Assistant", id="ai_assistant"),
                    Button("Exit", id="exit"),
                    id="left_panel",
                ),
                Vertical(
                    Panel(Markdown("## Main Menu Options")),
                    ListView(id="menu_list"),
                    id="right_panel",
                ),
                id="main_container",
            )
        )

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "start_server":
            await self.start_server()
        elif event.button.id == "stop_server":
            await self.stop_server()
        elif event.button.id == "scrape_crawl":
            scrape_crawl()
        elif event.button.id == "github_dataset":
            github_dataset()
        elif event.button.id == "manage_datasets":
            manage_datasets()
        elif event.button.id == "resume_task":
            resume_task()
        elif event.button.id == "scheduled_tasks":
            scheduled_tasks()
        elif event.button.id == "web_ui":
            web_ui()
        elif event.button.id == "configuration":
            configuration()
        elif event.button.id == "ai_assistant":
            ai_assistant()
        elif event.button.id == "exit":
            self.exit()

    async def start_server(self):
        credentials_manager = CredentialsManager()
        api_key = credentials_manager.get_openapi_key()
        if not api_key:
            self.query_one(ListView).append(Label("OpenAPI key not configured. Please set an API key."))
            return
        server_port = credentials_manager.get_server_port()
        if start_server(api_key, port=server_port):
            self.query_one(ListView).append(Label(f"OpenAPI Endpoints started successfully at http://0.0.0.0:{server_port}"))
        else:
            self.query_one(ListView).append(Label("Failed to start OpenAPI Endpoints"))

    async def stop_server(self):
        if stop_server():
            self.query_one(ListView).append(Label("OpenAPI Endpoints stopped successfully"))
        else:
            self.query_one(ListView).append(Label("Failed to stop OpenAPI Endpoints"))

def main_menu():
    app = MainMenuApp()
    app.run()
