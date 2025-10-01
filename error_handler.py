import logging
import time
import functools
from typing import Callable, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class RetryConfig:
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_backoff: bool = True
    exceptions: tuple = (Exception,)

class MRAutomationError(Exception):
    """Base exception for MR Automation errors"""
    pass

class GitLabAPIError(MRAutomationError):
    """GitLab API related errors"""
    pass

class DiscordNotificationError(MRAutomationError):
    """Discord notification errors"""
    pass

class ConfigurationError(MRAutomationError):
    """Configuration validation errors"""
    pass

class DeploymentError(MRAutomationError):
    """Deployment workflow errors"""
    pass

def retry_with_backoff(config: RetryConfig):
    """
    Decorator that implements retry logic with exponential backoff
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            
            for attempt in range(config.max_attempts):
                try:
                    return func(*args, **kwargs)
                except config.exceptions as e:
                    last_exception = e
                    
                    if attempt == config.max_attempts - 1:
                        logger.error(f"Function {func.__name__} failed after {config.max_attempts} attempts: {e}")
                        raise
                    
                    # Calculate delay
                    if config.exponential_backoff:
                        delay = min(config.base_delay * (2 ** attempt), config.max_delay)
                    else:
                        delay = config.base_delay
                    
                    logger.warning(f"Function {func.__name__} failed (attempt {attempt + 1}/{config.max_attempts}), retrying in {delay}s: {e}")
                    time.sleep(delay)
            
            # This should never be reached, but just in case
            raise last_exception
        
        return wrapper
    return decorator

def safe_execute(func: Callable, *args, fallback_value: Any = None, **kwargs) -> Any:
    """
    Safely execute a function and return fallback value on error
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        logger.error(f"Safe execution failed for {func.__name__}: {e}")
        return fallback_value

class ErrorRecoveryManager:
    """
    Manages error recovery strategies for the MR automation workflow
    """
    
    def __init__(self, config: dict):
        self.config = config
        self.retry_config = RetryConfig(
            max_attempts=config['automation'].get('retry_attempts', 3),
            base_delay=config['automation'].get('retry_delay', 30),
            max_delay=300,
            exponential_backoff=True
        )
    
    def handle_gitlab_api_error(self, error: Exception, context: str) -> bool:
        """
        Handle GitLab API errors with appropriate recovery strategies
        """
        logger.error(f"GitLab API error in {context}: {error}")
        
        # Check if it's a rate limit error
        if "rate limit" in str(error).lower():
            logger.warning("Rate limit detected, waiting 60 seconds...")
            time.sleep(60)
            return True  # Retry
        
        # Check if it's a temporary network error
        if any(term in str(error).lower() for term in ["timeout", "connection", "network"]):
            logger.warning("Network error detected, will retry...")
            return True  # Retry
        
        # Check if it's a permission error
        if "permission" in str(error).lower() or "forbidden" in str(error).lower():
            logger.error("Permission error - manual intervention required")
            return False  # Don't retry
        
        # For other errors, retry with backoff
        return True
    
    def handle_merge_conflict(self, repo_name: str, source_branch: str, target_branch: str) -> bool:
        """
        Handle merge conflicts by creating an issue or notification
        """
        logger.error(f"Merge conflict detected in {repo_name}: {source_branch} → {target_branch}")
        
        # In a real implementation, you might:
        # 1. Create a GitLab issue
        # 2. Send detailed Discord notification
        # 3. Attempt automated resolution for simple conflicts
        
        return False  # Requires manual intervention
    
    def handle_pipeline_failure(self, repo_name: str, branch_name: str, pipeline_url: Optional[str] = None) -> bool:
        """
        Handle CI/CD pipeline failures
        """
        logger.error(f"Pipeline failure in {repo_name}:{branch_name}")
        
        # Check if it's a known transient failure
        # In real implementation, you might check specific failure reasons
        
        return False  # Requires manual investigation
    
    def handle_deployment_timeout(self, repo_name: str, environment: str) -> bool:
        """
        Handle deployment timeouts
        """
        logger.error(f"Deployment timeout for {repo_name} in {environment}")
        
        # Could implement status checking or rollback logic here
        return False  # Requires manual intervention
    
    def create_error_context(self, operation: str, repo_name: Optional[str] = None, 
                           branch: Optional[str] = None, **kwargs) -> dict:
        """
        Create standardized error context for logging and notifications
        """
        context = {
            'operation': operation,
            'timestamp': time.time(),
            'repo_name': repo_name,
            'branch': branch
        }
        context.update(kwargs)
        return context

# Decorator for GitLab API calls
def gitlab_api_call(retry_config: Optional[RetryConfig] = None):
    """
    Decorator for GitLab API calls with automatic retry and error handling
    """
    default_config = RetryConfig(
        max_attempts=3,
        base_delay=5.0,
        max_delay=60.0,
        exceptions=(Exception,)
    )
    
    config = retry_config or default_config
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            @retry_with_backoff(config)
            def _wrapped_call():
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    # Convert to appropriate exception type
                    if "gitlab" in str(e).lower() or "api" in str(e).lower():
                        raise GitLabAPIError(f"GitLab API error in {func.__name__}: {e}") from e
                    raise
            
            return _wrapped_call()
        
        return wrapper
    return decorator

# Decorator for Discord notifications
def discord_notification(fallback_on_error: bool = True):
    """
    Decorator for Discord notifications with error handling
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> bool:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Discord notification failed in {func.__name__}: {e}")
                if fallback_on_error:
                    logger.info("Continuing without Discord notification")
                    return True  # Don't fail the entire workflow
                raise DiscordNotificationError(f"Discord notification error: {e}") from e
        
        return wrapper
    return decorator

class WorkflowStateManager:
    """
    Manages workflow state for recovery and resumption
    """
    
    def __init__(self, state_file: str = "mr_automation_state.json"):
        self.state_file = state_file
        self.state = {}
    
    def save_state(self, state: dict):
        """Save workflow state to file"""
        try:
            import json
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
            logger.debug(f"Workflow state saved to {self.state_file}")
        except Exception as e:
            logger.error(f"Failed to save workflow state: {e}")
    
    def load_state(self) -> dict:
        """Load workflow state from file"""
        try:
            import json
            with open(self.state_file, 'r') as f:
                self.state = json.load(f)
            logger.debug(f"Workflow state loaded from {self.state_file}")
            return self.state
        except FileNotFoundError:
            logger.debug("No existing workflow state found")
            return {}
        except Exception as e:
            logger.error(f"Failed to load workflow state: {e}")
            return {}
    
    def clear_state(self):
        """Clear workflow state"""
        try:
            import os
            if os.path.exists(self.state_file):
                os.remove(self.state_file)
            self.state = {}
            logger.debug("Workflow state cleared")
        except Exception as e:
            logger.error(f"Failed to clear workflow state: {e}")

# Context manager for error handling
class ErrorHandlingContext:
    """
    Context manager for structured error handling in workflows
    """
    
    def __init__(self, operation: str, error_manager: ErrorRecoveryManager, 
                 discord_notifier=None, **context):
        self.operation = operation
        self.error_manager = error_manager
        self.discord_notifier = discord_notifier
        self.context = context
        self.start_time = time.time()
    
    def __enter__(self):
        logger.info(f"Starting operation: {self.operation}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        
        if exc_type is None:
            logger.info(f"Operation completed successfully: {self.operation} ({duration:.2f}s)")
            return False
        
        # Handle the error
        logger.error(f"Operation failed: {self.operation} ({duration:.2f}s) - {exc_val}")
        
        # Send critical failure notification if available
        if self.discord_notifier:
            try:
                self.discord_notifier.send_critical_failure(
                    f"Operation '{self.operation}' failed: {exc_val}",
                    self.context.get('repo_name')
                )
            except Exception as notify_error:
                logger.error(f"Failed to send error notification: {notify_error}")
        
        # Don't suppress the exception
        return False