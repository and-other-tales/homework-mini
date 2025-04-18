import logging
import json
from huggingface_hub import HfApi, HfFolder, DatasetCard, DatasetCardData
from pathlib import Path

logger = logging.getLogger(__name__)


class DatasetManager:
    """Manage existing datasets on Hugging Face Hub."""

    def __init__(self, huggingface_token=None, credentials_manager=None):
        self.credentials_manager = credentials_manager
        
        if credentials_manager:
            _, self.token = credentials_manager.get_huggingface_credentials()
        else:
            self.token = huggingface_token
            
        self.api = HfApi()
        if self.token:
            HfFolder.save_token(self.token)

    def list_datasets(self, username=None):
        """List datasets for the authenticated user or specified username."""
        try:
            if username:
                logger.info(f"Listing datasets for user: {username}")
                datasets = self.api.list_datasets(author=username)
            else:
                # List datasets for the authenticated user
                if not self.token:
                    logger.error(
                        "No Hugging Face token provided. Cannot list datasets."
                    )
                    return []
                whoami = self.api.whoami(self.token)
                username = whoami["name"]
                logger.info(f"Listing datasets for authenticated user: {username}")
                datasets = self.api.list_datasets(author=username)

            logger.info(f"Found {len(datasets)} datasets")
            return datasets
        except Exception as e:
            logger.error(f"Error listing datasets: {e}")
            return []

    def get_dataset_info(self, dataset_name):
        """Get information about a specific dataset."""
        try:
            logger.info(f"Getting info for dataset: {dataset_name}")
            info = self.api.dataset_info(dataset_name)
            return info
        except Exception as e:
            logger.error(f"Error getting dataset info for {dataset_name}: {e}")
            return None

    def delete_dataset(self, dataset_name):
        """Delete a dataset from Hugging Face Hub.
        
        Args:
            dataset_name (str): The name of the dataset to delete in format 'username/dataset_name'
            
        Returns:
            bool: Whether the deletion was successful
        """
        if not self.token:
            logger.error("No Hugging Face token provided. Cannot delete dataset.")
            return False

        try:
            logger.info(f"Deleting dataset: {dataset_name}")
            self.api.delete_repo(dataset_name, repo_type="dataset", token=self.token)
            logger.info(f"Dataset {dataset_name} deleted successfully")
            return True
        except Exception as e:
            logger.error(f"Error deleting dataset {dataset_name}: {e}")
            return False

    def download_dataset_metadata(self, dataset_name, output_dir=None):
        """Download dataset metadata.
        
        Args:
            dataset_name (str): The name of the dataset to download metadata for
            output_dir (Path, optional): The directory to save the metadata to
            
        Returns:
            bool: Whether the metadata was successfully downloaded
        """
        try:
            if not output_dir:
                output_dir = Path(f"./dataset_metadata/{dataset_name}")
                output_dir.mkdir(parents=True, exist_ok=True)

            logger.info(f"Downloading metadata for dataset: {dataset_name}")
            try:
                # First try to get the metadata.json file if it exists
                self.api.hf_hub_download(
                    repo_id=dataset_name,
                    filename="metadata.json",
                    repo_type="dataset",
                    local_dir=output_dir,
                    token=self.token,
                )
                logger.info(f"Downloaded metadata.json for {dataset_name}")
                return True
            except Exception as e:
                logger.warning(f"No metadata.json found for {dataset_name}: {e}")

                # Try to get the dataset card
                try:
                    dataset_card = DatasetCard.load(dataset_name, token=self.token)
                    if dataset_card and dataset_card.data:
                        # Extract metadata from the dataset card
                        metadata = {
                            "name": dataset_name,
                            "description": dataset_card.data.get("description", ""),
                            "license": dataset_card.data.get("license", "Unknown"),
                            "tags": dataset_card.data.get("tags", []),
                        }
                        
                        with open(output_dir / "dataset_card_info.json", "w") as f:
                            json.dump(metadata, f, indent=2)
                            
                        logger.info(f"Created dataset_card_info.json for {dataset_name}")
                        return True
                except Exception as card_e:
                    logger.warning(f"Could not load dataset card for {dataset_name}: {card_e}")

                # As a last resort, get the dataset info
                info = self.get_dataset_info(dataset_name)
                if info:
                    metadata = {
                        "name": info.id,
                        "description": info.description,
                        "created_at": (
                            info.created_at.isoformat() if info.created_at else None
                        ),
                        "last_modified": (
                            info.last_modified.isoformat()
                            if info.last_modified
                            else None
                        ),
                        "tags": info.tags,
                        "downloads": info.downloads,
                        "likes": info.likes,
                    }

                    with open(output_dir / "dataset_info.json", "w") as f:
                        json.dump(metadata, f, indent=2)

                    logger.info(f"Created dataset_info.json for {dataset_name}")
                    return True

                return False
        except Exception as e:
            logger.error(f"Error downloading dataset metadata for {dataset_name}: {e}")
            return False
            
    def update_dataset_card(self, dataset_name, metadata):
        """Update or create a dataset card with metadata.
        
        Args:
            dataset_name (str): The name of the dataset to update
            metadata (dict): Metadata to add to the dataset card
            
        Returns:
            bool: Whether the card was successfully updated
        """
        if not self.token:
            logger.error("No Hugging Face token provided. Cannot update dataset card.")
            return False
            
        try:
            logger.info(f"Updating dataset card for: {dataset_name}")
            
            # Try to load existing card or create a new one
            try:
                card = DatasetCard.load(dataset_name, token=self.token)
            except Exception:
                card = DatasetCard()
                
            # Create or update card data
            if not hasattr(card, 'data') or not card.data:
                card.data = DatasetCardData()
                
            # Update with provided metadata
            if "description" in metadata:
                card.data["description"] = metadata["description"]
                
            if "license" in metadata:
                card.data["license"] = metadata["license"]
                
            if "tags" in metadata and metadata["tags"]:
                card.data["tags"] = metadata["tags"]
                
            # Add additional metadata sections if provided
            if "repository_structure" in metadata:
                card.data["repository_structure"] = metadata["repository_structure"]
                
            # Push the updated card
            card.push_to_hub(dataset_name, token=self.token)
            logger.info(f"Dataset card updated for {dataset_name}")
            return True
        except Exception as e:
            logger.error(f"Error updating dataset card for {dataset_name}: {e}")
            return False
