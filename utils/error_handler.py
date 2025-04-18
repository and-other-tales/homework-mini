import logging
import traceback
from github.client import GitHubAPIError, RateLimitError

logger = logging.getLogger(__name__)


class ErrorHandler:
    """Handle and format errors for user display."""

    @staticmethod
    def format_error(exception):
        """Format exception details for display to users."""
        if isinstance(exception, GitHubAPIError):
            if isinstance(exception, RateLimitError):
                return "GitHub API rate limit exceeded. Please try again later or use a different token."
            return f"GitHub API error: {str(exception)}"
        elif isinstance(exception, ValueError):
            return f"Input error: {str(exception)}"
        elif isinstance(exception, FileNotFoundError):
            return f"File not found: {str(exception)}"
        elif isinstance(exception, PermissionError):
            return f"Permission error: {str(exception)}"
        else:
            return f"Error: {str(exception)}"

    @staticmethod
    def log_exception(exception):
        """Log an exception with traceback."""
        error_message = f"Exception: {type(exception).__name__}: {str(exception)}"
        logger.error(error_message)
        logger.error(f"Traceback: {traceback.format_exc()}")

    @staticmethod
    def handle_exception(exception, display_callback=None):
        """Handle exception: log it and optionally display to user."""
        ErrorHandler.log_exception(exception)

        error_message = ErrorHandler.format_error(exception)

        if display_callback:
            display_callback(error_message)

        return False
