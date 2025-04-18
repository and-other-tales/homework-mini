import logging
import uuid
import time
from typing import Dict, List, Optional, Any, Union
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from utils.task_tracker import TaskTracker
from utils.llm_client import LLMClient
from config.credentials_manager import CredentialsManager

# Configure logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter()

# Models for agent task requests and responses
class AgentTaskOptions(BaseModel):
    """Options for agent tasks."""
    url_patterns: Optional[List[str]] = Field(None, description="List of URL patterns to follow")
    max_depth: Optional[int] = Field(None, description="Maximum crawl depth")
    content_filters: Optional[List[str]] = Field(None, description="Content filters")
    export_to_graph: Optional[bool] = Field(None, description="Whether to export to knowledge graph")
    graph_name: Optional[str] = Field(None, description="Name of the knowledge graph")
    dataset_name: Optional[str] = Field(None, description="Name for the dataset")
    description: Optional[str] = Field(None, description="Description for the dataset or graph")

class AgentTaskRequest(BaseModel):
    """Request body for agent task endpoints."""
    task_type: str = Field(..., description="Type of agent task (web, github, knowledge_graph)")
    message: str = Field(..., description="User message for the agent")
    options: Optional[AgentTaskOptions] = Field(None, description="Additional task options")

class AgentTaskResponse(BaseModel):
    """Response model for agent task endpoints."""
    task_id: str = Field(..., description="Unique ID for the task")
    status: str = Field(..., description="Status of the task")
    message: str = Field(..., description="Status message")
    data: Optional[Dict[str, Any]] = Field(None, description="Additional task data")

class TaskStatusResponse(BaseModel):
    """Response model for task status endpoints."""
    task_id: str = Field(..., description="Unique ID for the task")
    status: str = Field(..., description="Status of the task")
    progress: Optional[float] = Field(None, description="Task progress percentage")
    message: Optional[str] = Field(None, description="Status message")
    result: Optional[Dict[str, Any]] = Field(None, description="Task result data")
    created_at: Optional[float] = Field(None, description="Task creation timestamp")
    updated_at: Optional[float] = Field(None, description="Last status update timestamp")

# Dependency for getting an LLM client
async def get_llm_client():
    """Get an initialized LLM client."""
    # First check environment directly for OPENAI_API_KEY
    import os
    from utils.env_loader import load_environment_variables
    
    # Force reload environment variables
    env_vars = load_environment_variables()
    
    # Try environment first
    openai_key = os.environ.get("OPENAI_API_KEY")
    
    # If not found in environment, try credentials manager
    if not openai_key:
        credentials_manager = CredentialsManager()
        openai_key = credentials_manager.get_openai_key()
    
    if not openai_key:
        # One last attempt - read the .env file directly
        try:
            from pathlib import Path
            import re
            
            env_paths = [
                Path(".env"),
                Path("../.env"),
                Path(os.path.join(os.path.dirname(__file__), "../../.env")),
            ]
            
            for env_path in env_paths:
                if env_path.exists():
                    logger.info(f"Reading .env file directly from {env_path}")
                    env_content = env_path.read_text()
                    key_match = re.search(r'OPENAI_API_KEY=(.+)', env_content)
                    
                    if key_match:
                        openai_key = key_match.group(1).strip()
                        logger.info("Found OpenAI API key directly in .env file")
                        # Set it in environment for future use
                        os.environ["OPENAI_API_KEY"] = openai_key
                        break
        except Exception as e:
            logger.error(f"Error reading .env file directly: {e}")
    
    if not openai_key:
        raise HTTPException(
            status_code=500,
            detail="OpenAI API key not configured. Please set OPENAI_API_KEY in .env file or environment."
        )
    
    # Log that we found the key (with masking)
    masked_key = openai_key[:4] + "..." + openai_key[-4:] if len(openai_key) > 8 else "***"
    logger.info(f"Using OpenAI API key: {masked_key}")
    
    # Create LLM client with key
    credentials_manager = CredentialsManager()
    return LLMClient(api_key=openai_key, credentials_manager=credentials_manager)

@router.post("/agent/tasks", response_model=AgentTaskResponse, tags=["Agent"])
async def create_agent_task(
    request: AgentTaskRequest,
    llm_client: LLMClient = Depends(get_llm_client),
    api_key: str = Header(None, alias="X-API-KEY")
):
    """
    Create a new agent task for processing.
    
    This endpoint accepts various types of agent tasks and processes them asynchronously.
    A task ID is immediately returned, which can be used to check status later.
    """
    # Check if we got an API key from the frontend, and if we need to update our LLM client
    if api_key and not llm_client.api_key:
        logger.info("Using API key provided by frontend request")
        llm_client.api_key = api_key
        # Set it in the environment for other parts of the app
        os.environ["OPENAI_API_KEY"] = api_key
    
    task_id = str(uuid.uuid4())
    task_tracker = TaskTracker()
    
    # Validate task type
    valid_task_types = ["web", "github", "knowledge_graph", "custom"]
    if request.task_type not in valid_task_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid task type. Must be one of: {', '.join(valid_task_types)}"
        )
    
    # Initialize task in tracker
    task_tracker.add_task(
        task_id=task_id,
        task_type=request.task_type,
        status="queued",
        details={
            "message": request.message,
            "options": request.options.dict() if request.options else {},
            "created_at": time.time()
        }
    )
    
    # Handle task in background
    import asyncio
    asyncio.create_task(
        process_agent_task(
            task_id=task_id,
            task_type=request.task_type,
            message=request.message,
            options=request.options.dict() if request.options else {},
            llm_client=llm_client
        )
    )
    
    return AgentTaskResponse(
        task_id=task_id,
        status="queued",
        message="Agent task queued for processing",
        data={"task_type": request.task_type}
    )

@router.get("/agent/tasks/{task_id}", response_model=TaskStatusResponse, tags=["Agent"])
async def get_task_status(task_id: str):
    """
    Get the status of an agent task.
    
    This endpoint retrieves the current status, progress, and results (if available)
    for a previously created agent task.
    """
    task_tracker = TaskTracker()
    task = task_tracker.get_task(task_id)
    
    if not task:
        raise HTTPException(
            status_code=404,
            detail=f"Task with ID {task_id} not found"
        )
    
    return TaskStatusResponse(
        task_id=task_id,
        status=task.get("status", "unknown"),
        progress=task.get("progress"),
        message=task.get("message"),
        result=task.get("result"),
        created_at=task.get("details", {}).get("created_at"),
        updated_at=task.get("updated_at")
    )

@router.delete("/agent/tasks/{task_id}", response_model=dict, tags=["Agent"])
async def cancel_task(task_id: str):
    """
    Cancel a running agent task.
    
    This endpoint attempts to cancel a running task and marks it as cancelled
    in the task tracker.
    """
    task_tracker = TaskTracker()
    success = task_tracker.cancel_task(task_id)
    
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Task with ID {task_id} not found or could not be cancelled"
        )
    
    return {
        "success": True,
        "message": f"Task {task_id} cancelled successfully"
    }

@router.get("/agent/tasks", response_model=Dict[str, Any], tags=["Agent"])
async def list_tasks(
    status: Optional[str] = None,
    task_type: Optional[str] = None,
    limit: int = 10
):
    """
    List agent tasks with optional filtering.
    
    This endpoint retrieves a list of agent tasks, optionally filtered by status
    and task type, with a configurable limit on the number of results.
    """
    task_tracker = TaskTracker()
    tasks = task_tracker.list_tasks(status=status, task_type=task_type, limit=limit)
    
    return {
        "tasks": tasks,
        "count": len(tasks)
    }

async def process_agent_task(
    task_id: str,
    task_type: str,
    message: str,
    options: Dict[str, Any],
    llm_client: LLMClient
):
    """
    Process an agent task asynchronously.
    
    This function runs in the background and updates the task status as it progresses.
    It handles different types of agent tasks accordingly.
    
    Args:
        task_id: Unique identifier for the task
        task_type: Type of agent task (web, github, knowledge_graph, custom)
        message: User message for the agent
        options: Additional task options
        llm_client: Initialized LLM client
    """
    task_tracker = TaskTracker()
    
    try:
        # Update task status to running
        task_tracker.update_task(
            task_id=task_id,
            status="running",
            progress=0,
            message="Starting agent task"
        )
        
        # Define a progress callback for task updates
        def progress_callback(percent, message=None):
            task_tracker.update_task(
                task_id=task_id,
                progress=percent,
                message=message or f"Processing: {percent:.0f}% complete"
            )
        
        # Process based on task type
        if task_type == "web":
            # Web crawling task
            result = await llm_client.run_web_agent(
                message=message,
                url_patterns=options.get("url_patterns", []),
                max_depth=options.get("max_depth", 3),
                content_filters=options.get("content_filters", []),
                progress_callback=progress_callback,
                export_to_graph=options.get("export_to_graph", False),
                graph_name=options.get("graph_name"),
                dataset_name=options.get("dataset_name"),
                description=options.get("description", "Dataset created by web agent")
            )
        elif task_type == "github":
            # GitHub repository task
            result = await llm_client.run_github_agent(
                message=message,
                progress_callback=progress_callback,
                export_to_graph=options.get("export_to_graph", False),
                graph_name=options.get("graph_name"),
                dataset_name=options.get("dataset_name"),
                description=options.get("description", "Dataset created by GitHub agent")
            )
        elif task_type == "knowledge_graph":
            # Knowledge graph task
            result = await llm_client.run_knowledge_graph_agent(
                message=message,
                graph_name=options.get("graph_name"),
                progress_callback=progress_callback
            )
        elif task_type == "custom":
            # Custom agent task (uses automatic tool selection)
            result = await llm_client.run_agent(
                message=message,
                progress_callback=progress_callback,
                options=options
            )
        else:
            # Should not happen due to validation in endpoint
            raise ValueError(f"Invalid task type: {task_type}")
        
        # Update task with result
        if isinstance(result, dict) and result.get("success") is not None:
            if result.get("success"):
                task_tracker.update_task(
                    task_id=task_id,
                    status="completed",
                    progress=100,
                    message=result.get("message", "Task completed successfully"),
                    result=result.get("data", {})
                )
            else:
                task_tracker.update_task(
                    task_id=task_id,
                    status="failed",
                    message=result.get("message", "Task failed"),
                    result=result.get("data", {})
                )
        else:
            # Handle non-standard result format
            task_tracker.update_task(
                task_id=task_id,
                status="completed",
                progress=100,
                message="Task completed",
                result={"response": result}
            )
    
    except Exception as e:
        logger.error(f"Error processing agent task {task_id}: {str(e)}", exc_info=True)
        
        # Update task with error
        task_tracker.update_task(
            task_id=task_id,
            status="failed",
            message=f"Error: {str(e)}",
            result={"error": str(e)}
        )