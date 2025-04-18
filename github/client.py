import time
import logging
import requests
import random
import threading
import sys
from pathlib import Path
from requests.exceptions import RequestException, ConnectionError, ReadTimeout
from http.client import RemoteDisconnected
from urllib3.exceptions import ProtocolError
# Ensure local import takes precedence over any installed packages
sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import (
    GITHUB_API_URL,
    GITHUB_MAX_RETRIES,
    GITHUB_TIMEOUT,
    GITHUB_DOWNLOAD_RETRIES,
)

logger = logging.getLogger(__name__)


class GitHubAPIError(Exception):
    """Exception raised for GitHub API errors."""

    pass


class RateLimitError(GitHubAPIError):
    """Exception raised when GitHub API rate limit is reached."""

    pass


class GitHubClient:
    """Client for interacting with GitHub API with improved rate limiting."""

    # Class-level lock for thread-safe operation
    _class_lock = threading.RLock()
    # Add this class attribute
    request_lock = threading.Lock()
    
    # Initialize class variables in a thread-safe way
    @classmethod
    def _initialize_class_vars(cls):
        with cls._class_lock:
            if not hasattr(cls, "_initialized"):
                cls.last_request_time = 0
                cls.min_request_interval = 1.0  # Minimum time between requests
                cls.requests_per_hour = 5000  # GitHub's limit for authenticated users
                cls.current_requests = 0
                cls.hour_start_time = time.time()
                cls._initialized = True
    
    # Instance-level lock for this specific client
    # Class-level rate limiting with thread safety

    def __init__(self, token=None):
        # Initialize class variables if not already done
        self._initialize_class_vars()
        
        # Instance variables
        self.token = token
        self.headers = {"Accept": "application/vnd.github.v3+json"}
        if token:
            # GitHub API accepts both formats but "Bearer" is more modern and standard OAuth format
            self.headers["Authorization"] = f"Bearer {token}"
        self.session = requests.Session()
        # Create an instance-level lock for this specific client
        self.request_lock = threading.RLock()

    def get(self, endpoint, params=None):
        """Make a GET request to GitHub API with proper rate limiting."""
        url = f"{GITHUB_API_URL}/{endpoint.lstrip('/')}"
        retries = 0

        # Check hourly rate limit - use class-level lock for shared state
        with GitHubClient._class_lock:
            current_time = time.time()
            elapsed_since_hour_start = current_time - GitHubClient.hour_start_time

            # Reset hourly counter if an hour has passed
            if elapsed_since_hour_start > 3600:
                GitHubClient.hour_start_time = current_time
                GitHubClient.current_requests = 0
                logger.debug("Resetting hourly rate limit counter")

            # If we're approaching the limit, slow down dramatically
            if GitHubClient.current_requests > (GitHubClient.requests_per_hour * 0.9):
                remaining_limit = (
                    GitHubClient.requests_per_hour - GitHubClient.current_requests
                )
                if remaining_limit <= 10:
                    wait_time = max((3600 - elapsed_since_hour_start), 60)
                    logger.warning(
                        f"Rate limit nearly exhausted. Waiting {wait_time:.0f}s."
                    )
                    raise RateLimitError(
                        f"GitHub API rate limit nearly exhausted. Please wait {wait_time/60:.1f} minutes before trying again."
                    )

        while retries < GITHUB_MAX_RETRIES:
            # Apply rate limiting between requests - use instance lock for request timing
            # and class lock for shared counters
            with self.request_lock:
                # First check/update instance-specific rate limit
                current_time = time.time()
                
                # Now update shared class state with proper locking
                with GitHubClient._class_lock:
                    elapsed = current_time - GitHubClient.last_request_time
                    if elapsed < GitHubClient.min_request_interval:
                        sleep_time = GitHubClient.min_request_interval - elapsed
                        logger.debug(
                            f"Rate limiting: waiting {sleep_time:.2f}s before next request"
                        )
                        time.sleep(sleep_time)
    
                    # Update last request time
                    GitHubClient.last_request_time = time.time()
                    GitHubClient.current_requests += 1

            try:
                response = self.session.get(
                    url, headers=self.headers, params=params, timeout=GITHUB_TIMEOUT
                )

                # Check remaining rate limit
                remaining = int(response.headers.get("X-RateLimit-Remaining", "1"))
                if remaining <= 100:
                    logger.warning(
                        f"GitHub API rate limit low: {remaining} requests remaining"
                    )
                    # Slow down even more when we're close to the limit
                    GitHubClient.min_request_interval = max(
                        GitHubClient.min_request_interval, 2.0
                    )

                if response.status_code == 200:
                    return response.json()
                elif (
                    response.status_code == 403
                    and "rate limit exceeded" in response.text.lower()
                ):
                    reset_time = int(response.headers.get("X-RateLimit-Reset", 0))
                    wait_time = max(reset_time - time.time(), 0) + 5  # Add buffer

                    # If wait time is too long, notify the user instead of blocking
                    if wait_time > 120:  # More than 2 minutes
                        message = f"GitHub API rate limit exceeded. Try again after {wait_time/60:.1f} minutes."
                        logger.error(message)
                        raise RateLimitError(message)

                    logger.warning(
                        f"Rate limit exceeded. Waiting for {wait_time:.0f} seconds."
                    )

                    if retries < GITHUB_MAX_RETRIES - 1:
                        time.sleep(min(wait_time, 30))  # Wait max 30 seconds
                        retries += 1
                        continue
                    else:
                        raise RateLimitError(
                            "GitHub API rate limit exceeded. Please try again later."
                        )
                else:
                    try:
                        error_data = response.json()
                        error_message = error_data.get("message", "Unknown error")
                        # Get more detailed error information if available
                        error_docs = error_data.get("documentation_url", "")
                        errors_detail = error_data.get("errors", [])
                        error_detail = ""
                        if errors_detail:
                            error_detail = f", details: {str(errors_detail)}"
                        
                        full_error = f"GitHub API error: {response.status_code} - {error_message}{error_detail}"
                        if error_docs:
                            full_error += f" (docs: {error_docs})"
                            
                        logger.error(full_error)
                        raise GitHubAPIError(full_error)
                    except ValueError:
                        # Handle case when response is not valid JSON
                        error_message = response.text[:200] if response.text else "No response body"
                        logger.error(f"GitHub API error (non-JSON): {response.status_code} - {error_message}")
                        raise GitHubAPIError(f"GitHub API error: {response.status_code} - {error_message}")

            except RequestException as e:
                logger.error(f"Request error: {e}")
                if retries < GITHUB_MAX_RETRIES - 1:
                    retries += 1
                    # Exponential backoff with jitter
                    backoff_time = (2**retries) + (0.1 * random.random())
                    time.sleep(backoff_time)
                    continue
                raise GitHubAPIError(f"Failed to connect to GitHub API: {e}")

        raise GitHubAPIError("Maximum retries reached")

    def get_organization_repos(self, org_name, page=1, per_page=100):
        """Get repositories for a GitHub organization."""
        logger.info(f"Fetching repositories for organization: {org_name}")
        try:
            return self.get(
                f"orgs/{org_name}/repos", {"page": page, "per_page": per_page}
            )
        except GitHubAPIError as e:
            logger.error(f"Failed to fetch repositories for {org_name}: {e}")
            raise

    def get_repository(self, owner, repo):
        """Get a single repository."""
        logger.info(f"Fetching repository: {owner}/{repo}")
        try:
            return self.get(f"repos/{owner}/{repo}")
        except GitHubAPIError as e:
            logger.error(f"Failed to fetch repository {owner}/{repo}: {e}")
            raise

    def get_repository_contents(self, owner, repo, path="", ref=None):
        """Get contents of a repository directory."""
        logger.debug(f"Fetching contents for {owner}/{repo}/{path}")
        params = {}
        if ref:
            params["ref"] = ref

        try:
            return self.get(f"repos/{owner}/{repo}/contents/{path}", params)
        except GitHubAPIError as e:
            logger.error(f"Failed to fetch contents for {owner}/{repo}/{path}: {e}")
            raise
            
    def scan_repository_structure(self, owner, repo, ref=None):
        """
        Scan a repository's directory structure to identify all relevant folders.
        
        Args:
            owner (str): Repository owner
            repo (str): Repository name
            ref (str, optional): Branch or commit reference
            
        Returns:
            dict: Dictionary with relevant paths and file metadata
        """
        logger.info(f"Scanning repository structure for {owner}/{repo}")
        result = {
            "relevant_paths": [],
            "total_files": 0,
            "relevant_files": 0,
            "structure": {}
        }
        
        try:
            # Start with root directory
            self._scan_directory_structure(owner, repo, "", ref, result)
            return result
        except GitHubAPIError as e:
            logger.error(f"Failed to scan repository structure for {owner}/{repo}: {e}")
            raise
            
    def _scan_directory_structure(self, owner, repo, path, ref, result, max_depth=10):
        """Recursively scan directory structure with depth limit."""
        if max_depth <= 0:
            return
            
        try:
            contents = self.get_repository_contents(owner, repo, path, ref)
            
            if not isinstance(contents, list):
                # This is a file, not a directory
                return
                
            current_path = result["structure"]
            if path:
                # Create nested dict structure based on path
                path_parts = path.split("/")
                for part in path_parts:
                    if part not in current_path:
                        current_path[part] = {}
                    current_path = current_path[part]
            
            # Check if this is a relevant folder
            from config.settings import RELEVANT_FOLDERS
            path_parts = path.split("/") if path else []
            is_relevant = any(part.lower() in RELEVANT_FOLDERS for part in path_parts)
            if is_relevant:
                result["relevant_paths"].append(path)
            
            # Process items in this directory
            for item in contents:
                result["total_files"] += 1
                if item["type"] == "dir":
                    # Skip ignored directories
                    from config.settings import IGNORED_DIRS
                    if item["name"] in IGNORED_DIRS:
                        continue
                        
                    # Add directory to structure
                    if "dirs" not in current_path:
                        current_path["dirs"] = []
                    current_path["dirs"].append(item["name"])
                    
                    # Recursively scan subdirectory
                    new_path = f"{path}/{item['name']}" if path else item["name"]
                    self._scan_directory_structure(owner, repo, new_path, ref, result, max_depth - 1)
                elif item["type"] == "file":
                    # Record file in structure
                    if "files" not in current_path:
                        current_path["files"] = []
                    
                    file_info = {
                        "name": item["name"],
                        "path": item["path"],
                        "size": item["size"],
                        "sha": item["sha"],
                        "download_url": item.get("download_url")
                    }
                    current_path["files"].append(file_info)
                    
                    # Check if file is in a relevant folder
                    if is_relevant:
                        # Check file type
                        from config.settings import TEXT_FILE_EXTENSIONS, MAX_FILE_SIZE_MB
                        if (any(item["name"].lower().endswith(ext) for ext in TEXT_FILE_EXTENSIONS) and
                            item["size"] / 1024 / 1024 <= MAX_FILE_SIZE_MB):
                            result["relevant_files"] += 1
        except GitHubAPIError as e:
            logger.warning(f"Error scanning directory {path}: {e}")
            # Continue with other directories even if one fails
            return

    def verify_credentials(self):
        """
        Verify GitHub API credentials by making a lightweight API call.
        
        Returns:
            bool: True if credentials are valid, raises exception otherwise
        """
        logger.debug("Verifying GitHub API credentials")
        try:
            if self.token:
                # If token is provided, get user info
                result = self.get("user")
                logger.info(f"Successfully authenticated with GitHub API as {result.get('login', 'unknown')}")
                return True
            else:
                # If no token, check rate limit as a lightweight API call
                result = self.get("rate_limit")
                logger.info("Successfully connected to GitHub API (unauthenticated)")
                return True
        except GitHubAPIError as e:
            logger.error(f"Failed to verify GitHub credentials: {e}")
            raise

    def get_repository_file(self, owner, repo, path, ref=None):
        """Get the raw content of a file."""
        logger.debug(f"Fetching file content for {owner}/{repo}/{path}")
        content_data = self.get_repository_contents(owner, repo, path, ref)

        if isinstance(content_data, dict) and "download_url" in content_data:
            # Special retry logic for file downloads
            download_retries = GITHUB_DOWNLOAD_RETRIES  # More retries for downloads
            retry_count = 0

            while retry_count < download_retries:
                try:
                    # Apply rate limiting for download as well
                    with GitHubClient.request_lock:
                        current_time = time.time()
                        elapsed = current_time - GitHubClient.last_request_time
                        if elapsed < GitHubClient.min_request_interval:
                            sleep_time = GitHubClient.min_request_interval - elapsed
                            time.sleep(sleep_time)
                        GitHubClient.last_request_time = time.time()

                    download_timeout = (
                        GITHUB_TIMEOUT * 2
                    )  # Double timeout for downloads
                    response = self.session.get(
                        content_data["download_url"], timeout=download_timeout
                    )
                    response.raise_for_status()
                    return response.text
                except (
                    ConnectionError,
                    ReadTimeout,
                    RemoteDisconnected,
                    ProtocolError,
                ) as e:
                    retry_count += 1
                    if retry_count < download_retries:
                        # Exponential backoff with jitter
                        backoff_time = min(30, (2**retry_count) + (random.random() * 2))
                        logger.warning(
                            f"Connection error downloading {path}, "
                            f"retrying in {backoff_time:.2f}s ({retry_count}/{download_retries}): {e}"
                        )
                        time.sleep(backoff_time)
                    else:
                        logger.error(
                            f"Failed to download file after {download_retries} retries: {e}"
                        )
                        raise GitHubAPIError(
                            f"Failed to download file content after {download_retries} retries: {e}"
                        )
                except RequestException as e:
                    logger.error(f"Failed to download file content: {e}")
                    raise GitHubAPIError(f"Failed to download file content: {e}")

            raise GitHubAPIError(f"Maximum retries reached for downloading {path}")
        else:
            raise GitHubAPIError(f"Unexpected content data format for {path}")