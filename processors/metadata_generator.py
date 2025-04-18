import logging
import hashlib
import json
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class MetadataGenerator:
    """Generate metadata for datasets and files."""

    def generate_dataset_metadata(self, source_info, file_count):
        """Generate metadata for a dataset."""
        timestamp = datetime.now().isoformat()

        if isinstance(source_info, str):
            # Check if this is a GitHub repository URL
            if "github.com" in source_info.lower():
                source_type = "repository"
                # Extract repository name from URL (last part after the last /)
                import re
                repo_match = re.search(r'github\.com/[^/]+/([^/]+)', source_info)
                if repo_match:
                    source_name = repo_match.group(1)
                else:
                    source_name = source_info
            else:
                source_type = "url"
                source_name = source_info
        else:
            # Check if this is a repository dictionary from GitHub API
            if "full_name" in source_info:
                source_type = "repository"
                source_name = source_info.get("full_name", "unknown")
            else:
                source_type = "custom"
                source_name = source_info.get("name", "unknown")

        # Build the description with the appropriate prefix for GitHub repositories
        description = (
            f"Dataset created from GitHub repository {source_name}" 
            if source_type == "repository" 
            else f"Dataset created from {source_type} {source_name}"
        )

        return {
            "created_at": timestamp,
            "source_type": source_type,
            "source_name": source_name,
            "file_count": file_count,
            "creator": "homework_dataset_creator",
            "version": "1.0",
            "description": description,
        }

    def generate_file_metadata(self, file_data):
        """Generate metadata for a specific file."""
        if "local_path" not in file_data:
            return {
                "filename": file_data.get("name", "unknown"),
                "path": file_data.get("path", "unknown"),
                "repo": file_data.get("repo", "unknown"),
                "error": file_data.get("error", "Unknown error"),
            }

        file_path = Path(file_data["local_path"])

        try:
            file_content = file_path.read_bytes()
            file_hash = hashlib.sha256(file_content).hexdigest()
            file_stats = file_path.stat()

            return {
                "filename": file_data["name"],
                "path": file_data["path"],
                "repo": file_data["repo"],
                "sha": file_data.get("sha", ""),
                "size_bytes": file_stats.st_size,
                "hash": file_hash,
                "last_modified": datetime.fromtimestamp(
                    file_stats.st_mtime
                ).isoformat(),
                "url": file_data.get("url", ""),
                "extension": file_path.suffix,
            }
        except Exception as e:
            logger.error(f"Error generating metadata for {file_path}: {e}")
            return {
                "filename": file_data["name"],
                "path": file_data["path"],
                "repo": file_data["repo"],
                "error": str(e),
            }

    def generate_repo_structure_metadata(self, file_data_list):
        """Generate metadata about the repository structure."""
        repos = {}

        for file_data in file_data_list:
            repo_name = file_data.get("repo", "unknown")
            if repo_name not in repos:
                repos[repo_name] = {
                    "file_count": 0,
                    "total_size_bytes": 0,
                    "file_types": {},
                    "directories": set(),
                }

            repo_info = repos[repo_name]
            repo_info["file_count"] += 1

            if "size" in file_data:
                repo_info["total_size_bytes"] += file_data["size"]

            file_path = file_data.get("path", "")
            if file_path:
                # Track directories
                parts = file_path.split("/")
                for i in range(len(parts) - 1):
                    dir_path = "/".join(parts[: i + 1])
                    if dir_path:
                        repo_info["directories"].add(dir_path)

                # Track file types
                extension = Path(file_path).suffix.lower()
                if extension:
                    repo_info["file_types"][extension] = (
                        repo_info["file_types"].get(extension, 0) + 1
                    )

        # Convert sets to lists for JSON serialization
        for repo_name, repo_info in repos.items():
            repo_info["directories"] = sorted(list(repo_info["directories"]))

        return repos
