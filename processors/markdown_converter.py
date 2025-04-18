import logging
import re
import os
from typing import Optional, Dict, Any, Union
from pathlib import Path
import importlib

logger = logging.getLogger(__name__)

# HTML cleaning patterns
SCRIPT_PATTERN = r"<[ ]*script.*?\/[ ]*script[ ]*>"
STYLE_PATTERN = r"<[ ]*style.*?\/[ ]*style[ ]*>"
META_PATTERN = r"<[ ]*meta.*?>"
COMMENT_PATTERN = r"<[ ]*!--.*?--[ ]*>"
LINK_PATTERN = r"<[ ]*link.*?>"
BASE64_IMG_PATTERN = r'<img[^>]+src="data:image/[^;]+;base64,[^"]+"[^>]*>'
SVG_PATTERN = r"(<svg[^>]*>)(.*?)(<\/svg>)"


class HTMLMarkdownConverter:
    """
    Converter for HTML to Markdown using the ReaderLM-v2 model from Jina AI.
    """

    def __init__(self, model_path: str = "jinaai/ReaderLM-v2", device: str = None):
        """
        Initialize the HTML to Markdown converter.
        
        Args:
            model_path: Path or name of the model to use (default: jinaai/ReaderLM-v2)
            device: Device to run the model on ('cuda' or 'cpu', defaults to CUDA if available)
        """
        self.model_path = model_path
        self.device = device or self._get_default_device()
        self.model = None
        self.tokenizer = None
        
        # Check if transformers is installed
        try:
            import transformers
            self.transformers_available = True
        except ImportError:
            self.transformers_available = False
            logger.warning("transformers not installed. Install with 'pip install transformers' for full functionality.")
    
    def _get_default_device(self) -> str:
        """Get the default device (CUDA if available, otherwise CPU)."""
        try:
            import torch
            return "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            return "cpu"
    
    def load_model(self) -> bool:
        """
        Load the ReaderLM-v2 model for HTML to Markdown conversion.
        
        Returns:
            bool: Whether the model was loaded successfully
        """
        if not self.transformers_available:
            logger.error("Cannot load model: transformers package not installed")
            return False
        
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
            
            logger.info(f"Loading ReaderLM-v2 model on {self.device}...")
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_path)
            self.model = AutoModelForCausalLM.from_pretrained(self.model_path).to(self.device)
            
            logger.info("Model loaded successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            return False
    
    def clean_html(self, html: str, clean_svg: bool = True, clean_base64: bool = True) -> str:
        """
        Clean HTML content by removing scripts, styles, comments, etc.
        
        Args:
            html: HTML content to clean
            clean_svg: Whether to replace SVG content with placeholders
            clean_base64: Whether to replace base64 images with simple img tags
            
        Returns:
            Cleaned HTML string
        """
        # Remove scripts
        html = re.sub(SCRIPT_PATTERN, "", html, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
        
        # Remove styles
        html = re.sub(STYLE_PATTERN, "", html, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
        
        # Remove meta tags
        html = re.sub(META_PATTERN, "", html, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
        
        # Remove comments
        html = re.sub(COMMENT_PATTERN, "", html, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
        
        # Remove link tags
        html = re.sub(LINK_PATTERN, "", html, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
        
        # Clean SVG content if requested
        if clean_svg:
            html = self.replace_svg(html)
        
        # Clean base64 images if requested
        if clean_base64:
            html = self.replace_base64_images(html)
        
        return html
    
    def replace_svg(self, html: str, new_content: str = "this is a placeholder") -> str:
        """
        Replace SVG content with a placeholder to reduce input size.
        
        Args:
            html: HTML content containing SVGs
            new_content: Placeholder text to use
            
        Returns:
            HTML with SVG content replaced
        """
        return re.sub(
            SVG_PATTERN,
            lambda match: f"{match.group(1)}{new_content}{match.group(3)}",
            html,
            flags=re.DOTALL
        )
    
    def replace_base64_images(self, html: str, new_image_src: str = "#") -> str:
        """
        Replace base64 encoded images with simple image tags.
        
        Args:
            html: HTML content containing base64 images
            new_image_src: Replacement source for images
            
        Returns:
            HTML with base64 images replaced
        """
        return re.sub(BASE64_IMG_PATTERN, f'<img src="{new_image_src}"/>', html)
    
    def create_prompt(self, html: str, instruction: str = None, schema: str = None) -> str:
        """
        Create a prompt for the model with optional instruction and JSON schema.
        
        Args:
            html: HTML content to convert
            instruction: Optional custom instruction
            schema: Optional JSON schema for structured extraction
            
        Returns:
            Formatted prompt for the model
        """
        if not self.tokenizer:
            raise ValueError("Model not loaded. Call load_model() first.")
        
        if not instruction:
            instruction = "Extract the main content from the given HTML and convert it to Markdown format."
        
        if schema:
            instruction = "Extract the specified information from the HTML and present it in a structured JSON format."
            prompt = f"{instruction}\n```html\n{html}\n```\nThe JSON schema is as follows:```json\n{schema}\n```"
        else:
            prompt = f"{instruction}\n```html\n{html}\n```"
        
        messages = [
            {
                "role": "user",
                "content": prompt,
            }
        ]
        
        return self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
    
    def html_to_markdown(
        self, 
        html: str, 
        clean_html: bool = True, 
        custom_instruction: str = None, 
        max_tokens: int = 4096,
        temperature: float = 0.0
    ) -> str:
        """
        Convert HTML to Markdown using the ReaderLM-v2 model.
        
        Args:
            html: HTML content to convert
            clean_html: Whether to clean the HTML before conversion
            custom_instruction: Optional custom instruction for the model
            max_tokens: Maximum number of new tokens to generate
            temperature: Temperature for generation (0.0 = deterministic)
            
        Returns:
            Markdown string
        """
        if not self.model or not self.tokenizer:
            loaded = self.load_model()
            if not loaded:
                logger.error("Failed to load model. Using fallback method.")
                return self._fallback_html_to_markdown(html)
        
        try:
            import torch
            
            # Clean the HTML if requested
            if clean_html:
                html = self.clean_html(html)
            
            # Create the prompt
            input_prompt = self.create_prompt(html, instruction=custom_instruction)
            
            # Encode the prompt
            inputs = self.tokenizer.encode(input_prompt, return_tensors="pt").to(self.device)
            
            # Generate the markdown
            with torch.no_grad():
                outputs = self.model.generate(
                    inputs,
                    max_new_tokens=max_tokens,
                    temperature=temperature,
                    do_sample=(temperature > 0),
                    repetition_penalty=1.08
                )
            
            # Decode the output
            output_text = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
            
            # Extract just the assistant's response
            # This removes the input prompt from the response
            assistant_response = output_text.split("[/INST]")[-1].strip()
            
            return assistant_response
            
        except Exception as e:
            logger.error(f"Error converting HTML to Markdown with model: {e}")
            logger.info("Falling back to basic HTML to Markdown conversion")
            return self._fallback_html_to_markdown(html)
    
    def _fallback_html_to_markdown(self, html: str) -> str:
        """
        Fallback method to convert HTML to Markdown using BeautifulSoup if the model fails.
        
        Args:
            html: HTML content to convert
            
        Returns:
            Basic Markdown conversion of the HTML
        """
        try:
            from bs4 import BeautifulSoup
            
            # Clean the HTML
            html = self.clean_html(html)
            
            # Parse the HTML
            soup = BeautifulSoup(html, 'html.parser')
            
            # Get the page title
            title = soup.find('title')
            title_text = title.text.strip() if title else "Untitled Page"
            
            # Start markdown with title
            markdown = f"# {title_text}\n\n"
            
            # Add headings
            for heading in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                level = int(heading.name[1])
                markdown += f"{'#' * level} {heading.text.strip()}\n\n"
            
            # Add paragraphs
            for p in soup.find_all('p'):
                markdown += f"{p.text.strip()}\n\n"
            
            # Add lists
            for ul in soup.find_all('ul'):
                for li in ul.find_all('li'):
                    markdown += f"* {li.text.strip()}\n"
                markdown += "\n"
            
            for ol in soup.find_all('ol'):
                for i, li in enumerate(ol.find_all('li')):
                    markdown += f"{i+1}. {li.text.strip()}\n"
                markdown += "\n"
            
            # Add links
            for a in soup.find_all('a', href=True):
                # If the link appears in the generated markdown, replace it with markdown link format
                link_text = a.text.strip()
                if link_text:
                    href = a['href']
                    markdown = markdown.replace(
                        link_text, 
                        f"[{link_text}]({href})"
                    )
            
            return markdown
            
        except ImportError:
            logger.error("BeautifulSoup not installed. Using very basic conversion.")
            
            # Very basic fallback if BeautifulSoup is not available
            # Remove all HTML tags
            text = re.sub(r'<[^>]*>', '', html)
            # Replace HTML entities
            text = text.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
            # Split into paragraphs
            paragraphs = re.split(r'\n\s*\n', text)
            # Join with double newlines
            return '\n\n'.join(p.strip() for p in paragraphs)
        
        except Exception as e:
            logger.error(f"Error in fallback HTML to Markdown conversion: {e}")
            return "Error converting HTML to Markdown"
    
    def html_to_json(
        self, 
        html: str, 
        schema: str,
        clean_html: bool = True,
        max_tokens: int = 4096,
        temperature: float = 0.0
    ) -> str:
        """
        Convert HTML to structured JSON using the ReaderLM-v2 model.
        
        Args:
            html: HTML content to convert
            schema: JSON schema defining the expected output structure
            clean_html: Whether to clean the HTML before conversion
            max_tokens: Maximum number of new tokens to generate
            temperature: Temperature for generation (0.0 = deterministic)
            
        Returns:
            JSON string
        """
        if not self.model or not self.tokenizer:
            loaded = self.load_model()
            if not loaded:
                logger.error("Failed to load model for HTML to JSON conversion")
                return "{}"
        
        try:
            import torch
            
            # Clean the HTML if requested
            if clean_html:
                html = self.clean_html(html)
            
            # Create the prompt with schema
            input_prompt = self.create_prompt(html, schema=schema)
            
            # Encode the prompt
            inputs = self.tokenizer.encode(input_prompt, return_tensors="pt").to(self.device)
            
            # Generate the JSON
            with torch.no_grad():
                outputs = self.model.generate(
                    inputs,
                    max_new_tokens=max_tokens, 
                    temperature=temperature,
                    do_sample=(temperature > 0),
                    repetition_penalty=1.08
                )
            
            # Decode the output
            output_text = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
            
            # Extract just the assistant's response
            assistant_response = output_text.split("[/INST]")[-1].strip()
            
            return assistant_response
            
        except Exception as e:
            logger.error(f"Error converting HTML to JSON: {e}")
            return "{}"
    
    def batch_convert_to_markdown(self, html_files: list, output_dir: Optional[str] = None) -> Dict[str, str]:
        """
        Batch convert multiple HTML files to Markdown.
        
        Args:
            html_files: List of HTML file paths or (path, html_content) tuples
            output_dir: Optional directory to save output files
            
        Returns:
            Dictionary mapping input paths to output paths or markdown content
        """
        results = {}
        
        # Create output directory if specified and not exists
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        
        # Load model once for all conversions
        if not self.model or not self.tokenizer:
            loaded = self.load_model()
            if not loaded:
                logger.error("Failed to load model for batch conversion")
        
        # Process each file
        for item in html_files:
            try:
                # Handle both file paths and (path, content) tuples
                if isinstance(item, tuple) and len(item) == 2:
                    file_path, html_content = item
                else:
                    file_path = item
                    with open(file_path, 'r', encoding='utf-8') as f:
                        html_content = f.read()
                
                # Convert to markdown
                markdown = self.html_to_markdown(html_content)
                
                # Save to file if output directory specified
                if output_dir:
                    filename = os.path.basename(file_path)
                    base_name = os.path.splitext(filename)[0]
                    output_path = os.path.join(output_dir, f"{base_name}.md")
                    
                    with open(output_path, 'w', encoding='utf-8') as f:
                        f.write(markdown)
                    
                    results[file_path] = output_path
                else:
                    # Just store the markdown content
                    results[file_path] = markdown
                    
            except Exception as e:
                logger.error(f"Error processing {file_path}: {e}")
                results[file_path] = None
        
        return results