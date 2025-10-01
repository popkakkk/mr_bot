from typing import List, Optional, Literal
from dataclasses import dataclass
from enum import Enum

# Type aliases for better type safety
MRState = Literal["pending", "created", "existing", "merged", "failed", "no_commits"]
EnvironmentName = Literal["dev2", "sit2", "all"]

class DeploymentPhase(Enum):
    LIBRARIES = "libraries"
    SERVICES = "services"

@dataclass
class MRStatus:
    """Status tracking for a merge request."""
    repo_name: str
    source_branch: str
    target_branch: str
    mr_id: Optional[int] = None
    mr_url: Optional[str] = None
    state: MRState = "pending"
    error: Optional[str] = None
    commit_count: int = 0
    
    @property
    def is_successful(self) -> bool:
        """Check if MR was successfully merged."""
        return self.state == "merged"
    
    @property
    def is_failed(self) -> bool:
        """Check if MR failed."""
        return self.state == "failed"
    
    @property
    def is_active(self) -> bool:
        """Check if MR is actively being processed."""
        return self.state in ["created", "existing"]

@dataclass
class DeploymentProgress:
    """Progress tracking for deployment phases."""
    phase: DeploymentPhase
    environment: str
    completed_repos: List[str]
    failed_repos: List[str]
    in_progress_repos: List[str]
    pending_repos: List[str]
    
    @property
    def total_repos(self) -> int:
        """Total number of repositories in this deployment."""
        return len(self.completed_repos + self.failed_repos + self.in_progress_repos + self.pending_repos)
    
    @property
    def success_rate(self) -> float:
        """Success rate as percentage."""
        if self.total_repos == 0:
            return 0.0
        return (len(self.completed_repos) / self.total_repos) * 100
    
    @property
    def is_complete(self) -> bool:
        """Check if deployment phase is complete."""
        return len(self.in_progress_repos) == 0 and len(self.pending_repos) == 0