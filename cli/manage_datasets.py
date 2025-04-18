import logging
from config.credentials_manager import CredentialsManager
from huggingface.dataset_manager import DatasetManager

logger = logging.getLogger(__name__)

def manage_datasets():
    print("\n----- Manage Datasets -----")
    
    try:
        credentials_manager = CredentialsManager()
        _, huggingface_token = credentials_manager.get_huggingface_credentials()
        
        if not huggingface_token:
            print("\nError: Hugging Face token not found. Please set your credentials first.")
            return
        
        # Initialize dataset manager if needed
        dataset_manager = DatasetManager(huggingface_token=huggingface_token,
                                         credentials_manager=credentials_manager)
        
        print("\nFetching your datasets from Hugging Face...")
        datasets = dataset_manager.list_datasets()
        
        if not datasets:
            print("No datasets found for your account.")
            return
        
        # Display datasets and options
        print(f"\nFound {len(datasets)} datasets:")
        for i, dataset in enumerate(datasets):
            print(f"{i+1}. {dataset.get('id', 'Unknown')} - {dataset.get('lastModified', 'Unknown date')}")
        
        print("\nOptions:")
        print("1. View dataset details")
        print("2. Download dataset metadata")
        print("3. Delete a dataset")
        print("4. Return to main menu")
        
        manage_choice = input("\nEnter choice (1-4): ")
        
        if manage_choice == "1":
            dataset_index = int(input("Enter dataset number to view: ")) - 1
            
            if 0 <= dataset_index < len(datasets):
                dataset_id = datasets[dataset_index].get('id')
                info = dataset_manager.get_dataset_info(dataset_id)
                
                if info:
                    print(f"\n----- Dataset: {info.id} -----")
                    print(f"Description: {info.description}")
                    print(f"Created: {info.created_at}")
                    print(f"Last modified: {info.last_modified}")
                    print(f"Downloads: {info.downloads}")
                    print(f"Likes: {info.likes}")
                    print(f"Tags: {', '.join(info.tags) if info.tags else 'None'}")
                else:
                    print(f"Error retrieving details for dataset {dataset_id}")
            else:
                print("Invalid dataset number")
        
        elif manage_choice == "2":
            dataset_index = int(input("Enter dataset number to download metadata: ")) - 1
            
            if 0 <= dataset_index < len(datasets):
                dataset_id = datasets[dataset_index].get('id')
                success = dataset_manager.download_dataset_metadata(dataset_id)
                
                if success:
                    print(f"\nMetadata for dataset '{dataset_id}' downloaded successfully")
                    print(f"Saved to ./dataset_metadata/{dataset_id}/")
                else:
                    print(f"Error downloading metadata for dataset {dataset_id}")
            else:
                print("Invalid dataset number")
        
        elif manage_choice == "3":
            dataset_index = int(input("Enter dataset number to delete: ")) - 1
            
            if 0 <= dataset_index < len(datasets):
                dataset_id = datasets[dataset_index].get('id')
                
                confirm = input(f"Are you sure you want to delete dataset '{dataset_id}'? (yes/no): ")
                if confirm.lower() == "yes":
                    success = dataset_manager.delete_dataset(dataset_id)
                    
                    if success:
                        print(f"\nDataset '{dataset_id}' deleted successfully")
                    else:
                        print(f"Error deleting dataset {dataset_id}")
                else:
                    print("Deletion cancelled")
            else:
                print("Invalid dataset number")
        
        elif manage_choice == "4":
            return
        
        else:
            print("Invalid choice")
        
    except Exception as e:
        print(f"\nError managing datasets: {e}")
        logging.error(f"Error in manage datasets: {e}")
