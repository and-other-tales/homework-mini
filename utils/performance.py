import time
import logging
import threading
import multiprocessing
from functools import wraps
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional
from utils.system_helpers import (
    register_executor,
)  # Changed from register_executor_for_shutdown

logger = logging.getLogger(__name__)


def timing_decorator(func):
    """Decorator to measure execution time of functions."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        logger.debug(
            f"Function {func.__name__} took {end_time - start_time:.2f} seconds to execute"
        )
        return result

    return wrapper


class BackgroundTask:
    """Manages a task running in the background."""

    def __init__(
        self, target: Callable, args=None, kwargs=None, on_complete=None, on_error=None
    ):
        """Initialize a background task.

        Args:
            target: The function to execute
            args: Positional arguments for the target function
            kwargs: Keyword arguments for the target function
            on_complete: Callback when task completes successfully
            on_error: Callback when task fails
        """
        self.target = target
        self.args = args or ()
        self.kwargs = kwargs or {}
        self.on_complete = on_complete
        self.on_error = on_error
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.future = None
        self._is_cancelled = threading.Event()
        self._original_kwargs = dict(kwargs or {})

        # Register the executor for cleanup
        register_executor(self.executor)  # Changed from register_executor_for_shutdown

    def start(self):
        """Start the background task."""
        if self.future is not None and not self.future.done():
            logger.warning("Task is already running")
            return

        # Update kwargs to include the cancellation event
        self.kwargs = dict(self._original_kwargs)
        self.kwargs["_cancellation_event"] = self._is_cancelled

        def wrapped_target(*args, **kwargs):
            try:
                # Remove _cancellation_event from kwargs before passing to target
                # if the target doesn't expect it
                if (
                    "_cancellation_event" in kwargs
                    and "_cancellation_event" not in self.target.__code__.co_varnames
                ):
                    cancellation_event = kwargs.pop("_cancellation_event")
                result = self.target(*args, **kwargs)
                if not self._is_cancelled.is_set() and self.on_complete:
                    self.on_complete(result)
                return result
            except Exception as e:
                if not self._is_cancelled.is_set() and self.on_error:
                    self.on_error(e)
                else:
                    logger.error(f"Error in background task: {e}")
                raise

        self.future = self.executor.submit(wrapped_target, *self.args, **self.kwargs)
        return self.future

    def stop(self):
        """Stop the background task."""
        if self.future:
            # Signal cancellation
            self._is_cancelled.set()

            # Cancel the future if supported
            if hasattr(self.future, "cancel"):
                self.future.cancel()

            # Shutdown the executor to force interruption
            self.executor.shutdown(wait=False)

            # Create a new executor for future tasks
            self.executor = ThreadPoolExecutor(max_workers=1)
            register_executor(
                self.executor
            )  # Changed from register_executor_for_shutdown

            logger.info("Background task cancelled")
            return True
        return False

    def is_running(self):
        """Check if the task is still running."""
        return self.future is not None and not self.future.done()

    def is_cancelled(self):
        """Check if the task has been cancelled."""
        return self._is_cancelled.is_set()


def parallel_process(
    items, process_func, max_workers=None, chunk_size=1, progress_callback=None
):
    """Process items in parallel using multiprocessing."""
    if max_workers is None:
        # Use less workers than CPU count to avoid overwhelming the system
        max_workers = max(1, multiprocessing.cpu_count() - 1)

    with multiprocessing.Pool(max_workers) as pool:
        # Use imap_unordered if ordered results aren't required for better performance
        if progress_callback is not None:
            # Process with progress reporting
            results = []
            total = len(items)
            for i, result in enumerate(pool.imap(process_func, items, chunk_size)):
                results.append(result)
                if (
                    i % 10 == 0 or i == total - 1
                ):  # Update progress every 10 items or at the end
                    progress_callback(i / total)
        else:
            # Standard processing without progress reporting
            results = pool.map(process_func, items, chunk_size)

    return results


def distributed_process(
    items, process_func, rank=0, world_size=1, chunk_size=1, **kwargs
):
    """
    Process items in a distributed fashion across different processes or nodes.

    Args:
        items: List of items to process
        process_func: Function to process each item
        rank: Rank of current process (default: 0)
        world_size: Total number of processes (default: 1)
        chunk_size: Number of items to process in each batch (default: 1)
        **kwargs: Additional arguments to pass to process_func

    Returns:
        List of processed items assigned to this rank
    """
    # Validate rank and world_size
    if rank < 0 or rank >= world_size:
        return []  # Return empty list for invalid ranks

    # Extract progress_callback to handle separately
    progress_callback = kwargs.pop("progress_callback", None)

    # Distribute items among processes
    results = []
    item_count = 0
    total_assigned = len([i for i in range(rank, len(items), world_size)])

    for i in range(rank, len(items), world_size):
        result = process_func(items[i])
        results.append(result)

        # Update progress
        item_count += 1
        if progress_callback and total_assigned > 0:
            progress = (item_count / total_assigned) * 100
            progress_callback(progress)

    return results


def async_process(items, process_func, max_workers=None, chunk_size=1):
    """Process items asynchronously using a thread pool.

    This is useful for IO-bound operations like downloading or API calls.

    Args:
        items: Items to process.
        process_func: Async function to apply to each item.
        max_workers (int, optional): Maximum number of workers.
        chunk_size (int): Number of items to process at once (default: 1).

    Returns:
        list: Processed items.
    """
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    if max_workers is None:
        max_workers = max(
            1, multiprocessing.cpu_count() * 2
        )  # More threads for IO-bound tasks

    async def process_all():
        # Create new event loop to avoid issues with nested event loops
        loop = asyncio.get_event_loop()
        executor = ThreadPoolExecutor(max_workers=max_workers)
        try:
            # Schedule all tasks
            futures = [
                loop.run_in_executor(executor, process_func, item) for item in items
            ]
            # Gather results as they complete
            return await asyncio.gather(*futures)
        finally:
            # Ensure executor is properly shut down
            executor.shutdown(wait=True)

    try:
        return asyncio.run(process_all())
    except RuntimeError as e:
        if "cannot schedule new futures" in str(e):
            logger.warning(
                "Caught shutdown exception during async processing. Some tasks may not complete."
            )
            # Return partial results or empty list when caught during shutdown
            return []
        raise
