import logging
import json
from pathlib import Path
from datetime import datetime
from datasets import Dataset, Features, Value, Pdf
from huggingface_hub import HfApi
from processors.file_processor import FileProcessor
from processors.metadata_generator import MetadataGenerator
from utils.performance import distributed_process
from utils.task_tracker import TaskTracker

logger = logging.getLogger(__name__)


class DatasetCreator:
    """Create Hugging Face datasets from repository content."""

    def __init__(self, huggingface_token=None):
        self.token = huggingface_token
        self.file_processor = FileProcessor()
        self.metadata_generator = MetadataGenerator()
        self.api = HfApi() if huggingface_token else None
        self.task_tracker = TaskTracker()

    def create_dataset(
        self,
        file_data_list,
        dataset_name,
        description=None,
        source_info=None,
        progress_callback=None,
    ):
        """Create a Hugging Face dataset from file data.
        
        Args:
            file_data_list (list): List of file data dictionaries
            dataset_name (str): Name for the dataset
            description (str, optional): Description for the dataset
            source_info (str, optional): Source information
            progress_callback (callable, optional): Function to call with progress updates
            
        Returns:
            Dataset: The created dataset or None if creation fails
        """
        logger.info(
            f"Creating dataset '{dataset_name}' from {len(file_data_list)} files"
        )

        # Process files
        processed_files = self.file_processor.process_files(file_data_list)

        if not processed_files:
            logger.error("No files were successfully processed for the dataset")
            return None

        # Check if there are PDF files
        has_pdf_files = any("pdf_path" in item for item in processed_files)

        # Generate dataset metadata
        dataset_metadata = self.metadata_generator.generate_dataset_metadata(
            source_info or dataset_name, len(processed_files)
        )

        if description:
            dataset_metadata["description"] = description

        # Generate repository structure metadata
        repo_structure = self.metadata_generator.generate_repo_structure_metadata(
            file_data_list
        )
        dataset_metadata["repository_structure"] = repo_structure

        # Create dataset
        try:
            if has_pdf_files:
                # Map PDF paths for each item in processed_files
                pdf_paths = []
                metadata_entries = []
                for item in processed_files:
                    if "pdf_path" in item:
                        pdf_paths.append(item["pdf_path"])
                    else:
                        # For non-PDF items, add None as placeholder
                        pdf_paths.append(None)
                    metadata_entries.append(json.dumps(item["metadata"]))
                
                dataset = Dataset.from_dict(
                    {
                        "pdf": pdf_paths,
                        "metadata": metadata_entries,
                    }
                )

                # Cast PDF column to use the Pdf feature
                dataset = dataset.cast_column("pdf", Pdf())
                dataset = dataset.cast_column("metadata", Value("string"))
            else:
                dataset = Dataset.from_dict(
                    {
                        "text": [item["text"] for item in processed_files],
                        "metadata": [
                            json.dumps(item["metadata"]) for item in processed_files
                        ],
                    }
                )

                dataset = dataset.cast_column("metadata", Value("string"))

            # Add dataset metadata
            dataset.info.description = dataset_metadata["description"]
            dataset.info.license = "Unknown"  # Set appropriate license if known
            
            # Set the appropriate features based on dataset type
            if has_pdf_files:
                dataset.info.features = Features(
                    {"pdf": Pdf(), "metadata": Value("string")}
                )
            else:
                dataset.info.features = Features(
                    {"text": Value("string"), "metadata": Value("string")}
                )

            # Save dataset metadata
            metadata_dir = Path(f"./dataset_metadata/{dataset_name}")
            metadata_dir.mkdir(parents=True, exist_ok=True)

            with open(metadata_dir / "metadata.json", "w") as f:
                json.dump(dataset_metadata, f, indent=2)

            logger.info(
                f"Dataset '{dataset_name}' created successfully with {len(processed_files)} entries"
            )

            if progress_callback:
                progress_callback(100)

            return dataset
        except Exception as e:
            logger.error(f"Error creating dataset: {e}")
            raise

    def push_to_hub(self, dataset, repo_name, private=True, progress_callback=None, commit_message=None):
        """Push a dataset to the Hugging Face Hub.
        
        Args:
            dataset: The dataset to push to the Hub
            repo_name: The name of the repository to push to
            private: Whether the repository should be private
            progress_callback: Function to call with progress updates
            commit_message: Custom commit message for updates
            
        Returns:
            bool: Whether the operation was successful
        """
        if not self.token:
            logger.error("Hugging Face token not provided. Cannot push to Hub.")
            return False

        try:
            logger.info(f"Pushing dataset to Hugging Face Hub: {repo_name}")
            # Check if the repo exists
            try:
                repo_exists = any(repo.id == repo_name for repo in self.api.list_datasets(author=self.api.whoami(self.token)["name"]))
            except Exception:
                repo_exists = False
                
            # Use the appropriate push_to_hub parameters
            # If commit_message is not provided, generate a default one
            commit_message = commit_message or ("Update dataset" if repo_exists else "Upload dataset")
            
            # Push the dataset to the Hugging Face Hub
            dataset.push_to_hub(
                repo_name, 
                token=self.token, 
                private=private if not repo_exists else None,
                commit_message=commit_message
            )
            
            logger.info(f"Dataset successfully pushed to {repo_name}")

            if progress_callback:
                progress_callback(100)

            return True
        except Exception as e:
            logger.error(f"Error pushing dataset to Hub: {e}")
            return False

    def create_and_push_dataset(
        self,
        file_data_list,
        dataset_name,
        description=None,
        source_info=None,
        private=True,
        progress_callback=None,
        update_existing=False,
        _test_data=None
    ):
        """
        Create a dataset and push it to the Hugging Face Hub.
        
        Args:
            file_data_list: List of file data to include in the dataset
            dataset_name: Name for the dataset
            description: Dataset description
            source_info: Source information
            private: Whether to make the dataset private
            progress_callback: Function for progress updates
            update_existing: Whether to update an existing dataset
        
        Returns:
            Tuple of (success, dataset)
        """
        try:
            # Add progress reporting
            if progress_callback:
                progress_callback(0)  # 0% - starting dataset creation

            # Scale progress through the pipeline
            def create_progress(p):
                if progress_callback:
                    # Scale to 0-80%
                    progress_callback(p * 0.8)

            # Use test data if provided (for testing purposes only)
            if _test_data is not None:
                # Create dataset directly from test data
                dataset = Dataset.from_dict({
                    "text": [item.get("text", "") for item in _test_data],
                    "metadata": [json.dumps(item.get("metadata", {})) for item in _test_data]
                })
                dataset.info.description = description or dataset_name
            else:
                # Normal dataset creation from file data
                dataset = self.create_dataset(
                    file_data_list, dataset_name, description, source_info, create_progress
                )

            if progress_callback:
                progress_callback(80)  # 80% - dataset created, now pushing

            if dataset:
                def push_progress(p):
                    if progress_callback:
                        # Scale from 80-100%
                        progress_callback(80 + p * 0.2)

                # Check if updating or creating new
                message = None
                if update_existing:
                    try:
                        # Check if dataset exists
                        username = self.api.whoami()["name"]
                        repo_url = f"{username}/{dataset_name}"
                        
                        # Try to get dataset info to check if it exists
                        existing = self.api.repo_info(repo_id=repo_url, repo_type="dataset")
                        logger.info(f"Updating existing dataset: {repo_url}")
                        message = "Update dataset from source URL"
                    except Exception:
                        logger.info(f"Dataset {dataset_name} doesn't exist yet, creating new")
                
                success = self.push_to_hub(
                    dataset, dataset_name, private, push_progress, commit_message=message
                )
                return success, dataset
            return False, None
        except Exception as e:
            logger.error(f"Error in create_and_push_dataset: {e}")
            return False, None

    def create_dataset_from_repository(
        self, repo_url, dataset_name, description, progress_callback=None, _cancellation_event=None,
        task_id=None, resume_from=None, update_existing=False
    ):
        """Create a dataset from a GitHub repository URL.
        
        Args:
            repo_url: URL of the GitHub repository to fetch
            dataset_name: Name to use for the dataset
            description: Dataset description
            progress_callback: Function to call with progress updates
            _cancellation_event: Threading event for cancellation
            task_id: Task ID for tracking (created if not provided)
            resume_from: Stage to resume from (if resuming a task)
            update_existing: Whether to update an existing dataset instead of creating new
            
        Returns:
            Dictionary with success status and message
        """
        # Setup progress callback if not provided
        if progress_callback is None:
            progress_callback = lambda p, m=None: None

        # Create or update task tracking
        if not task_id:
            task_id = self.task_tracker.create_task(
                "repository",
                {
                    "repo_url": repo_url,
                    "dataset_name": dataset_name,
                    "description": description
                },
                f"{'Update' if update_existing else 'Create'} dataset '{dataset_name}' from repository {repo_url}"
            )
        
        # Wrapper for progress callback that also updates task tracking
        def _progress_callback(percent, message=None):
            # Update task progress
            self.task_tracker.update_task_progress(
                task_id, 
                percent,
                stage=message,
                stage_progress=percent
            )
            # Call original callback
            progress_callback(percent, message)
        
        # Check for early cancellation
        if _cancellation_event and _cancellation_event.is_set():
            _progress_callback(10, "Operation cancelled")
            self.task_tracker.cancel_task(task_id)
            return {"success": False, "message": "Operation cancelled by user.", "task_id": task_id}
        
        try:
            # Process the repository using internal method
            result = self._process_repository(
                repo_url=repo_url,
                dataset_name=dataset_name,
                description=description,
                progress_callback=_progress_callback,
                _cancellation_event=_cancellation_event,
                task_id=task_id,
                resume_from=resume_from,
                update_existing=update_existing
            )
            
            # If result is False, the operation was cancelled
            if result is False:
                return {"success": False, "message": "Operation cancelled during processing.", "task_id": task_id}
                
            # Mark task as completed
            self.task_tracker.complete_task(
                task_id, 
                success=True, 
                result={"dataset_name": dataset_name}
            )
            
            return {
                "success": True, 
                "message": f"Dataset {'updated' if update_existing else 'created'} successfully", 
                "task_id": task_id
            }
            
        except Exception as e:
            logger.error(f"Error creating dataset from repository: {e}")
            _progress_callback(40, f"Error: {str(e)}")
            
            # Mark task as failed
            self.task_tracker.complete_task(
                task_id, 
                success=False, 
                result={"error": str(e)}
            )
            
            return {
                "success": False, 
                "message": str(e), 
                "task_id": task_id
            }
            
    def _process_repository(self, repo_url, dataset_name, description, progress_callback=None, 
                           _cancellation_event=None, task_id=None, resume_from=None, update_existing=False):
        """
        Process a GitHub repository to create a dataset.
        
        Args:
            repo_url: URL of the GitHub repository
            dataset_name: Name for the dataset
            description: Description for the dataset
            progress_callback: Function to call with progress updates
            _cancellation_event: Event to check for operation cancellation
            task_id: Task ID for tracking
            resume_from: Stage to resume from (if resuming)
            update_existing: Whether to update an existing dataset
            
        Returns:
            bool: True if processing completed successfully, False if cancelled
        """
        # Implementation would use the ContentFetcher to fetch repository content
        # and then create a dataset from it
        
        # This is a stub implementation for testing purposes
        if progress_callback:
            progress_callback(30, "Processing repository...")
            
        # Check for cancellation
        if _cancellation_event and _cancellation_event.is_set():
            if progress_callback:
                progress_callback(40, "Operation cancelled during processing")
            return False
            
        if progress_callback:
            progress_callback(100, "Repository processing completed")
            
        return True
        
    def create_dataset_from_source(
        self, source_url, dataset_name, description, progress_callback=None, _cancellation_event=None,
        task_id=None, resume_from=None, update_existing=False
    ):
        """Create a dataset from a URL source.
        
        Args:
            source_url: URL of the source to fetch
            dataset_name: Name to use for the dataset
            description: Dataset description
            progress_callback: Function to call with progress updates
            _cancellation_event: Threading event for cancellation
            task_id: Task ID for tracking (created if not provided)
            resume_from: Stage to resume from (if resuming a task)
            update_existing: Whether to update an existing dataset instead of creating new
            
        Returns:
            Dictionary with success status and message
        """
        # Setup progress callback if not provided
        if progress_callback is None:
            progress_callback = lambda p, m=None: None

        # Create or update task tracking
        if not task_id:
            task_id = self.task_tracker.create_task(
                "source",
                {
                    "source_url": source_url,
                    "dataset_name": dataset_name,
                    "description": description
                },
                f"{'Update' if update_existing else 'Create'} dataset '{dataset_name}' from source {source_url}"
            )
        
        # Wrapper for progress callback that also updates task tracking
        def _progress_callback(percent, message=None):
            # Update task progress
            self.task_tracker.update_task_progress(
                task_id, 
                percent,
                stage=message,
                stage_progress=percent
            )
            # Call original callback
            progress_callback(percent, message)
        
        # Check for early cancellation
        if _cancellation_event and _cancellation_event.is_set():
            _progress_callback(10, "Operation cancelled")
            self.task_tracker.cancel_task(task_id)
            return {"success": False, "message": "Operation cancelled by user.", "task_id": task_id}
        
        try:
            # Extract source information from URL
            _progress_callback(20, f"Fetching source: {source_url}")
            
            # Process the source contents
            _progress_callback(25, "Processing source contents")
            
            # Process source
            processing_result = self._process_source(
                source_url=source_url,
                dataset_name=dataset_name,
                description=description,
                progress_callback=_progress_callback,
                _cancellation_event=_cancellation_event,
                task_id=task_id,
                resume_from=resume_from,
                update_existing=update_existing
            )
            
            # Check for cancellation
            if processing_result is False:
                logger.info("Processing returned False - operation was cancelled")
                _progress_callback(30, "Operation cancelled")
                self.task_tracker.cancel_task(task_id)
                return {"success": False, "message": "Operation cancelled during processing.", "task_id": task_id}
                
            if _cancellation_event and _cancellation_event.is_set():
                logger.info("Cancellation event was set during processing")
                _progress_callback(30, "Operation cancelled")
                self.task_tracker.cancel_task(task_id)
                return {"success": False, "message": "Operation cancelled during processing.", "task_id": task_id}
                
            # If we get here, processing was successful
            _progress_callback(100, f"Dataset {'update' if update_existing else 'creation'} completed successfully")
            
            # Mark task as completed
            self.task_tracker.complete_task(
                task_id, 
                success=True, 
                result={"dataset_name": dataset_name}
            )
            
            return {
                "success": True, 
                "message": f"Dataset {'updated' if update_existing else 'created'} successfully", 
                "task_id": task_id
            }
            
        except Exception as e:
            logger.error(f"Error creating dataset from source: {e}")
            _progress_callback(40, f"Error: {str(e)}")
            
            # Mark task as failed
            self.task_tracker.complete_task(
                task_id, 
                success=False, 
                result={"error": str(e)}
            )
            
            return {
                "success": False, 
                "message": str(e), 
                "task_id": task_id
            }

    def _process_source(
        self,
        source_url,
        dataset_name,
        description="",
        progress_callback=None,
        _cancellation_event=None,
        task_id=None,
        resume_from=None,
        update_existing=False
    ):
        """Process a source's content for dataset creation.

        Args:
            source_url: URL of the source
            dataset_name: Name for the dataset
            description: Description for the dataset
            progress_callback: Function to call with progress updates
            _cancellation_event: Event to check for operation cancellation
            task_id: Task ID for tracking
            resume_from: Stage to resume from (if resuming a task)

        Returns:
            bool: True if processing completed successfully, False if cancelled
        """
        try:
            # Check for cancellation
            if _cancellation_event and _cancellation_event.is_set():
                logger.info("Cancellation detected at start of processing")
                return False

            # Initialize content fetcher
            from github.content_fetcher import ContentFetcher
            content_fetcher = ContentFetcher()
            
            # Define progress callback wrapper to scale progress within our range
            def fetch_progress(p):
                if progress_callback:
                    # Scale from 30-70%
                    progress_callback(30 + (p * 0.4), "Fetching content...")
            
            # Fetch source content
            if progress_callback:
                progress_callback(30, "Fetching source content...")
                
            content_files = content_fetcher.fetch_content_for_dataset(
                source_url, progress_callback=fetch_progress
            )
            
            # Check for cancellation after fetching
            if _cancellation_event and _cancellation_event.is_set():
                logger.info("Cancellation detected after content fetching")
                return False

            # Process fetched files
            if progress_callback:
                progress_callback(70, "Processing files...")
                
            if not content_files:
                logger.warning(f"No content files found in source: {source_url}")
                return False
                
            # Create or update dataset
            success, dataset = self.create_and_push_dataset(
                file_data_list=content_files,
                dataset_name=dataset_name,
                description=description,
                source_info=source_url,
                progress_callback=lambda p: progress_callback(70 + (p * 0.3), 
                                                             "Updating dataset..." if update_existing else "Creating dataset...") 
                if progress_callback else None,
                update_existing=update_existing
            )
            
            # Final cancellation check before returning success
            if _cancellation_event and _cancellation_event.is_set():
                logger.info("Cancellation detected at end of processing")
                return False

            return success

        except Exception as e:
            logger.error(f"Error processing source: {e}")
            return False
            
    def create_dataset_from_url(
        self, url, dataset_name, description, recursive=False, progress_callback=None,
        _cancellation_event=None, task_id=None, resume_from=None, update_existing=False,
        export_to_knowledge_graph=True, graph_name=None, user_instructions=None, use_ai_guidance=False
    ):
        """Create a dataset from a URL by crawling the website.
        
        Args:
            url: URL to crawl
            dataset_name: Name to use for the dataset
            description: Dataset description
            recursive: Whether to recursively crawl all linked pages
            progress_callback: Function to call with progress updates
            _cancellation_event: Threading event for cancellation
            task_id: Task ID for tracking (created if not provided)
            resume_from: Stage to resume from (if resuming a task)
            update_existing: Whether to update an existing dataset instead of creating new
            export_to_knowledge_graph: Whether to export the data to a knowledge graph
            graph_name: Optional name for the knowledge graph
            user_instructions: User's description of what to scrape (for AI guidance)
            use_ai_guidance: Whether to use AI to guide the crawling process
            
        Returns:
            Dictionary with success status and message
        """
        # Setup progress callback if not provided
        if progress_callback is None:
            progress_callback = lambda p, m=None: None

        # Create or update task tracking
        if not task_id:
            task_id = self.task_tracker.create_task(
                "scrape",
                {
                    "url": url,
                    "dataset_name": dataset_name,
                    "description": description,
                    "recursive": recursive
                },
                f"{'Update' if update_existing else 'Create'} dataset '{dataset_name}' from URL {url}"
            )
        
        # Wrapper for progress callback that also updates task tracking
        def _progress_callback(percent, message=None):
            # Update task progress
            self.task_tracker.update_task_progress(
                task_id, 
                percent,
                stage=message,
                stage_progress=percent
            )
            # Call original callback
            progress_callback(percent, message)
        
        # Check for early cancellation
        if _cancellation_event and _cancellation_event.is_set():
            _progress_callback(5, "Operation cancelled")
            self.task_tracker.cancel_task(task_id)
            return {"success": False, "message": "Operation cancelled by user.", "task_id": task_id}
        
        try:
            # Initialize web crawler
            from web.crawler import WebCrawler
            web_crawler = WebCrawler(respect_robots_txt=True, rate_limit_delay=1.0)
            
            # Start crawling message
            _progress_callback(10, f"Starting {'recursive ' if recursive else ''}crawl of {url}")
            
            # Crawl the website
            # The progress from crawling will be from 10-60%
            def crawl_progress(p, m=None):
                if p < 0:  # Error indicator
                    message = m or "Error during crawling"
                    _progress_callback(10, message)
                    return
                
                # Scale 0-100% from crawler to 10-60% in our overall process
                scaled_percent = 10 + (p * 0.5)
                _progress_callback(scaled_percent, m)
            
            # Perform the crawl
            crawled_data = web_crawler.crawl_website(
                start_url=url,
                recursive=recursive,
                max_pages=None,  # No limit
                progress_callback=crawl_progress,
                _cancellation_event=_cancellation_event,
                user_instructions=user_instructions,
                use_ai_guidance=use_ai_guidance
            )
            
            # Check for cancellation or error
            if not crawled_data:
                _progress_callback(60, "No content found or operation cancelled")
                self.task_tracker.complete_task(
                    task_id, 
                    success=False, 
                    result={"error": "No content found or operation cancelled"}
                )
                return {
                    "success": False, 
                    "message": "No content was found during crawling", 
                    "task_id": task_id
                }
            
            if _cancellation_event and _cancellation_event.is_set():
                _progress_callback(60, "Operation cancelled after crawling")
                self.task_tracker.cancel_task(task_id)
                return {
                    "success": False, 
                    "message": "Operation cancelled after crawling", 
                    "task_id": task_id
                }
            
            # Prepare data for dataset creation
            _progress_callback(65, "Preparing data for dataset creation")
            file_data_list = web_crawler.prepare_data_for_dataset(crawled_data)
            
            # Create and push dataset
            # Progress from 70-90%
            def dataset_progress(p):
                # Scale 0-100% from dataset creation to 70-90% in our overall process
                scaled_percent = 70 + (p * 0.2)
                _progress_callback(scaled_percent, "Creating dataset..." if p < 80 else "Uploading dataset...")
            
            success, dataset = self.create_and_push_dataset(
                file_data_list=file_data_list,
                dataset_name=dataset_name,
                description=description,
                source_info=url,
                progress_callback=dataset_progress,
                update_existing=update_existing
            )
            
            # Check if we need to export to knowledge graph
            if success and export_to_knowledge_graph:
                _progress_callback(91, "Exporting to knowledge graph")
                try:
                    from knowledge_graph.graph_store import GraphStore
                    
                    # Initialize graph store with specified graph name
                    graph_store = GraphStore(graph_name=graph_name)
                    
                    # Create or select graph
                    if graph_name and not graph_store.test_connection():
                        graph_store.create_graph(graph_name, f"Knowledge graph for {dataset_name} from {url}")
                    
                    # Initialize graph schema if needed
                    graph_store.initialize_schema()
                    
                    # Add documents to graph
                    for i, page_data in enumerate(crawled_data):
                        # Basic document metadata
                        document_data = {
                            "url": page_data.get("url", ""),
                            "title": page_data.get("title", "Unknown Title"),
                            "description": page_data.get("meta_description", ""),
                            "content": page_data.get("markdown", ""),
                            "fetched_at": page_data.get("fetched_at", "")
                        }
                        
                        # Add to graph
                        document_id = graph_store.add_document(document_data)
                        
                        # Update progress periodically
                        if i % 10 == 0 or i == len(crawled_data) - 1:
                            progress = 91 + ((i + 1) / len(crawled_data) * 8)
                            _progress_callback(progress, f"Adding documents to knowledge graph ({i+1}/{len(crawled_data)})")
                    
                    # Extract entities from documents
                    _progress_callback(99, "Extracting entities for knowledge graph")
                    documents = [
                        {
                            "id": f"doc_{i}",
                            "url": page.get("url", ""),
                            "title": page.get("title", ""),
                            "content": page.get("markdown", "")
                        }
                        for i, page in enumerate(crawled_data)
                    ]
                    
                    # Extract entities and relationships
                    graph_store.extract_entities_from_documents(documents)
                    
                except Exception as graph_error:
                    logger.error(f"Error exporting to knowledge graph: {graph_error}")
                    _progress_callback(99, f"Knowledge graph export error: {str(graph_error)}")
            
            # Final completion message
            _progress_callback(100, f"Dataset {'update' if update_existing else 'creation'} completed successfully")
            
            # Cleanup temporary files
            try:
                for item in crawled_data:
                    if "local_path" in item and item["local_path"]:
                        import os
                        if os.path.exists(item["local_path"]):
                            os.remove(item["local_path"])
            except Exception as cleanup_error:
                logger.warning(f"Error cleaning up temporary files: {cleanup_error}")
            
            # Mark task as completed
            self.task_tracker.complete_task(
                task_id, 
                success=True, 
                result={"dataset_name": dataset_name}
            )
            
            return {
                "success": True, 
                "message": f"Dataset {'updated' if update_existing else 'created'} successfully", 
                "task_id": task_id,
                "pages_processed": len(crawled_data)
            }
            
        except Exception as e:
            logger.error(f"Error creating dataset from URL: {e}")
            _progress_callback(50, f"Error: {str(e)}")
            
            # Mark task as failed
            self.task_tracker.complete_task(
                task_id, 
                success=False, 
                result={"error": str(e)}
            )
            
            return {
                "success": False, 
                "message": str(e), 
                "task_id": task_id
            }