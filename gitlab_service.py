from typing import Dict, List, Optional, Tuple
import logging
from gitlab_client import GitLabClient
from models import MRState

logger = logging.getLogger(__name__)


class GitLabRepositoryService:
    """Service layer for GitLab repository operations."""
    
    def __init__(self, gitlab_client: GitLabClient):
        self.client = gitlab_client
    
    def validate_branch_exists(self, repo_name: str, branch_name: str) -> bool:
        """Check if branch exists in repository."""
        return self.client.branch_exists(repo_name, branch_name)
    
    def get_commit_comparison(self, repo_name: str, source_branch: str, 
                            target_branch: str) -> Tuple[bool, int]:
        """Compare commits between source and target branches."""
        return self.client.validate_commits(repo_name, source_branch, target_branch)
    
    def get_branch_commit_details(self, repo_name: str, source_branch: str, 
                                target_branch: str) -> List[Dict]:
        """Get detailed commit information between branches."""
        return self.client.get_commit_details(repo_name, source_branch, target_branch)


class GitLabMRService:
    """Service layer for GitLab merge request operations."""
    
    def __init__(self, gitlab_client: GitLabClient):
        self.client = gitlab_client
    
    def create_merge_request(self, repo_name: str, source_branch: str, 
                           target_branch: str, title: str, 
                           auto_merge: bool = False) -> Optional[Dict]:
        """Create a merge request."""
        return self.client.create_merge_request(
            repo_name, source_branch, target_branch, title, auto_merge=auto_merge
        )
    
    def create_enhanced_merge_request(self, repo_name: str, source_branch: str,
                                    target_branch: str, title: str,
                                    commit_details: List[Dict],
                                    auto_merge: bool = False) -> Optional[Dict]:
        """Create merge request with enhanced commit details."""
        return self.client.create_merge_request_with_commits(
            repo_name, source_branch, target_branch, title, 
            commit_details, auto_merge=auto_merge
        )
    
    def monitor_merge_status(self, repo_name: str, mr_id: int, 
                           timeout: int = 1800) -> Tuple[bool, str]:
        """Monitor merge request until completion or timeout."""
        return self.client.monitor_merge_status(repo_name, mr_id, timeout)
    
    def enable_auto_merge_batch(self, repo_name: str, mr_ids: List[int]) -> Dict[int, bool]:
        """Enable auto-merge for multiple MRs."""
        return self.client.enable_auto_merge_for_ready_mrs(repo_name, mr_ids)


class GitLabDeploymentService:
    """Service layer for GitLab deployment operations."""
    
    def __init__(self, gitlab_client: GitLabClient):
        self.client = gitlab_client
    
    def get_deployment_status(self, repo_name: str, environment: str) -> Optional[str]:
        """Get current deployment status for environment."""
        return self.client.get_deployment_status(repo_name, environment)
    
    def wait_for_deployment(self, repo_name: str, environment: str, 
                          timeout: int = 3600) -> bool:
        """Wait for deployment completion."""
        return self.client.wait_for_deployment(repo_name, environment, timeout)
    
    def get_pipeline_status(self, repo_name: str, branch_name: str) -> Optional[str]:
        """Get pipeline status for branch."""
        return self.client.check_pipeline_status(repo_name, branch_name)


class GitLabBranchDiscoveryService:
    """Service layer for discovering branches and commits."""
    
    def __init__(self, gitlab_client: GitLabClient):
        self.client = gitlab_client
    
    def find_branches_with_new_commits(self, repo_name: str, after_merge_branch: str,
                                     final_target_branch: str) -> List[Tuple[str, int]]:
        """Find branches with new commits between merge and target branches."""
        return self.client.get_branches_with_new_commits(
            repo_name, after_merge_branch, final_target_branch
        )
    
    def find_intermediate_commits(self, repo_name: str, branch_flow: List[str],
                                final_target_branch: str) -> Dict[str, Tuple[int, List[Dict]]]:
        """Find commits in intermediate branches not in final target."""
        return self.client.get_intermediate_branch_commits(
            repo_name, branch_flow, final_target_branch
        )


class GitLabServiceFacade:
    """Facade providing high-level GitLab operations."""
    
    def __init__(self, gitlab_client: GitLabClient):
        self.client = gitlab_client
        self.repository = GitLabRepositoryService(gitlab_client)
        self.merge_requests = GitLabMRService(gitlab_client)
        self.deployments = GitLabDeploymentService(gitlab_client)
        self.branch_discovery = GitLabBranchDiscoveryService(gitlab_client)
    
    def validate_repository_for_deployment(self, repo_name: str, source_branch: str,
                                         target_branch: str) -> Tuple[bool, Optional[str], int]:
        """Comprehensive repository validation for deployment."""
        # Check source branch exists
        if not self.repository.validate_branch_exists(repo_name, source_branch):
            return False, f"Source branch {source_branch} does not exist", 0
        
        # Check target branch exists
        if not self.repository.validate_branch_exists(repo_name, target_branch):
            return False, f"Target branch {target_branch} does not exist", 0
        
        # Check for commits to merge
        has_commits, commit_count = self.repository.get_commit_comparison(
            repo_name, source_branch, target_branch
        )
        
        if not has_commits:
            return False, "No new commits to merge", 0
        
        return True, None, commit_count
    
    def create_and_monitor_merge_request(self, repo_name: str, source_branch: str,
                                       target_branch: str, title: str,
                                       auto_merge: bool = False,
                                       timeout: int = 1800) -> Tuple[bool, Optional[Dict], str]:
        """Create MR and monitor until completion."""
        # Create MR
        mr_result = self.merge_requests.create_merge_request(
            repo_name, source_branch, target_branch, title, auto_merge
        )
        
        if not mr_result:
            return False, None, "Failed to create merge request"
        
        # Monitor MR
        success, final_state = self.merge_requests.monitor_merge_status(
            repo_name, mr_result['id'], timeout
        )
        
        return success, mr_result, final_state
    
    def batch_deployment_validation(self, repo_configs: List[Tuple[str, str, str]]) -> Dict[str, Tuple[bool, Optional[str], int]]:
        """Validate multiple repositories for deployment in batch."""
        results = {}
        
        for repo_name, source_branch, target_branch in repo_configs:
            is_valid, error, commit_count = self.validate_repository_for_deployment(
                repo_name, source_branch, target_branch
            )
            results[repo_name] = (is_valid, error, commit_count)
        
        return results
    
    def batch_environment_deployment_wait(self, repo_env_configs: List[Tuple[str, str]],
                                        timeout: int = 3600) -> Dict[str, bool]:
        """Wait for deployment completion across multiple repo-environment pairs."""
        results = {}
        
        for repo_name, environment in repo_env_configs:
            try:
                success = self.deployments.wait_for_deployment(repo_name, environment, timeout)
                results[f"{repo_name}:{environment}"] = success
            except Exception as e:
                logger.error(f"Error waiting for deployment {repo_name}:{environment}: {e}")
                results[f"{repo_name}:{environment}"] = False
        
        return results