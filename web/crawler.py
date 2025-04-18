import logging
import re
import atexit
import signal
import time
import os
import json
from pathlib import Path
from urllib.parse import urlparse, urljoin
from concurrent.futures import ThreadPoolExecutor
import requests
from urllib.robotparser import RobotFileParser
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from utils.task_tracker import TaskTracker

logger = logging.getLogger(__name__)

# Global executor for background tasks
_global_executor = None


def get_executor(max_workers=3):
    """Get or create a global thread pool executor."""
    global _global_executor
    if _global_executor is None:
        _global_executor = ThreadPoolExecutor(max_workers=max_workers)
    return _global_executor


def shutdown_executor():
    """Shutdown the global executor."""
    global _global_executor
    if _global_executor:
        logger.debug("Shutting down global thread pool executor")
        _global_executor.shutdown(wait=False)
        _global_executor = None


# Register shutdown function
atexit.register(shutdown_executor)

# Register signal handlers for graceful shutdown
for sig in (signal.SIGINT, signal.SIGTERM):
    signal.signal(sig, lambda signum, frame: shutdown_executor())


class WebCrawler:
    """Crawls websites and extracts content for dataset creation."""

    def __init__(self, respect_robots_txt=True, rate_limit_delay=1.0):
        """
        Initialize the web crawler.
        
        Args:
            respect_robots_txt: Whether to respect robots.txt rules
            rate_limit_delay: Delay between requests in seconds
        """
        self.task_tracker = TaskTracker()
        self.temp_dir = Path("./temp")
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        # Store all visited URLs to avoid duplicates
        self.visited_urls = set()
        
        # Configure default headers for requests
        self.user_agent = 'othertales-serper/1.0 (https://othertales.com/serper; contact@othertales.com)'
        self.headers = {
            'User-Agent': self.user_agent
        }
        
        # Robots.txt handling
        self.respect_robots_txt = respect_robots_txt
        self.robots_parsers = {}  # Cache for robots.txt parsers
        
        # Rate limiting
        self.rate_limit_delay = rate_limit_delay
        self.domain_last_access = {}  # Track when we last accessed each domain
        
        # Status display variables
        self.status_thread = None
        self.stop_status_display = None
        self.current_status = ""

    def _is_valid_url(self, url, base_url):
        """
        Check if the URL is valid and belongs to the same domain.
        
        Args:
            url: URL to check
            base_url: Base URL of the website being crawled
            
        Returns:
            bool: Whether the URL is valid
        """
        if not url or url.startswith('#'):
            return False
        
        # Parse the URLs
        base_domain = urlparse(base_url).netloc
        parsed_url = urlparse(url)
        
        # If it's a relative URL, it's valid
        if not parsed_url.netloc:
            return True
            
        # If absolute URL, check if it's from the same domain
        return parsed_url.netloc == base_domain

    def _get_absolute_url(self, url, base_url):
        """
        Convert a relative URL to an absolute URL.
        
        Args:
            url: URL to convert
            base_url: Base URL of the website
            
        Returns:
            str: Absolute URL
        """
        return urljoin(base_url, url)

    def _get_robots_parser(self, url):
        """
        Get or create a robots.txt parser for the given URL's domain.
        
        Args:
            url: URL to get robots parser for
            
        Returns:
            RobotFileParser instance
        """
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        
        # Check if we already have a parser for this domain
        if domain in self.robots_parsers:
            return self.robots_parsers[domain]
        
        # Create a new parser
        parser = RobotFileParser()
        robots_url = f"{parsed_url.scheme}://{domain}/robots.txt"
        
        try:
            parser.set_url(robots_url)
            parser.read()
            logger.info(f"Loaded robots.txt from {robots_url}")
        except Exception as e:
            logger.warning(f"Failed to fetch robots.txt from {robots_url}: {e}")
            # Create an empty parser that allows everything
            parser = RobotFileParser()
            parser.parse(['User-agent: *', 'Allow: /'])
        
        # Cache the parser
        self.robots_parsers[domain] = parser
        return parser
    
    def _can_fetch(self, url):
        """
        Check if the URL can be fetched according to robots.txt rules.
        
        Args:
            url: URL to check
            
        Returns:
            bool: Whether the URL can be fetched
        """
        if not self.respect_robots_txt:
            return True
            
        parser = self._get_robots_parser(url)
        return parser.can_fetch(self.user_agent, url)
    
    def _apply_rate_limiting(self, url):
        """
        Apply rate limiting for the domain of the given URL.
        
        Args:
            url: URL to apply rate limiting for
        """
        # Extract domain
        domain = urlparse(url).netloc
        
        # Check if we need to wait
        current_time = time.time()
        if domain in self.domain_last_access:
            last_access_time = self.domain_last_access[domain]
            elapsed = current_time - last_access_time
            
            if elapsed < self.rate_limit_delay:
                # Need to wait
                wait_time = self.rate_limit_delay - elapsed
                logger.debug(f"Rate limiting: waiting {wait_time:.2f}s for {domain}")
                time.sleep(wait_time)
        
        # Update last access time
        self.domain_last_access[domain] = time.time()
    
    def _extract_urls(self, soup, base_url, url_patterns=None, current_depth=0, max_depth=None):
        """
        Extract all valid URLs from a BeautifulSoup object.
        
        Args:
            soup: BeautifulSoup object
            base_url: Base URL of the website
            url_patterns: List of regex patterns for URLs to include
            current_depth: Current depth from start URL
            max_depth: Maximum depth to crawl
            
        Returns:
            list: List of valid URLs
        """
        # Check if we've reached max depth
        if max_depth is not None and current_depth >= max_depth:
            logger.info(f"Reached maximum depth ({max_depth}), stopping extraction of new URLs")
            return []

        urls = []
        for link in soup.find_all('a', href=True):
            url = link['href']
            if self._is_valid_url(url, base_url):
                absolute_url = self._get_absolute_url(url, base_url)
                
                # Check robots.txt permissions
                if not self._can_fetch(absolute_url):
                    logger.debug(f"Skipping URL disallowed by robots.txt: {absolute_url}")
                    continue
                
                # Apply URL pattern filtering if specified
                if url_patterns:
                    import re
                    matches = False
                    for pattern in url_patterns:
                        if re.search(pattern, absolute_url):
                            matches = True
                            break
                    
                    if not matches:
                        logger.debug(f"Skipping URL that doesn't match patterns: {absolute_url}")
                        continue
                
                urls.append(absolute_url)
        
        # Remove duplicates while preserving order
        unique_urls = []
        seen = set()
        for url in urls:
            if url not in seen:
                seen.add(url)
                unique_urls.append(url)
                
        return unique_urls

    def fetch_page(self, url, use_playwright=True):
        """
        Fetch a web page using either requests or Playwright.
        
        Args:
            url: URL to fetch
            use_playwright: Whether to use Playwright (for JavaScript rendering)
            
        Returns:
            dict: Dictionary with status, content, and soup object
        """
        logger.info(f"Fetching page: {url}")
        
        # Check robots.txt permissions
        if self.respect_robots_txt and not self._can_fetch(url):
            logger.warning(f"Skipping URL disallowed by robots.txt: {url}")
            return {
                "status": "error",
                "error": "URL disallowed by robots.txt",
                "url": url
            }
        
        # Apply rate limiting
        self._apply_rate_limiting(url)
        
        result = {
            "status": "error",
            "content": None,
            "html": None,
            "soup": None,
            "title": None,
            "meta_description": None,
            "url": url,
            "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        try:
            if use_playwright:
                # Use Playwright for JavaScript-rendered pages
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page(
                        user_agent=self.user_agent
                    )
                    
                    # Set viewport size
                    page.set_viewport_size({"width": 1280, "height": 800})
                    
                    # Navigate to the page
                    page.goto(url, wait_until="networkidle", timeout=60000)
                    
                    # Wait for page to be fully loaded
                    page.wait_for_load_state("networkidle")
                    
                    # Get the fully rendered HTML
                    html = page.content()
                    
                    # Get page title
                    title = page.title()
                    
                    # Close browser
                    browser.close()
                    
                    # Parse the HTML with BeautifulSoup
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    result["status"] = "success"
                    result["html"] = html
                    result["soup"] = soup
                    result["title"] = title
                    
                    # Extract meta description
                    meta_desc = soup.find('meta', attrs={'name': 'description'})
                    if meta_desc and 'content' in meta_desc.attrs:
                        result["meta_description"] = meta_desc['content']
                    
                    # Extract other useful metadata
                    canonical = soup.find('link', attrs={'rel': 'canonical'})
                    if canonical and 'href' in canonical.attrs:
                        result["canonical_url"] = canonical['href']
            else:
                # Use requests for simpler pages
                response = requests.get(url, headers=self.headers, timeout=30)
                response.raise_for_status()
                
                html = response.text
                soup = BeautifulSoup(html, 'html.parser')
                
                result["status"] = "success"
                result["html"] = html
                result["soup"] = soup
                
                # Extract title
                title_tag = soup.find('title')
                if title_tag:
                    result["title"] = title_tag.text.strip()
                
                # Extract meta description
                meta_desc = soup.find('meta', attrs={'name': 'description'})
                if meta_desc and 'content' in meta_desc.attrs:
                    result["meta_description"] = meta_desc['content']
                
                # Extract other useful metadata
                canonical = soup.find('link', attrs={'rel': 'canonical'})
                if canonical and 'href' in canonical.attrs:
                    result["canonical_url"] = canonical['href']
        
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            result["error"] = str(e)
            
        return result

    def html_to_markdown(self, html, url):
        """
        Convert HTML to markdown using jinaai/Reader-LMv2 model.
        
        Args:
            html: HTML content
            url: URL of the page
            
        Returns:
            str: Markdown content
        """
        try:
            # Use our dedicated HTML to Markdown converter
            from processors.markdown_converter import HTMLMarkdownConverter
            
            # Initialize the converter (lazy loading of model when needed)
            converter = HTMLMarkdownConverter()
            
            # Create a custom instruction that includes the URL
            custom_instruction = f"Extract the main content from the given HTML and convert it to Markdown format. Include the source URL: {url}"
            
            # Convert HTML to Markdown
            markdown = converter.html_to_markdown(
                html=html,
                clean_html=True,
                custom_instruction=custom_instruction,
                max_tokens=4096
            )
            
            # If successful, return the markdown
            if markdown and len(markdown) > 10:  # Basic check that we got something usable
                return markdown
            
            # If markdown is empty or very short, try the fallback method
            logger.warning("Markdown conversion returned minimal content, trying fallback method")
            return self._fallback_html_to_markdown(html, url)
            
        except ImportError:
            # Fall back to basic conversion if the converter module is not available
            logger.warning("markdown_converter module not available, using fallback method")
            return self._fallback_html_to_markdown(html, url)
            
        except Exception as e:
            logger.error(f"Error converting HTML to markdown: {e}")
            
            # Fallback to basic text extraction
            return self._fallback_html_to_markdown(html, url)
    
    def _fallback_html_to_markdown(self, html, url):
        """
        Fallback method to convert HTML to Markdown using BeautifulSoup.
        
        Args:
            html: HTML content to convert
            url: URL of the page
            
        Returns:
            str: Basic Markdown conversion of the HTML
        """
        try:
            soup = BeautifulSoup(html, 'html.parser')
            for script in soup(["script", "style"]):
                script.extract()
            
            # Get the page title
            title = soup.find('title')
            if title:
                title_text = title.text.strip()
            else:
                title_text = "Untitled Page"
            
            # Start markdown with title and URL
            markdown = f"# {title_text}\n\nSource: {url}\n\n"
            
            # Add headings
            for heading in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                level = int(heading.name[1])
                markdown += f"{'#' * level} {heading.text.strip()}\n\n"
                
                # Add paragraphs after headings
                next_el = heading.next_sibling
                while next_el and next_el.name != 'h1' and next_el.name != 'h2' and next_el.name != 'h3':
                    if next_el.name == 'p':
                        markdown += f"{next_el.text.strip()}\n\n"
                    next_el = next_el.next_sibling
            
            # Add remaining paragraphs
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
                link_text = a.text.strip()
                if link_text:
                    href = a['href']
                    if not href.startswith(('http://', 'https://')):
                        href = urljoin(url, href)
                    # We're not actually replacing in text since this is a basic fallback
                    markdown += f"[{link_text}]({href})\n\n"
            
            return markdown
            
        except Exception as e:
            logger.error(f"Error in fallback HTML to Markdown conversion: {e}")
            
            # Very basic fallback if everything else fails
            try:
                soup = BeautifulSoup(html, 'html.parser')
                for script in soup(["script", "style"]):
                    script.extract()
                
                return f"# Page Content from {url}\n\n" + soup.get_text(separator='\n\n', strip=True)
            except:
                return f"# Content from {url}\n\nError extracting content."

    def get_crawl_instructions(self, user_input, url):
        """
        Get crawling instructions from a chat completions model based on user input.
        
        Args:
            user_input (str): The user's description of what they want to scrape
            url (str): The URL to crawl
            
        Returns:
            dict: A dictionary of crawling instructions
        """
        import requests
        import json
        import os
        
        # Default instructions if API call fails
        default_instructions = {
            "should_crawl_recursively": True,
            "max_pages": 100,
            "same_domain_only": True,
            "content_selectors": [],
            "extraction_goal": "general",
            "filters": [],
            "priority_content": []
        }
        
        try:
            # Get API key from environment or configuration
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                try:
                    from config.credentials_manager import CredentialsManager
                    credentials_manager = CredentialsManager()
                    api_key = credentials_manager.get_openai_key()
                except (ImportError, AttributeError):
                    logger.warning("OpenAI API key not found for crawl instructions. Using default settings.")
                    return default_instructions
            
            if not api_key:
                logger.warning("OpenAI API key not found for crawl instructions. Using default settings.")
                return default_instructions
                
            # Prepare the message to the completions API
            messages = [
                {"role": "system", "content": "You are an expert web crawler instruction generator. Your task is to analyze the user's intent for web scraping and provide specific instructions for the web crawler. Return your response as a JSON object."},
                {"role": "user", "content": f"I want to crawl this URL: {url}\n\nI need: {user_input}\n\nPlease provide detailed instructions for my web crawler in JSON format. Include the following fields: should_crawl_recursively (boolean), max_pages (integer), same_domain_only (boolean), content_selectors (array of CSS selectors to focus on), extraction_goal (string: 'general', 'specific_content', 'full_text'), filters (array of criteria to filter content), priority_content (array of keywords or patterns to prioritize)."}
            ]
            
            # Make API call to chat completions endpoint (works with both OpenAI and compatible endpoints)
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }
            
            endpoint = os.environ.get("OPENAI_API_ENDPOINT", "https://api.openai.com/v1/chat/completions")
            
            payload = {
                "model": os.environ.get("OPENAI_MODEL", "gpt-3.5-turbo"),
                "messages": messages,
                "temperature": 0.2,
                "response_format": {"type": "json_object"}
            }
            
            logger.debug(f"Requesting crawl instructions for URL: {url}")
            response = requests.post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                if "choices" in result and len(result["choices"]) > 0:
                    content = result["choices"][0]["message"]["content"]
                    try:
                        instructions = json.loads(content)
                        logger.info("Successfully received crawl instructions from AI")
                        
                        # Validate and set defaults for missing fields
                        if "should_crawl_recursively" not in instructions:
                            instructions["should_crawl_recursively"] = default_instructions["should_crawl_recursively"]
                        if "max_pages" not in instructions:
                            instructions["max_pages"] = default_instructions["max_pages"]
                        if "same_domain_only" not in instructions:
                            instructions["same_domain_only"] = default_instructions["same_domain_only"]
                        if "content_selectors" not in instructions:
                            instructions["content_selectors"] = default_instructions["content_selectors"]
                        if "extraction_goal" not in instructions:
                            instructions["extraction_goal"] = default_instructions["extraction_goal"]
                        if "filters" not in instructions:
                            instructions["filters"] = default_instructions["filters"]
                        if "priority_content" not in instructions:
                            instructions["priority_content"] = default_instructions["priority_content"]
                            
                        return instructions
                    except json.JSONDecodeError:
                        logger.error("Failed to parse JSON response from AI")
                        return default_instructions
            
            logger.warning(f"Failed to get crawl instructions: {response.status_code}")
            return default_instructions
            
        except Exception as e:
            logger.error(f"Error getting crawl instructions: {str(e)}")
            return default_instructions
            
    def crawl_website(self, start_url, recursive=False, max_pages=None, progress_callback=None, 
                      _cancellation_event=None, cleanup_temp=False, user_instructions=None, use_ai_guidance=False,
                      max_depth=None, content_filters=None, url_patterns=None):
        """
        Crawl a website starting from the provided URL.
        
        Args:
            start_url: URL to start crawling from
            recursive: Whether to recursively crawl all linked pages
            max_pages: Maximum number of pages to crawl
            progress_callback: Function to call with progress updates
            _cancellation_event: Event to check for cancellation
            cleanup_temp: Whether to clean up temporary files after crawling
            user_instructions: User's description of what to scrape (used with AI guidance)
            use_ai_guidance: Whether to use AI to guide the crawling process
            max_depth: Maximum depth to crawl from the start URL (None means no limit)
            content_filters: List of keywords or patterns to filter content by (inclusive)
            url_patterns: List of regex patterns for URLs to include
            
        Returns:
            list: List of crawled page data
        """
        # If AI guidance is requested and user instructions are provided, get crawl instructions
        ai_instructions = None
        if use_ai_guidance and user_instructions:
            if progress_callback:
                progress_callback(0, "Getting AI guidance for crawling...")
                
            ai_instructions = self.get_crawl_instructions(user_instructions, start_url)
            
            # Apply AI instructions to crawler settings
            if ai_instructions:
                # Override recursive setting if specified by AI
                if "should_crawl_recursively" in ai_instructions:
                    recursive = ai_instructions["should_crawl_recursively"]
                    
                # Override max_pages if specified by AI
                if "max_pages" in ai_instructions and ai_instructions["max_pages"] > 0:
                    max_pages = ai_instructions["max_pages"]
                    
                logger.info(f"Using AI-guided crawl settings: recursive={recursive}, max_pages={max_pages}")
        
        logger.info(f"Starting crawl at {start_url}, recursive={recursive}")
        
        if progress_callback:
            if ai_instructions:
                progress_callback(0, f"Starting AI-guided crawl with {len(ai_instructions.get('content_selectors', []))} content selectors")
            else:
                progress_callback(0, "Starting crawl")
        
        # Reset visited URLs
        self.visited_urls = set()
        
        # Queue of URLs to visit (with depth tracking)
        to_visit = [(start_url, 0)]  # (url, depth)
        
        # List of page data
        results = []
        
        # Crawl until queue is empty or max_pages is reached
        page_count = 0
        total_pages = 1  # Initial estimate
        
        while to_visit and (max_pages is None or page_count < max_pages):
            # Check for cancellation
            if _cancellation_event and _cancellation_event.is_set():
                logger.info("Crawl cancelled")
                if progress_callback:
                    progress_callback(page_count / max(1, total_pages) * 100, "Crawl cancelled")
                break
            
            # Update progress
            if progress_callback:
                progress_percent = min(95, page_count / max(1, len(to_visit) + page_count) * 100)
                progress_callback(progress_percent, f"Crawled {page_count} pages, {len(to_visit)} in queue")
            
            # Get next URL to visit (and its depth if available)
            url_info = to_visit.pop(0)
            if isinstance(url_info, tuple) and len(url_info) == 2:
                url, current_depth = url_info
            else:
                url = url_info
                current_depth = 0
            
            # Skip if already visited
            if url in self.visited_urls:
                continue
            
            # Mark as visited
            self.visited_urls.add(url)
            
            # Fetch the page
            page_data = self.fetch_page(url)
            # Add depth information
            page_data["depth"] = current_depth
            
            if page_data["status"] == "success":
                # Convert HTML to markdown
                markdown = self.html_to_markdown(page_data["html"], url)
                
                # Generate unique filename
                parsed_url = urlparse(url)
                filename = parsed_url.netloc + parsed_url.path.replace('/', '_')
                if not filename.endswith('.md'):
                    filename += '.md'
                
                # Save to temp directory
                file_path = self.temp_dir / filename
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(markdown)
                
                # Apply content selectors from AI instructions if available
                if ai_instructions and ai_instructions.get("content_selectors"):
                    try:
                        # Create a new soup from the markdown for further processing
                        filtered_content = ""
                        soup_copy = page_data["soup"]
                        
                        # Apply each selector
                        for selector in ai_instructions["content_selectors"]:
                            try:
                                selected_elements = soup_copy.select(selector)
                                if selected_elements:
                                    for element in selected_elements:
                                        filtered_content += str(element) + "\n\n"
                                        
                                    logger.debug(f"Applied selector '{selector}' found {len(selected_elements)} elements")
                            except Exception as selector_error:
                                logger.warning(f"Error applying selector '{selector}': {str(selector_error)}")
                        
                        # If we extracted content with selectors, reconvert it to markdown
                        if filtered_content and len(filtered_content) > 10:
                            logger.info(f"Using AI-selected content for {url}")
                            
                            # Convert the filtered HTML to markdown
                            filtered_markdown = self.html_to_markdown(filtered_content, url)
                            
                            # If we got good filtered content, replace the original markdown
                            if filtered_markdown and len(filtered_markdown) > 20:
                                page_data["ai_filtered"] = True
                                page_data["original_markdown"] = markdown
                                markdown = filtered_markdown
                                page_data["markdown"] = markdown
                                
                                if progress_callback:
                                    progress_callback(
                                        page_count / max(1, total_pages) * 100,
                                        f"Applied {len(ai_instructions['content_selectors'])} AI-guided content selectors"
                                    )
                    except Exception as e:
                        logger.error(f"Error applying AI content selectors: {str(e)}")
                
                # Add to results
                page_data["markdown"] = markdown
                page_data["local_path"] = str(file_path)
                
                # Add AI guidance information if applicable
                if ai_instructions:
                    page_data["ai_guided"] = True
                    page_data["extraction_goal"] = ai_instructions.get("extraction_goal", "general")
                    
                results.append(page_data)
                
                # Increment page count
                page_count += 1
                
                # Apply content filtering if specified
                if content_filters and page_data.get("markdown"):
                    content_match = False
                    for filter_pattern in content_filters:
                        if filter_pattern.lower() in page_data["markdown"].lower():
                            content_match = True
                            logger.info(f"Content filter '{filter_pattern}' matched for {url}")
                            break
                    
                    if not content_match:
                        logger.info(f"Page content didn't match any content filters, excluding: {url}")
                        page_data["filtered_out"] = True
                        # Keep tracking the URL as visited but don't include in final results
                        continue

                # Extract URLs and add to queue if recursive
                if recursive:
                    if page_data["soup"]:
                        # Track current depth for this page
                        current_depth = page_data.get("depth", 0)
                        
                        # Extract URLs with depth and pattern awareness
                        new_urls = self._extract_urls(
                            page_data["soup"], 
                            url, 
                            url_patterns=url_patterns,
                            current_depth=current_depth,
                            max_depth=max_depth
                        )
                        
                        # Filter out already visited or queued URLs
                        filtered_urls = [u for u in new_urls if u not in self.visited_urls and u not in to_visit]
                        
                        # Apply AI prioritization if available
                        if ai_instructions and ai_instructions.get("priority_content"):
                            prioritized_urls = []
                            other_urls = []
                            
                            for link in filtered_urls:
                                # Check if link matches any priority content patterns
                                is_priority = False
                                for pattern in ai_instructions["priority_content"]:
                                    if pattern.lower() in link.lower():
                                        is_priority = True
                                        break
                                
                                if is_priority:
                                    prioritized_urls.append(link)
                                else:
                                    other_urls.append(link)
                            
                            # Create URL objects with depth information
                            prioritized_with_depth = [(url, current_depth + 1) for url in prioritized_urls]
                            other_with_depth = [(url, current_depth + 1) for url in other_urls]
                            
                            # Add prioritized links first
                            to_visit_with_depth = [(u, d) for u, d in prioritized_with_depth if u not in [x[0] for x in to_visit]]
                            to_visit_with_depth.extend([(u, d) for u, d in to_visit_with_depth + other_with_depth if u not in [x[0] for x in to_visit]])
                            
                            # Update to_visit with the new structure
                            to_visit = to_visit_with_depth
                            
                            if prioritized_urls and progress_callback:
                                progress_callback(
                                    page_count / max(1, total_pages) * 100, 
                                    f"Found {len(prioritized_urls)} priority links matching AI criteria"
                                )
                        else:
                            # Standard link handling with depth tracking
                            url_with_depth = [(url, current_depth + 1) for url in filtered_urls]
                            to_visit.extend(url_with_depth)
                        
                        # Update total pages estimate
                        total_pages = max(total_pages, page_count + len(to_visit))
            
            # Respect rate limiting
            time.sleep(1)
        
        # Complete progress
        if progress_callback:
            progress_callback(100, f"Completed crawl of {page_count} pages")
        
        # Second verification round to ensure no documents are missed
        if recursive and page_count > 0 and not (_cancellation_event and _cancellation_event.is_set()):
            logger.info("Starting verification round to check for missed documents")
            
            if progress_callback:
                progress_callback(95, "Verifying crawl completeness")
            
            # Check if we missed any pages by re-examining all links
            for page_data in results:
                if page_data["soup"]:
                    urls = self._extract_urls(page_data["soup"], page_data["url"])
                    
                    for url in urls:
                        if url not in self.visited_urls:
                            logger.info(f"Found missed URL during verification: {url}")
                            
                            # Fetch the missed page
                            missed_page = self.fetch_page(url)
                            
                            if missed_page["status"] == "success":
                                # Convert HTML to markdown
                                markdown = self.html_to_markdown(missed_page["html"], url)
                                
                                # Generate unique filename
                                parsed_url = urlparse(url)
                                filename = parsed_url.netloc + parsed_url.path.replace('/', '_')
                                if not filename.endswith('.md'):
                                    filename += '.md'
                                
                                # Save to temp directory
                                file_path = self.temp_dir / filename
                                with open(file_path, 'w', encoding='utf-8') as f:
                                    f.write(markdown)
                                
                                # Add to results
                                missed_page["markdown"] = markdown
                                missed_page["local_path"] = str(file_path)
                                results.append(missed_page)
                                
                                # Mark as visited
                                self.visited_urls.add(url)
            
            logger.info(f"Verification round complete, final page count: {len(results)}")
        
        # Final progress update
        if progress_callback:
            progress_callback(100, f"Completed crawl with {len(results)} pages")
        
        # Clean up temporary files if requested
        if cleanup_temp:
            logger.info("Cleaning up temporary files")
            for page_data in results:
                if "local_path" in page_data and page_data["local_path"]:
                    try:
                        # Store the markdown in a content field before removing the file
                        if os.path.exists(page_data["local_path"]):
                            with open(page_data["local_path"], 'r', encoding='utf-8') as f:
                                # Make sure we have the content in memory before deleting the file
                                if "markdown" not in page_data or not page_data["markdown"]:
                                    page_data["markdown"] = f.read()
                            
                            # Remove the file
                            os.remove(page_data["local_path"])
                            logger.debug(f"Removed temporary file: {page_data['local_path']}")
                    except Exception as e:
                        logger.error(f"Error cleaning up temporary file {page_data.get('local_path')}: {e}")
        
        return results

    def prepare_data_for_dataset(self, crawled_data):
        """
        Prepare crawled data for dataset creation.
        
        Args:
            crawled_data: List of crawled page data
            
        Returns:
            list: List of file data for dataset creation
        """
        file_data_list = []
        
        for page in crawled_data:
            file_data = {
                "path": page["url"],
                "local_path": page["local_path"],
                "format": "markdown",
                "url": page["url"],
                "title": page["title"] or "Unknown Title",
                "description": page["meta_description"] or "",
                "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "content_type": "text/markdown"
            }
            
            # Add to file data list
            file_data_list.append(file_data)
        
        return file_data_list

    def export_to_knowledge_graph(self, crawled_data):
        """
        Export crawled data to Neo4j knowledge graph.
        
        Args:
            crawled_data: List of crawled page data
            
        Returns:
            bool: Whether export was successful
        """
        try:
            # Import here to avoid dependency issues
            from knowledge_graph.graph_store import GraphStore
            
            # Initialize graph store
            graph_store = GraphStore()
            
            # Add documents to graph
            for page in crawled_data:
                # Basic document metadata
                document_data = {
                    "url": page["url"],
                    "title": page["title"] or "Unknown Title",
                    "description": page["meta_description"] or "",
                    "content": page["markdown"],
                    "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S")
                }
                
                # Add document to graph
                document_id = graph_store.add_document(document_data)
                
                # Extract concepts and entities if available
                try:
                    from transformers import pipeline
                    
                    # Initialize NER pipeline
                    ner_pipe = pipeline("ner", model="dslim/bert-base-NER")
                    
                    # Extract entities from markdown
                    entities = ner_pipe(page["markdown"])
                    
                    # Group entities
                    grouped_entities = {}
                    for entity in entities:
                        if entity["entity"].startswith("B-"):
                            entity_type = entity["entity"][2:]
                            if entity_type not in grouped_entities:
                                grouped_entities[entity_type] = []
                            grouped_entities[entity_type].append(entity["word"])
                    
                    # Add entities to graph
                    for entity_type, entity_words in grouped_entities.items():
                        for word in entity_words:
                            graph_store.add_entity(word, entity_type, document_id)
                            
                except ImportError:
                    logger.warning("transformers not installed, skipping entity extraction")
                    
                except Exception as e:
                    logger.error(f"Error extracting entities: {e}")
            
            return True
            
        except ImportError:
            logger.warning("Neo4j not configured, skipping knowledge graph export")
            return False
            
        except Exception as e:
            logger.error(f"Error exporting to knowledge graph: {e}")
            return False