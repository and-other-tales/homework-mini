import os
import sys
import signal
import logging
import threading
import traceback
import atexit
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# Global collections to track threads and executors
_active_threads = set()
_active_executors = set()
_lock = threading.RLock()


def register_executor(executor):
    """
    Register a ThreadPoolExecutor to ensure proper cleanup on exit.

    Args:
        executor: ThreadPoolExecutor instance to register

    Returns:
        The registered executor
    """
    if not isinstance(executor, ThreadPoolExecutor):
        raise TypeError("Only ThreadPoolExecutor instances can be registered")

    with _lock:
        _active_executors.add(executor)

    return executor


def register_thread(thread):
    """
    Register a Thread to ensure proper cleanup on exit.

    Args:
        thread: Thread instance to register

    Returns:
        The registered thread
    """
    if not isinstance(thread, threading.Thread):
        raise TypeError("Only Thread instances can be registered")

    with _lock:
        _active_threads.add(thread)

    return thread


def unregister_thread(thread):
    """Remove a thread from the cleanup registry."""
    with _lock:
        _active_threads.discard(thread)


def cleanup_resources():
    """Clean up all registered resources."""
    # Shutdown executors
    with _lock:
        for executor in list(_active_executors):
            try:
                logger.debug(f"Shutting down executor: {executor}")
                executor.shutdown(wait=False)
            except Exception as e:
                logger.error(f"Error shutting down executor: {e}")
            finally:
                _active_executors.discard(executor)

    # Try to join non-daemon threads, but don't remove them unless they're done
    joined_threads = []
    for thread in list(_active_threads):
        if thread.is_alive() and thread != threading.current_thread():
            try:
                logger.debug(f"Joining thread: {thread.name}")
                thread.join(timeout=0.1)  # Short timeout to avoid hanging
                if not thread.is_alive():
                    joined_threads.append(thread)
            except Exception as e:
                logger.error(f"Error joining thread {thread.name}: {e}")
        else:
            # Thread is already done
            joined_threads.append(thread)

    # Only remove threads that have actually completed
    with _lock:
        for thread in joined_threads:
            _active_threads.discard(thread)


def handle_signal(signum, frame):
    """Signal handler for clean shutdown."""
    name = signal.Signals(signum).name
    logger.info(f"Received signal {name}. Cleaning up resources...")
    cleanup_resources()
    # Re-raise the signal to allow default handling
    signal.signal(signum, signal.SIG_DFL)
    os.kill(os.getpid(), signum)


# Register cleanup function to run at exit
atexit.register(cleanup_resources)

# Register signal handlers for common termination signals
signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)


def safe_thread(daemon=True):
    """Decorator to create a safe thread that's registered for cleanup."""

    def decorator(func):
        def wrapper(*args, **kwargs):
            thread = threading.Thread(target=func, args=args, kwargs=kwargs)
            thread.daemon = daemon
            register_thread(thread)
            thread.start()
            return thread

        return wrapper

    return decorator


def create_managed_executor(max_workers=None, thread_name_prefix=""):
    """Create a thread pool executor that's registered for cleanup."""
    executor = ThreadPoolExecutor(
        max_workers=max_workers, thread_name_prefix=thread_name_prefix
    )
    register_executor(executor)
    return executor


def excepthook_handler(exc_type, exc_value, exc_traceback):
    """Global exception handler to ensure clean shutdown."""
    # Log the error
    logger.error("Uncaught exception:", exc_info=(exc_type, exc_value, exc_traceback))
    # Clean up resources
    cleanup_resources()
    # Call the default exception handler
    sys.__excepthook__(exc_type, exc_value, exc_traceback)


# Set the global exception handler
sys.excepthook = excepthook_handler
