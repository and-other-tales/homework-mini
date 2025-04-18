import logging
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Callable

logger = logging.getLogger(__name__)


class FileProcessor:
    """Process files from various sources."""

    def process_file(self, file_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a single file from a repository.

        Args:
            file_data: Dictionary containing file information

        Returns:
            Dictionary with processed text and metadata
        """
        result = {"metadata": file_data.copy()}

        # Check if local_path exists
        if "local_path" not in file_data:
            error_msg = (
                f"Missing local_path for file: {file_data.get('path', 'unknown')}"
            )
            logger.error(error_msg)
            result["error"] = error_msg
            return result

        local_path = Path(file_data["local_path"])

        # Check if file exists
        if not local_path.exists():
            error_msg = f"File does not exist: {local_path}"
            logger.error(error_msg)
            result["error"] = error_msg
            return result

        try:
            # Process file based on extension
            extension = local_path.suffix.lower()

            if extension in [".md", ".markdown"]:
                return self.process_markdown(local_path, file_data)
            elif extension == ".json":
                return self.process_json(local_path, file_data)
            elif extension == ".ipynb":
                return self.process_notebook(local_path, file_data)
            elif extension == ".pdf":
                return self.process_pdf(local_path, file_data)
            else:
                # Default to text processing
                file_text = local_path.read_text(encoding="utf-8", errors="replace")
                result["text"] = file_text
                return result

        except Exception as e:
            error_msg = f"Error processing file {local_path}: {str(e)}"
            logger.error(error_msg)
            result["error"] = error_msg
            return result

    def process_files(
        self,
        file_data_list: List[Dict[str, Any]],
        max_workers: int = 4,
        progress_callback: Callable = None,
    ) -> List[Dict[str, Any]]:
        """
        Process multiple files in parallel.

        Args:
            file_data_list: List of file data dictionaries
            max_workers: Maximum number of parallel workers
            progress_callback: Callback function to report progress

        Returns:
            List of dictionaries with processed text and metadata
        """
        logger.info(f"Processing {len(file_data_list)} files")

        # Process files sequentially to avoid parallel processing complexities
        results = []
        for i, file_data in enumerate(file_data_list):
            results.append(self.process_file(file_data))
            if progress_callback:
                progress_callback(i + 1, len(file_data_list))

        return results

    def process_markdown(
        self, file_path: Path, file_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process markdown files."""
        result = {"metadata": file_data.copy()}
        result["text"] = file_path.read_text(encoding="utf-8", errors="replace")
        result["metadata"]["format"] = "markdown"
        return result

    def process_json(
        self, file_path: Path, file_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process JSON files."""
        result = {"metadata": file_data.copy()}
        try:
            content = json.loads(
                file_path.read_text(encoding="utf-8", errors="replace")
            )
            result["text"] = json.dumps(content, indent=2)
            result["structured_data"] = content
            result["metadata"]["format"] = "json"
        except json.JSONDecodeError as e:
            result["text"] = file_path.read_text(encoding="utf-8", errors="replace")
            result["error"] = f"Invalid JSON: {str(e)}"
        return result

    def process_notebook(
        self, file_path: Path, file_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process Jupyter notebook files."""
        result = {"metadata": file_data.copy()}
        try:
            notebook = json.loads(
                file_path.read_text(encoding="utf-8", errors="replace")
            )

            # Extract cells content
            markdown_cells = []
            code_cells = []

            for cell in notebook.get("cells", []):
                cell_type = cell.get("cell_type", "")
                source = "".join(cell.get("source", []))

                if cell_type == "markdown":
                    markdown_cells.append(source)
                elif cell_type == "code":
                    code_cells.append(source)

            # Combine content
            combined_text = (
                "\n\n".join(markdown_cells) + "\n\n" + "\n\n".join(code_cells)
            )
            result["text"] = combined_text
            result["cells"] = {"markdown": markdown_cells, "code": code_cells}
            result["metadata"]["format"] = "notebook"

        except json.JSONDecodeError as e:
            result["text"] = file_path.read_text(encoding="utf-8", errors="replace")
            result["error"] = f"Invalid notebook JSON: {str(e)}"
        except Exception as e:
            result["error"] = f"Error processing notebook: {str(e)}"

        return result

    def process_pdf(self, file_path: Path, file_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process PDF files."""
        result = {"metadata": file_data.copy()}
        try:
            # Import here to avoid dependency if not needed
            try:
                import PyPDF2
                
                # Extract text from PDF using PyPDF2
                text_parts = []
                with open(file_path, 'rb') as file:
                    pdf_reader = PyPDF2.PdfReader(file)
                    for page_num in range(len(pdf_reader.pages)):
                        page = pdf_reader.pages[page_num]
                        text_parts.append(page.extract_text())
                
                result["text"] = "\n\n".join(text_parts)
                result["metadata"]["format"] = "pdf"
                result["metadata"]["page_count"] = len(pdf_reader.pages)
                
            except ImportError:
                # Fallback if PyPDF2 is not installed
                logger.warning("PyPDF2 not installed. Cannot extract PDF text.")
                result["text"] = f"PDF content extraction requires PyPDF2: {file_path.name}"
                result["metadata"]["format"] = "pdf"
                result["pdf_path"] = str(file_path)
                
        except Exception as e:
            result["error"] = f"Error processing PDF: {str(e)}"
            result["pdf_path"] = str(file_path)  # Still include the path for potential direct access
            
        return result
