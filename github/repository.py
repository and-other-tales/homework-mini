import re
import os
import time
import logging
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
# Ensure local import takes precedence over any installed packages
sys.path.insert(0, str(Path(__file__).parent.parent))
from github.client import GitHubClient, GitHubAPIError
from config.settings import (
    RELEVANT_FOLDERS,
    IGNORED_DIRS,
    TEXT_FILE_EXTENSIONS,
    MAX_FILE_SIZE_MB,
    GITHUB_DEFAULT_BRANCH,
    CACHE_DIR,
)

logger = logging.getLogger(__name__)


class DownloadQueue:
    """Manages a queue of files to download with progress tracking."""
    
    def __init__(self):
        """Initialize an empty download queue."""
        self.queue = []
        self.total_files = 0
        self.processed_files = 0
        self.start_time = None
        self.processing_history = []  # Track processing rate history
        self.history_window = 20  # Number of samples to keep for rate calculation
        
    def __repr__(self):
        """String representation for debugging."""
        return f"DownloadQueue(total={self.total_files}, processed={self.processed_files}, queue_len={len(self.queue)})"
        
    def add_file(self, file_info):
        """Add a file to the download queue."""
        self.queue.append(file_info)
        self.total_files += 1
        
    def add_files(self, file_list):
        """Add multiple files to the download queue."""
        self.queue.extend(file_list)
        self.total_files += len(file_list)
        
    def get_next_file(self):
        """Get the next file from the queue, or None if empty."""
        if not self.queue:
            return None
        return self.queue.pop(0)
        
    def mark_processed(self):
        """Mark a file as processed and update metrics."""
        self.processed_files += 1
        
        # Record processing rate for time estimation
        current_time = time.time()
        if not self.start_time:
            self.start_time = current_time
            
        if len(self.processing_history) >= self.history_window:
            self.processing_history.pop(0)  # Remove oldest entry
            
        self.processing_history.append(current_time)
        
    def get_progress(self):
        """
        Get the current progress statistics.
        
        Returns:
            dict: Progress information including percentage, files remaining, and estimated time
        """
        if self.total_files == 0:
            return {
                "percent": 0,
                "files_processed": 0,
                "files_total": 0,
                "files_remaining": 0,
                "time_elapsed": 0,
                "time_remaining": "Unknown",
                "status": "No files to process"
            }
            
        percent = (self.processed_files / self.total_files) * 100
        files_remaining = self.total_files - self.processed_files
        
        # Calculate time elapsed
        current_time = time.time()
        time_elapsed = 0 if not self.start_time else current_time - self.start_time
        
        # Estimate time remaining
        if len(self.processing_history) >= 2 and self.processed_files > 0:
            # Calculate processing rate based on recent history
            first_time = self.processing_history[0]
            last_time = self.processing_history[-1]
            if last_time > first_time:  # Avoid division by zero
                recent_rate = len(self.processing_history) / (last_time - first_time)  # files per second
                time_remaining_sec = files_remaining / recent_rate if recent_rate > 0 else float('inf')
                
                # Format time remaining
                if time_remaining_sec == float('inf'):
                    time_remaining = "Unknown"
                elif time_remaining_sec < 60:
                    time_remaining = f"{int(time_remaining_sec)}s"
                elif time_remaining_sec < 3600:
                    time_remaining = f"{int(time_remaining_sec / 60)}m {int(time_remaining_sec % 60)}s"
                else:
                    hours = int(time_remaining_sec / 3600)
                    minutes = int((time_remaining_sec % 3600) / 60)
                    time_remaining = f"{hours}h {minutes}m"
            else:
                time_remaining = "Calculating..."
        else:
            time_remaining = "Calculating..."
            
        return {
            "percent": percent,
            "files_processed": self.processed_files,
            "files_total": self.total_files,
            "files_remaining": files_remaining,
            "time_elapsed": time_elapsed,
            "time_remaining": time_remaining,
            "status": "In progress" if files_remaining > 0 else "Complete"
        }
        
    def get_status_message(self):
        """Get a formatted status message for console display."""
        progress = self.get_progress()
        
        if progress["files_total"] == 0:
            return "No files to process"
            
        return (f"Downloading: {progress['files_total']} Files, "
                f"{progress['percent']:.1f}% Complete "
                f"({progress['files_processed']}/{progress['files_total']}) "
                f"[{progress['time_remaining']} Remaining]")
                
    def is_empty(self):
        """Check if the queue is empty."""
        return len(self.queue) == 0
        
    def reset(self):
        """Reset the queue and all metrics."""
        self.queue = []
        self.total_files = 0
        self.processed_files = 0
        self.start_time = None
        self.processing_history = []

class RepositoryFetcher:
    """Handles fetching repositories and their contents from GitHub.
    
    This class provides methods to interact with GitHub repositories,
    fetch content, and manage the download process with proper rate limiting
    and error handling. It supports fetching both single repositories and 
    multiple repositories from an organization.
    
    Attributes:
        client (GitHubClient): Client for GitHub API interaction
        cache_dir (Path): Directory for caching downloaded files
        download_queue (DownloadQueue): Queue for managing file downloads
        file_patterns (list): Glob patterns to include when fetching files
        exclude_patterns (list): Glob patterns to exclude when fetching files
        include_directories (list): Directories to prioritize when fetching
        exclude_directories (list): Directories to exclude when fetching
        priority_content (list): Keywords or patterns to prioritize
    """

    def __init__(self, github_token=None, client=None):
        """Initialize the repository fetcher.

        Args:
            github_token (str, optional): GitHub token for authentication
            client (GitHubClient, optional): Existing GitHub client to use
            
        Raises:
            GitHubAPIError: If there's an error authenticating with GitHub
        """
        self.client = client if client is not None else GitHubClient(token=github_token)
        self.cache_dir = CACHE_DIR
        self.download_queue = DownloadQueue()  # Initialize download queue
        
        # AI guidance settings (can be set by ContentFetcher before fetching)
        self.file_patterns = []       # List of glob patterns to prioritize
        self.exclude_patterns = []    # List of glob patterns to exclude
        self.include_directories = [] # List of directories to prioritize
        self.exclude_directories = [] # List of directories to exclude
        self.priority_content = []    # Keywords or patterns to prioritize
        
        # Ensure cache directory exists with proper permissions
        try:
            if not self.cache_dir.exists():
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                
                # Try to set secure permissions on Unix systems
                try:
                    import stat
                    import os
                    os.chmod(self.cache_dir, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
                except Exception as e:
                    logger.warning(f"Could not set secure permissions on cache directory: {e}")
        except Exception as e:
            logger.error(f"Error creating cache directory: {e}")
            # Continue anyway, we'll handle directory errors during operations

    def fetch_organization_repos(self, org_name):
        """Fetch all repositories for an organization."""
        logger.info(f"Fetching repositories for organization: {org_name}")
        repos = []
        page = 1

        while True:
            batch = self.client.get_organization_repos(org_name, page=page)
            if not batch:
                break

            repos.extend(batch)
            if len(batch) < 100:  # Less than max per page, we're done
                break

            page += 1

        logger.info(f"Found {len(repos)} repositories for {org_name}")
        return repos

    def fetch_single_repo(self, repo_url):
        """Fetch a single repository from its URL."""
        # Check if this is an organization URL (no second path part)
        org_match = re.match(r"https?://github\.com/([^/]+)/?$", repo_url)
        if org_match:
            # This is an organization URL
            org_name = org_match.group(1)
            raise ValueError(f"Organization URL detected: {repo_url}. Use fetch_organization_repos instead")
            
        # Parse owner and repo from URL
        match = re.match(r"https?://github\.com/([^/]+)/([^/]+)", repo_url)
        if not match:
            raise ValueError(f"Invalid GitHub repository URL: {repo_url}")

        owner, repo = match.groups()
        repo = repo.rstrip(".git")

        logger.info(f"Fetching repository: {owner}/{repo}")
        return self.client.get_repository(owner, repo)

    def fetch_relevant_content(self, owner, repo, branch=None, progress_callback=None, 
                            _cancellation_event=None, max_files=None, ai_instructions=None):
        """
        Recursively fetch relevant content from a repository.
        Focuses on documentation, examples, samples, and cookbook folders.
        Uses a two-phase approach: first scan for all relevant files, then download them.
        
        Args:
            owner: Repository owner
            repo: Repository name
            branch: Branch to fetch
            progress_callback: Function to call with progress updates
            _cancellation_event: Event that can be set to cancel the operation
            max_files: Maximum number of files to fetch (optional limit)
            ai_instructions: AI-guided instructions for repository fetching (optional)
            
        Returns:
            List of content files
        """
        # Apply AI instructions if provided
        if ai_instructions:
            logger.info(f"Applying AI instructions for fetching from {owner}/{repo}")
            # Log AI guidance settings
            if "file_patterns" in ai_instructions and ai_instructions["file_patterns"]:
                logger.info(f"Using file patterns: {ai_instructions['file_patterns']}")
            if "exclude_patterns" in ai_instructions and ai_instructions["exclude_patterns"]:
                logger.info(f"Using exclude patterns: {ai_instructions['exclude_patterns']}")
            if "include_directories" in ai_instructions and ai_instructions["include_directories"]:
                logger.info(f"Using include directories: {ai_instructions['include_directories']}")
            if "exclude_directories" in ai_instructions and ai_instructions["exclude_directories"]:
                logger.info(f"Using exclude directories: {ai_instructions['exclude_directories']}")
            if "max_files" in ai_instructions and ai_instructions["max_files"]:
                logger.info(f"Using max files: {ai_instructions['max_files']}")
                if max_files is None or ai_instructions["max_files"] < max_files:
                    max_files = ai_instructions["max_files"]
        if not branch:
            try:
                repo_info = self.client.get_repository(owner, repo)
                branch = repo_info.get("default_branch", GITHUB_DEFAULT_BRANCH)
            except GitHubAPIError:
                branch = GITHUB_DEFAULT_BRANCH

        logger.info(f"Fetching relevant content from {owner}/{repo} (branch: {branch})")

        # Create repository cache directory
        repo_cache_dir = self.cache_dir / owner / repo
        repo_cache_dir.mkdir(parents=True, exist_ok=True)

        # Indicate progress started
        if progress_callback:
            progress_callback(5)
            
        # Check for early cancellation
        if _cancellation_event and _cancellation_event.is_set():
            logger.info(f"Operation cancelled before scanning repository structure for {owner}/{repo}")
            return []
            
        # Phase 1: Scan the repository to identify all relevant files without downloading
        try:
            repo_structure = self.client.scan_repository_structure(owner, repo, branch)
            
            # Check for cancellation after scanning
            if _cancellation_event and _cancellation_event.is_set():
                logger.info(f"Operation cancelled after scanning repository structure for {owner}/{repo}")
                return []
            
            # Update progress after scanning
            if progress_callback:
                progress_callback(15)
                
            logger.info(f"Scanned repository structure for {owner}/{repo}: "
                        f"Found {repo_structure['total_files']} total files, "
                        f"{repo_structure['relevant_files']} relevant files, "
                        f"{len(repo_structure['relevant_paths'])} relevant paths")
                        
            # Phase 2: Build a download queue from the scan results
            self.download_queue.reset()  # Clear any existing queue
            
            # Create a file list from all relevant paths
            all_file_items = []
            for path in repo_structure['relevant_paths']:
                # Check for cancellation during path processing
                if _cancellation_event and _cancellation_event.is_set():
                    logger.info(f"Operation cancelled during path processing for {owner}/{repo}")
                    return []
                    
                logger.debug(f"Preparing to fetch files from relevant path: {path}")
                files_to_download = self._identify_files_to_download(
                    repo_structure, path, owner, repo, branch, repo_cache_dir
                )
                all_file_items.extend(files_to_download)
                
            if not all_file_items:
                logger.warning(f"No relevant files found in {owner}/{repo}")
                return []
                
            # Add all files to the download queue
            self.download_queue.add_files(all_file_items)
            
            # Update progress now that queue is prepared
            if progress_callback:
                progress_callback(20)
                
            # Phase 3: Download all queued files
            return self._download_queued_files(owner, repo, branch, progress_callback, _cancellation_event, max_files)
            
        except GitHubAPIError as e:
            logger.error(f"Error scanning repository structure: {e}")
            # Fall back to the original recursive approach if scanning fails
            logger.warning("Falling back to direct recursive fetch")
            return self._fetch_directory_content(
                owner, repo, "", branch, repo_cache_dir, progress_callback, _cancellation_event
            )

    def _fetch_directory_content(
        self, owner, repo, path, branch, base_dir, progress_callback=None, _cancellation_event=None
    ):
        """
        Recursively fetch content from a directory with improved rate limiting.
        
        Args:
            owner: Repository owner
            repo: Repository name
            path: Path to fetch
            branch: Branch to use
            base_dir: Base directory to save files
            progress_callback: Function to call with progress updates
            _cancellation_event: Event that can be set to cancel the operation
            
        Returns:
            List of file data
        """
        # Check for cancellation
        if _cancellation_event and _cancellation_event.is_set():
            logger.info(f"Operation cancelled before fetching directory {path}")
            return []
            
        try:
            contents = self.client.get_repository_contents(owner, repo, path, branch)
        except GitHubAPIError as e:
            logger.error(f"Error fetching directory {path}: {e}")
            return []

        if not isinstance(contents, list):
            logger.warning(f"Expected directory content but got a file: {path}")
            return []

        # Process this directory's contents
        files_data = []
        subdirs_to_process = []

        # Indicate progress for this directory
        if progress_callback and not path:  # Only for root directory
            progress_callback(20)

        # Check for cancellation
        if _cancellation_event and _cancellation_event.is_set():
            logger.info(f"Operation cancelled after fetching directory list for {path}")
            return []

        for item in contents:
            item_name = item["name"]
            item_path = item["path"]
            item_type = item["type"]

            # Skip ignored directories
            if item_type == "dir" and item_name in IGNORED_DIRS:
                continue

            # Process directories
            if item_type == "dir":
                # Check if this is a relevant directory we want to process
                if self._is_relevant_folder(item_name) or self._is_relevant_folder(
                    path
                ):
                    subdirs_to_process.append((item_path, Path(base_dir) / item_name))
                # Otherwise, check if any parent directory is relevant
                elif path and any(
                    part for part in path.split("/") if self._is_relevant_folder(part)
                ):
                    subdirs_to_process.append((item_path, Path(base_dir) / item_name))

            # Process files (only in relevant directories)
            elif item_type == "file" and (
                self._is_relevant_folder(path)
                or any(
                    part for part in path.split("/") if self._is_relevant_folder(part)
                )
            ):
                if (
                    self._is_text_file(item_name)
                    and item["size"] / 1024 / 1024 <= MAX_FILE_SIZE_MB
                ):
                    # Process file
                    file_data = self._process_file(owner, repo, item, branch, base_dir)
                    files_data.append(file_data)

        # Update progress again after processing this directory
        if progress_callback and not path:  # Only for root directory
            progress_callback(30)
            
        # Check for cancellation before starting subdirectory processing
        if _cancellation_event and _cancellation_event.is_set():
            logger.info(f"Operation cancelled before processing subdirectories for {path}")
            return files_data  # Return what we've processed so far

        # Use ThreadPoolExecutor with fewer workers (3 instead of 10)
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = []
            for subdir_path, subdir_local in subdirs_to_process:
                subdir_local.mkdir(parents=True, exist_ok=True)
                futures.append(
                    executor.submit(
                        self._fetch_directory_content,
                        owner,
                        repo,
                        subdir_path,
                        branch,
                        subdir_local,
                        progress_callback,
                        _cancellation_event
                    )
                )

            # Collect results from all futures
            for future in futures:
                # Check for cancellation during future processing
                if _cancellation_event and _cancellation_event.is_set():
                    logger.info(f"Operation cancelled during subdirectory processing for {path}")
                    executor.shutdown(wait=False)
                    return files_data  # Return what we've processed so far
                    
                try:
                    result = future.result()
                    files_data.extend(result)
                except Exception as e:
                    logger.error(f"Error in directory fetch: {e}")
                    # Continue with other directories even if one fails

        # Final progress update when finished
        if progress_callback and not path:  # Only for root directory
            progress_callback(80)

        return files_data

    def _process_file(self, owner, repo, file_info, branch, base_dir):
        """Process a single file and save it to cache."""
        try:
            file_content = self.client.get_repository_file(
                owner, repo, file_info["path"], branch
            )
            file_path = Path(base_dir) / file_info["name"]

            # Save to cache
            file_path.write_text(file_content, encoding="utf-8", errors="replace")

            return {
                "name": file_info["name"],
                "path": file_info["path"],
                "sha": file_info["sha"],
                "size": file_info["size"],
                "url": file_info["html_url"],
                "local_path": str(file_path),
                "repo": f"{owner}/{repo}",
                "branch": branch,
            }
        except Exception as e:
            logger.error(f"Error processing file {file_info['path']}: {e}")
            # For large files, create a placeholder with file info but mark as error
            try:
                # Create an error file to indicate download failure
                error_file_path = Path(base_dir) / f"{file_info['name']}.error"
                error_file_path.write_text(
                    f"Error downloading: {str(e)}", encoding="utf-8"
                )
            except Exception:
                pass

            return {
                "name": file_info["name"],
                "path": file_info["path"],
                "error": str(e),
                "repo": f"{owner}/{repo}",
                "branch": branch,
                "size": file_info.get("size", 0),
            }

    def _is_relevant_folder(self, folder_name):
        """
        Check if a folder is relevant based on predefined folders and AI guidance.
        
        Args:
            folder_name: Name of the folder to check
            
        Returns:
            bool: True if the folder is relevant, False otherwise
        """
        folder_lower = folder_name.lower()
        
        # Always exclude specific directories, regardless of AI settings
        if folder_lower in IGNORED_DIRS:
            return False
            
        # Check if this folder is in the AI-guided exclude list
        if self.exclude_directories and any(
            excluded_dir.lower() == folder_lower 
            for excluded_dir in self.exclude_directories
        ):
            logger.debug(f"Excluding directory {folder_name} based on AI guidance")
            return False
            
        # First, check if this folder is in the AI-guided include list (highest priority)
        if self.include_directories and any(
            included_dir.lower() == folder_lower
            for included_dir in self.include_directories
        ):
            logger.debug(f"Including directory {folder_name} based on AI guidance")
            return True
            
        # Then check against the predefined list of relevant folders
        return any(relevant in folder_lower for relevant in RELEVANT_FOLDERS)

    def _is_text_file(self, filename):
        """
        Check if a file is a text file based on extension and AI-guided patterns.
        
        Args:
            filename: Name of the file to check
            
        Returns:
            bool: True if the file should be included, False otherwise
        """
        # Basic text file check
        is_text = any(filename.lower().endswith(ext) for ext in TEXT_FILE_EXTENSIONS)
        
        # If we have AI-guided file patterns, apply them
        if self.file_patterns or self.exclude_patterns:
            # Check exclude patterns first (higher priority than include)
            if self.exclude_patterns:
                import fnmatch
                if any(fnmatch.fnmatch(filename.lower(), pattern.lower()) 
                      for pattern in self.exclude_patterns):
                    logger.debug(f"Excluding file {filename} based on AI guidance patterns")
                    return False
            
            # If we have include patterns, they override the default text check
            if self.file_patterns:
                import fnmatch
                matches = any(fnmatch.fnmatch(filename.lower(), pattern.lower()) 
                             for pattern in self.file_patterns)
                return matches
        
        # Fall back to basic text file check if no patterns match
        return is_text

    def _identify_files_to_download(self, repo_structure, path, owner, repo, branch, base_dir):
        """
        Identify files to download from a specific path based on the repository structure.
        
        Args:
            repo_structure (dict): Repository structure from scan_repository_structure
            path (str): Path to process
            owner (str): Repository owner
            repo (str): Repository name
            branch (str): Branch to use
            base_dir (Path): Base directory for local storage
            
        Returns:
            list: List of file items to download
        """
        # Find this path in the structure
        current_path = repo_structure["structure"]
        if path:
            try:
                for part in path.split("/"):
                    current_path = current_path.get(part, {})
            except (KeyError, AttributeError):
                logger.warning(f"Path {path} not found in repository structure")
                return []
                
        # Extract files from this path
        files_to_download = []
        if "files" in current_path and isinstance(current_path["files"], list):
            for file_info in current_path["files"]:
                # Check if this is a text file we want to download
                if (self._is_text_file(file_info["name"]) and 
                    file_info["size"] / 1024 / 1024 <= MAX_FILE_SIZE_MB):
                    
                    # Create local path
                    file_path = Path(base_dir)
                    if path:
                        file_path = file_path / path
                    file_path = file_path / file_info["name"]
                    
                    # Add file to download queue
                    download_item = {
                        "owner": owner,
                        "repo": repo,
                        "path": file_info["path"],
                        "branch": branch,
                        "sha": file_info["sha"],
                        "name": file_info["name"],
                        "size": file_info["size"],
                        "local_path": str(file_path),
                        "url": file_info.get("download_url", ""),
                    }
                    files_to_download.append(download_item)
        
        return files_to_download
        
    def _download_queued_files(self, owner, repo, branch, progress_callback=None, _cancellation_event=None, max_files=None):
        """
        Download all files in the queue with progress tracking.
        
        Args:
            owner (str): Repository owner
            repo (str): Repository name
            branch (str): Branch to use
            progress_callback (function): Progress callback function
            _cancellation_event (Event): Event that can be set to cancel the operation
            max_files (int, optional): Maximum number of files to download
            
        Returns:
            list: List of downloaded file data
        """
        queue = self.download_queue
        total_files = queue.total_files
        
        if total_files == 0:
            logger.warning(f"No files to download for {owner}/{repo}")
            return []
            
        logger.info(f"Downloading {total_files} files from {owner}/{repo}")
        
        # Check for cancellation before starting downloads
        if _cancellation_event and _cancellation_event.is_set():
            logger.info(f"Operation cancelled before file download for {owner}/{repo}")
            return []
        
        # Start with initial progress
        if progress_callback:
            progress_callback(25)  # We're at 25% after scanning and queueing
            
        # Prepare for parallel downloads
        with ThreadPoolExecutor(max_workers=3) as executor:
            # Process files in batches for better progress tracking
            batch_size = 5
            downloaded_files = []
            last_progress_update = time.time()
            progress_update_interval = 0.5  # Update status at most every 0.5 seconds
            
            # Apply max_files limit if specified
            if max_files is not None and max_files > 0:
                logger.info(f"Limiting download to {max_files} files based on AI guidance")
                # Trim the queue to respect max_files
                if len(queue.queue) > max_files:
                    # Sort queue by priority if we have priority_content settings
                    if self.priority_content:
                        # Utility function to score a file based on priority keywords
                        def priority_score(file_item):
                            score = 0
                            path = file_item.get("path", "").lower()
                            for i, keyword in enumerate(self.priority_content):
                                if keyword.lower() in path:
                                    # Higher priority for earlier keywords in the list
                                    score += (len(self.priority_content) - i)
                            return score
                            
                        # Sort queue by priority score
                        queue.queue.sort(key=priority_score, reverse=True)
                        
                    # Trim queue to max_files
                    queue.queue = queue.queue[:max_files]
                    queue.total_files = len(queue.queue)
                    logger.info(f"Queue trimmed to {len(queue.queue)} files based on max_files limit")
            
            while not queue.is_empty():
                # Check for cancellation before each batch
                if _cancellation_event and _cancellation_event.is_set():
                    logger.info(f"Operation cancelled during file download for {owner}/{repo}")
                    executor.shutdown(wait=False)
                    return downloaded_files  # Return what we've got so far
                
                batch = []
                for _ in range(min(batch_size, len(queue.queue))):
                    next_file = queue.get_next_file()
                    if next_file:
                        batch.append(next_file)
                
                # Submit batch for download
                futures = []
                for file_item in batch:
                    futures.append(executor.submit(
                        self._download_single_file, 
                        file_item["owner"],
                        file_item["repo"],
                        file_item["path"],
                        file_item["branch"],
                        file_item["local_path"]
                    ))
                
                # Process results
                for i, future in enumerate(futures):
                    # Check for cancellation during future processing
                    if _cancellation_event and _cancellation_event.is_set():
                        logger.info(f"Operation cancelled while processing download futures for {owner}/{repo}")
                        executor.shutdown(wait=False)
                        return downloaded_files  # Return what we've got so far
                    
                    try:
                        result = future.result()
                        if result:
                            downloaded_files.append(result)
                        queue.mark_processed()
                    except Exception as e:
                        logger.error(f"Error downloading file: {e}")
                        queue.mark_processed()  # Still mark as processed to update progress
                
                # Update progress callback (but not too frequently)
                current_time = time.time()
                if current_time - last_progress_update >= progress_update_interval:
                    progress_info = queue.get_progress()
                    logger.debug(queue.get_status_message())
                    
                    if progress_callback:
                        # Map our queue progress (0-100%) to the expected progress range (25-90%)
                        callback_progress = 25 + (progress_info["percent"] * 0.65)
                        progress_callback(min(90, callback_progress))
                        
                    last_progress_update = current_time
        
        # Final check for cancellation
        if _cancellation_event and _cancellation_event.is_set():
            logger.info(f"Operation cancelled at end of download phase for {owner}/{repo}")
            return downloaded_files
        
        # Final progress update
        if progress_callback:
            progress_callback(95)
            
        logger.info(f"Downloaded {len(downloaded_files)} files from {owner}/{repo}")
        return downloaded_files
        
    def _download_single_file(self, owner, repo, path, branch, local_path):
        """
        Download a single file and save it locally.
        
        Args:
            owner (str): Repository owner
            repo (str): Repository name
            path (str): File path
            branch (str): Branch to use
            local_path (str): Local path to save the file
            
        Returns:
            dict: File information or None on failure
        """
        try:
            # Ensure parent directory exists
            Path(local_path).parent.mkdir(parents=True, exist_ok=True)
            
            # Download file
            file_content = self.client.get_repository_file(owner, repo, path, branch)
            
            # Save file locally
            Path(local_path).write_text(file_content, encoding="utf-8", errors="replace")
            
            return {
                "name": Path(path).name,
                "path": path,
                "local_path": local_path,
                "repo": f"{owner}/{repo}",
                "branch": branch,
                "size": len(file_content),
            }
        except Exception as e:
            logger.error(f"Error downloading file {path}: {e}")
            # Create error marker file
            try:
                error_path = f"{local_path}.error"
                Path(error_path).write_text(f"Error downloading: {str(e)}", encoding="utf-8")
            except Exception:
                pass
            return None
    
    def _is_pdf_file(self, filename):
        """Check if a file is a PDF file based on extension."""
        return filename.lower().endswith(".pdf")

    def _process_pdf_folder_structure(self, base_dir):
        """Process directory structure to extract PDF labels from folder names."""
        pdf_data = []
        base_path = Path(base_dir)
        
        # Walk the directory structure
        for root, dirs, files in os.walk(base_path):
            # Skip ignored directories
            if any(ignored in root.split(os.sep) for ignored in IGNORED_DIRS):
                continue
                
            # Extract PDF files
            for file in files:
                if file.lower().endswith('.pdf'):
                    file_path = Path(root) / file
                    rel_path = file_path.relative_to(base_path)
                    
                    # Extract labels from directory structure
                    path_parts = rel_path.parent.parts
                    labels = [part for part in path_parts if self._is_relevant_folder(part)]
                    
                    pdf_data.append({
                        "file_path": str(file_path),
                        "relative_path": str(rel_path),
                        "labels": labels,
                        "filename": file,
                        "directory": str(rel_path.parent)
                    })
        
        return pdf_data