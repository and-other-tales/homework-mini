"""
Exceptions related to GitHub API interactions.
"""


class GitHubAPIError(Exception):
    """Exception raised when GitHub API returns an error."""

    def __init__(self, message, status_code=None, response=None):
        self.status_code = status_code
        self.response = response
        super().__init__(message)