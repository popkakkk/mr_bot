import logging
import time
from typing import Dict, List, Optional, Tuple

from gitlab_client import GitLabClient
from models import DeploymentPhase, MRStatus, DeploymentProgress
from config_manager import ConfigManager

logger = logging.getLogger(__name__)


class MRValidationService:
    """Service for validating repositories and branches."""
    
    def __init__(self, gitlab_client: GitLabClient, config_manager: ConfigManager):
        self.gitlab = gitlab_client
        self.config = config_manager
    
    def validate_repository(self, repo_name: str, source_branch: str) -> Tuple[bool, Optional[str], int]:
        """Validate a single repository for deployment readiness."""
        try:
            # Check if source branch exists
            if not self.gitlab.branch_exists(repo_name, source_branch):
                return False, f"Source branch {source_branch} does not exist", 0
            
            # Get target branch
            flow = self.config.get_repository_flow(repo_name)
            try:
                source_index = flow.index(source_branch)
                if source_index >= len(flow) - 1:
                    return False, f"Source branch {source_branch} is already the final branch", 0
                
                target_branch = flow[source_index + 1]
            except ValueError:
                return False, f"Source branch {source_branch} not found in flow", 0
            
            # Check if target branch exists
            if not self.gitlab.branch_exists(repo_name, target_branch):
                return False, f"Target branch {target_branch} does not exist", 0
            
            # Check for new commits
            has_commits, commit_count = self.gitlab.validate_commits(repo_name, source_branch, target_branch)
            if not has_commits:
                return False, "No new commits to merge", 0
            
            return True, None, commit_count
            
        except Exception as e:
            logger.error(f"Error validating repository {repo_name}: {e}")
            return False, str(e), 0
    
    def validate_repositories(self, repos: List[str], source_branch: str) -> List[str]:
        """Validate multiple repositories and return only valid ones."""
        valid_repos = []
        
        for repo in repos:
            is_valid, error, commit_count = self.validate_repository(repo, source_branch)
            
            if is_valid:
                valid_repos.append(repo)
                logger.info(f"Repository {repo} is valid for deployment ({commit_count} commits)")
            else:
                logger.warning(f"Repository {repo} validation failed: {error}")
        
        return valid_repos


class MRCreationService:
    """Service for creating merge requests."""
    
    def __init__(self, gitlab_client: GitLabClient, config_manager: ConfigManager):
        self.gitlab = gitlab_client
        self.config = config_manager
    
    def create_single_mr(self, repo_name: str, source_branch: str, sprint_name: str) -> MRStatus:
        """Create a single merge request."""
        try:
            flow = self.config.get_repository_flow(repo_name)
            source_index = flow.index(source_branch)
            target_branch = flow[source_index + 1]
            
            # Validate commits
            has_commits, commit_count = self.gitlab.validate_commits(repo_name, source_branch, target_branch)
            
            mr_status = MRStatus(
                repo_name=repo_name,
                source_branch=source_branch,
                target_branch=target_branch,
                commit_count=commit_count
            )
            
            if not has_commits:
                mr_status.state = "no_commits"
                mr_status.error = "No new commits to merge"
                return mr_status
            
            # Create MR
            automation_config = self.config.get_automation_config()
            mr_result = self.gitlab.create_merge_request(
                repo_name, source_branch, target_branch, sprint_name,
                auto_merge=automation_config['auto_merge']
            )
            
            if mr_result:
                mr_status.mr_id = mr_result['id']
                mr_status.mr_url = mr_result['web_url']
                mr_status.state = "created"
                logger.info(f"Created MR for {repo_name}: {mr_result['web_url']}")
            else:
                mr_status.state = "failed"
                mr_status.error = "Failed to create MR"
            
            return mr_status
            
        except Exception as e:
            logger.error(f"Failed to create MR for {repo_name}: {e}")
            return MRStatus(
                repo_name=repo_name,
                source_branch=source_branch,
                target_branch="",
                state="failed",
                error=str(e)
            )
    
    def create_mrs_for_repositories(self, repos: List[str], source_branch: str, 
                                  sprint_name: str) -> List[MRStatus]:
        """Create merge requests for multiple repositories."""
        mrs = []
        for repo in repos:
            mr_status = self.create_single_mr(repo, source_branch, sprint_name)
            mrs.append(mr_status)
        return mrs


class MRMonitoringService:
    """Service for monitoring merge request status."""
    
    def __init__(self, gitlab_client: GitLabClient, config_manager: ConfigManager):
        self.gitlab = gitlab_client
        self.config = config_manager
    
    def monitor_single_mr(self, mr_status: MRStatus) -> MRStatus:
        """Monitor a single merge request."""
        if mr_status.state not in ["created", "existing"] or not mr_status.mr_id:
            return mr_status
        
        try:
            automation_config = self.config.get_automation_config()
            success, final_state = self.gitlab.monitor_merge_status(
                mr_status.repo_name, 
                mr_status.mr_id,
                timeout=automation_config['pipeline_timeout']
            )
            
            if success:
                mr_status.state = "merged"
                logger.info(f"MR merged successfully for {mr_status.repo_name}")
            else:
                mr_status.state = "failed"
                mr_status.error = f"Merge failed: {final_state}"
                logger.error(f"MR failed for {mr_status.repo_name}: {final_state}")
                
        except Exception as e:
            logger.error(f"Error monitoring MR for {mr_status.repo_name}: {e}")
            mr_status.state = "failed"
            mr_status.error = str(e)
        
        return mr_status
    
    def monitor_multiple_mrs(self, mr_statuses: List[MRStatus]) -> List[MRStatus]:
        """Monitor multiple merge requests."""
        active_mrs = [mr for mr in mr_statuses if mr.state in ["created", "existing"] and mr.mr_id]
        
        if not active_mrs:
            return mr_statuses
        
        logger.info(f"Monitoring {len(active_mrs)} active merge requests...")
        
        for mr_status in active_mrs:
            self.monitor_single_mr(mr_status)
        
        return mr_statuses


class DeploymentService:
    """Service for handling deployment operations."""
    
    def __init__(self, gitlab_client: GitLabClient, config_manager: ConfigManager):
        self.gitlab = gitlab_client
        self.config = config_manager
    
    def wait_for_environment_deployment(self, repos: List[str], environment: str) -> bool:
        """Wait for deployment to complete in specified environment."""
        env_config = self.config.get_environment_config(environment)
        
        if not env_config:
            logger.warning(f"Environment {environment} not configured for deployment monitoring")
            return True
        
        if not env_config.wait_for_deployment:
            return True
        
        logger.info(f"Waiting for deployment to {environment} environment...")
        
        all_deployed = True
        automation_config = self.config.get_automation_config()
        
        for repo in repos:
            try:
                success = self.gitlab.wait_for_deployment(
                    repo, environment,
                    timeout=automation_config['deployment_timeout']
                )
                
                if not success:
                    logger.error(f"Deployment failed for {repo} in {environment}")
                    all_deployed = False
                else:
                    logger.info(f"Deployment successful for {repo} in {environment}")
                    
            except Exception as e:
                logger.error(f"Error waiting for deployment of {repo} in {environment}: {e}")
                all_deployed = False
        
        return all_deployed


class MRAutomation:
    """Main MR automation orchestrator with refactored services."""
    
    def __init__(self, gitlab_client: GitLabClient, discord_notifier, config_manager: ConfigManager):
        self.gitlab = gitlab_client
        self.discord = discord_notifier
        self.config = config_manager
        self.mr_statuses: List[MRStatus] = []
        
        # Initialize services
        self.validation_service = MRValidationService(gitlab_client, config_manager)
        self.creation_service = MRCreationService(gitlab_client, config_manager)
        self.monitoring_service = MRMonitoringService(gitlab_client, config_manager)
        self.deployment_service = DeploymentService(gitlab_client, config_manager)
    
    # Delegated methods using configuration manager
    def get_repository_strategy(self, repo_name: str) -> Tuple[str, List[str]]:
        """Get repository strategy from config manager."""
        strategy = self.config.get_repository_strategy(repo_name)
        if strategy:
            return strategy.name, strategy.flow
        raise ValueError(f"No strategy found for repository: {repo_name}")
    
    def get_next_branch(self, repo_name: str, current_branch: str) -> Optional[str]:
        """Get next branch in flow for repository."""
        return self.config.get_next_branch(repo_name, current_branch)
    
    def order_repositories(self, repos: List[str]) -> Tuple[List[str], List[str]]:
        """Order repositories into libraries and services."""
        return self.config.order_repositories(repos)
    
    # Service delegation methods
    def validate_repositories(self, repos: List[str], source_branch: str) -> List[str]:
        """Validate repositories using validation service."""
        return self.validation_service.validate_repositories(repos, source_branch)
    
    def create_merge_requests_for_phase(self, repos: List[str], source_branch: str, 
                                      sprint_name: str, phase: DeploymentPhase) -> List[MRStatus]:
        """Create merge requests for a deployment phase."""
        return self.creation_service.create_mrs_for_repositories(repos, source_branch, sprint_name)
    
    def monitor_merge_requests(self, mr_statuses: List[MRStatus]) -> List[MRStatus]:
        """Monitor merge requests using monitoring service."""
        return self.monitoring_service.monitor_multiple_mrs(mr_statuses)
    
    def wait_for_environment_deployment(self, repos: List[str], environment: str) -> bool:
        """Wait for environment deployment using deployment service."""
        return self.deployment_service.wait_for_environment_deployment(repos, environment)
    
    def get_deployment_progress(self, mr_statuses: List[MRStatus], phase: DeploymentPhase) -> DeploymentProgress:
        """Get current deployment progress."""
        completed = [mr.repo_name for mr in mr_statuses if mr.state == "merged"]
        failed = [mr.repo_name for mr in mr_statuses if mr.state == "failed"]
        in_progress = [mr.repo_name for mr in mr_statuses if mr.state == "created"]
        pending = [mr.repo_name for mr in mr_statuses if mr.state == "pending"]
        
        # Determine environment based on target branches
        environment = "unknown"
        if mr_statuses:
            target_branch = mr_statuses[0].target_branch
            config_dict = self.config.load_config()
            for env_name, env_config in config_dict['environments'].items():
                if target_branch in env_config['triggered_by']:
                    environment = env_name
                    break
        
        return DeploymentProgress(
            phase=phase,
            environment=environment,
            completed_repos=completed,
            failed_repos=failed,
            in_progress_repos=in_progress,
            pending_repos=pending
        )
    
    def create_next_phase_mrs(self, successful_repos: List[str], sprint_name: str) -> List[MRStatus]:
        """Create merge requests for the next phase."""
        next_mrs = []
        
        for repo in successful_repos:
            try:
                flow = self.config.get_repository_flow(repo)
                
                # Find current position and create MR for next step
                for i in range(len(flow) - 2):  # Skip last branch (no next step)
                    current_branch = flow[i + 1]  # Target from previous step becomes source
                    next_branch = flow[i + 2]
                    
                    # Check if we need to create this MR
                    has_commits, commit_count = self.gitlab.validate_commits(repo, current_branch, next_branch)
                    
                    if has_commits:
                        automation_config = self.config.get_automation_config()
                        mr_result = self.gitlab.create_merge_request(
                            repo, current_branch, next_branch, sprint_name,
                            auto_merge=automation_config['auto_merge']
                        )
                        
                        mr_status = MRStatus(
                            repo_name=repo,
                            source_branch=current_branch,
                            target_branch=next_branch,
                            commit_count=commit_count
                        )
                        
                        if mr_result:
                            mr_status.mr_id = mr_result['id']
                            mr_status.mr_url = mr_result['web_url']
                            mr_status.state = "created"
                        else:
                            mr_status.state = "failed"
                            mr_status.error = "Failed to create next phase MR"
                        
                        next_mrs.append(mr_status)
                        break  # Only create one MR at a time per repo
            
            except Exception as e:
                logger.error(f"Failed to create next phase MR for {repo}: {e}")
        
        return next_mrs
    
    def find_branches_with_new_commits(self, repos: List[str], after_merge_branch: str, 
                                     final_target_branch: str) -> Dict[str, List[Tuple[str, int]]]:
        """Find branches with new commits between merge and final target branch."""
        repo_branches = {}
        
        for repo in repos:
            try:
                branches_with_commits = self.gitlab.get_branches_with_new_commits(
                    repo, after_merge_branch, final_target_branch
                )
                if branches_with_commits:
                    repo_branches[repo] = branches_with_commits
                    logger.info(f"Found branches with new commits in {repo}: {len(branches_with_commits)}")
            except Exception as e:
                logger.error(f"Failed to find branches with new commits for {repo}: {e}")
                continue
        
        return repo_branches
    
    def create_additional_merge_requests(self, repo_branches: Dict[str, List[Tuple[str, int]]], 
                                       final_target_branch: str, sprint_name: str) -> List[MRStatus]:
        """Create MRs for branches with new commits to final target branch."""
        additional_mrs = []
        
        for repo, branches in repo_branches.items():
            for branch_name, commit_count in branches:
                try:
                    commit_details = self.gitlab.get_commit_details(repo, branch_name, final_target_branch)
                    
                    mr_status = MRStatus(
                        repo_name=repo,
                        source_branch=branch_name,
                        target_branch=final_target_branch,
                        commit_count=commit_count
                    )
                    
                    automation_config = self.config.get_automation_config()
                    mr_result = self.gitlab.create_merge_request_with_commits(
                        repo, branch_name, final_target_branch, sprint_name,
                        commit_details, auto_merge=automation_config['auto_merge']
                    )
                    
                    if mr_result:
                        mr_status.mr_id = mr_result['id']
                        mr_status.mr_url = mr_result['web_url']
                        mr_status.state = "created"
                        logger.info(f"Created additional MR for {repo}: {branch_name} → {final_target_branch}")
                    else:
                        mr_status.state = "failed"
                        mr_status.error = "Failed to create additional MR"
                    
                    additional_mrs.append(mr_status)
                    
                except Exception as e:
                    logger.error(f"Failed to create additional MR for {repo}:{branch_name}: {e}")
                    mr_status = MRStatus(
                        repo_name=repo,
                        source_branch=branch_name,
                        target_branch=final_target_branch,
                        state="failed",
                        error=str(e),
                        commit_count=commit_count
                    )
                    additional_mrs.append(mr_status)
        
        return additional_mrs
    
    def find_intermediate_branch_commits(self, repos: List[str], final_target_branch: str) -> Dict[str, Dict[str, Tuple[int, List[Dict]]]]:
        """Find commits in intermediate branches not in final target branch."""
        repo_intermediate_commits = {}
        
        for repo in repos:
            try:
                flow = self.config.get_repository_flow(repo)
                intermediate_commits = self.gitlab.get_intermediate_branch_commits(repo, flow, final_target_branch)
                
                if intermediate_commits:
                    repo_intermediate_commits[repo] = intermediate_commits
                    total_commits = sum(count for count, _ in intermediate_commits.values())
                    logger.info(f"Found {total_commits} intermediate commits in {repo} across {len(intermediate_commits)} branches")
                
            except Exception as e:
                logger.error(f"Failed to find intermediate commits for {repo}: {e}")
                continue
        
        return repo_intermediate_commits
    
    def create_intermediate_merge_requests(self, repo_intermediate_commits: Dict[str, Dict[str, Tuple[int, List[Dict]]]], 
                                         final_target_branch: str, sprint_name: str) -> List[MRStatus]:
        """Create MRs for intermediate branch commits."""
        intermediate_mrs = []
        
        for repo, branch_commits in repo_intermediate_commits.items():
            for intermediate_branch, (commit_count, commit_details) in branch_commits.items():
                try:
                    mr_status = MRStatus(
                        repo_name=repo,
                        source_branch=intermediate_branch,
                        target_branch=final_target_branch,
                        commit_count=commit_count
                    )
                    
                    automation_config = self.config.get_automation_config()
                    mr_result = self.gitlab.create_merge_request_with_commits(
                        repo, intermediate_branch, final_target_branch, sprint_name,
                        commit_details, auto_merge=automation_config['auto_merge']
                    )
                    
                    if mr_result:
                        mr_status.mr_id = mr_result['id']
                        mr_status.mr_url = mr_result['web_url']
                        mr_status.state = "created"
                        logger.info(f"Created intermediate MR for {repo}: {intermediate_branch} → {final_target_branch}")
                    else:
                        mr_status.state = "failed"
                        mr_status.error = "Failed to create intermediate MR"
                    
                    intermediate_mrs.append(mr_status)
                    
                except Exception as e:
                    logger.error(f"Failed to create intermediate MR for {repo}:{intermediate_branch}: {e}")
                    mr_status = MRStatus(
                        repo_name=repo,
                        source_branch=intermediate_branch,
                        target_branch=final_target_branch,
                        state="failed",
                        error=str(e),
                        commit_count=commit_count
                    )
                    intermediate_mrs.append(mr_status)
        
        return intermediate_mrs
    
    def process_additional_commits(self, repos: List[str], current_target_branch: str, 
                                 final_target_branch: str, sprint_name: str) -> List[MRStatus]:
        """Process additional commits from various branches."""
        logger.info(f"Processing additional commits for {len(repos)} repositories")
        
        all_additional_mrs = []
        
        # Find branches with new commits
        repo_branches = self.find_branches_with_new_commits(repos, current_target_branch, final_target_branch)
        
        if repo_branches:
            total_branches = sum(len(branches) for branches in repo_branches.values())
            logger.info(f"Found {total_branches} additional branches with new commits")
            
            additional_mrs = self.create_additional_merge_requests(repo_branches, final_target_branch, sprint_name)
            all_additional_mrs.extend(additional_mrs)
        
        # Find intermediate branch commits
        repo_intermediate_commits = self.find_intermediate_branch_commits(repos, final_target_branch)
        
        if repo_intermediate_commits:
            total_intermediate_commits = sum(
                sum(count for count, _ in branch_commits.values()) 
                for branch_commits in repo_intermediate_commits.values()
            )
            logger.info(f"Found {total_intermediate_commits} intermediate branch commits")
            
            intermediate_mrs = self.create_intermediate_merge_requests(repo_intermediate_commits, final_target_branch, sprint_name)
            all_additional_mrs.extend(intermediate_mrs)
        
        # Create progressive MRs
        progressive_mrs = self.create_progressive_merge_requests(repos, sprint_name)
        if progressive_mrs:
            logger.info(f"Created {len(progressive_mrs)} progressive merge requests")
            all_additional_mrs.extend(progressive_mrs)
        
        if not all_additional_mrs:
            logger.info("No additional commits found in any branches")
            return []
        
        logger.info(f"Created {len(all_additional_mrs)} total additional merge requests")
        return all_additional_mrs
    
    def create_progressive_merge_requests(self, repos: List[str], sprint_name: str) -> List[MRStatus]:
        """Create progressive merge requests for merged branches."""
        progressive_mrs = []
        
        for repo in repos:
            try:
                flow = self.config.get_repository_flow(repo)
                
                for i in range(len(flow) - 1):
                    source_branch = flow[i]
                    target_branch = flow[i + 1]
                    
                    if not self._is_branch_merged_to_target(repo, source_branch, target_branch):
                        continue
                    
                    if i + 1 >= len(flow) - 1:
                        continue
                    
                    next_branch = flow[i + 2]
                    
                    # ตรวจสอบว่า next_branch trigger environment ที่มี wait_for_deployment = true หรือไม่
                    should_stop_at_next = self._should_stop_at_deploy_branch(next_branch)
                    
                    has_commits, commit_count = self.gitlab.validate_commits(repo, target_branch, next_branch)
                    
                    if has_commits:
                        if self._check_existing_mr(repo, target_branch, next_branch):
                            logger.info(f"MR already exists for {repo}: {target_branch} -> {next_branch}")
                            # ถ้าต้องหยุดที่ next_branch นี้ ให้ break
                            if should_stop_at_next:
                                logger.info(f"Stopping at deploy branch {next_branch} due to wait_for_deployment=true")
                                break
                            continue
                        
                        automation_config = self.config.get_automation_config()
                        mr_result = self.gitlab.create_merge_request(
                            repo, target_branch, next_branch, sprint_name,
                            auto_merge=automation_config['auto_merge']
                        )
                        
                        mr_status = MRStatus(
                            repo_name=repo,
                            source_branch=target_branch,
                            target_branch=next_branch,
                            commit_count=commit_count
                        )
                        
                        if mr_result:
                            mr_status.mr_id = mr_result['id']
                            mr_status.mr_url = mr_result['web_url']
                            mr_status.state = "created"
                        else:
                            mr_status.state = "failed"
                            mr_status.error = "Failed to create progressive MR"
                        
                        progressive_mrs.append(mr_status)
                        
                        # ถ้าต้องหยุดที่ next_branch นี้ ให้ break
                        if should_stop_at_next:
                            logger.info(f"Stopping at deploy branch {next_branch} due to wait_for_deployment=true")
                        break
                        
            except Exception as e:
                logger.error(f"Error creating progressive MR for {repo}: {e}")
                continue
        
        return progressive_mrs
    
    def _should_stop_at_deploy_branch(self, target_branch: str) -> bool:
        """
        ตรวจสอบว่า target branch นี้ trigger environment ที่มี wait_for_deployment = true หรือไม่
        
        Args:
            target_branch: branch ที่จะ merge เข้า
        
        Returns:
            True ถ้าต้องหยุดที่ branch นี้เนื่องจาก wait_for_deployment = true
        """
        try:
            config_dict = self.config.load_config()
            for env_name, env_config in config_dict.get('environments', {}).items():
                triggered_by = env_config.get('triggered_by', [])
                wait_for_deployment = env_config.get('wait_for_deployment', False)
                
                if target_branch in triggered_by and wait_for_deployment:
                    logger.debug(f"Target branch {target_branch} triggers {env_name} with wait_for_deployment=true")
                    return True
            
            return False
        except Exception as e:
            logger.debug(f"Error checking deploy branch stop condition for {target_branch}: {e}")
            return False
    
    def _is_branch_merged_to_target(self, repo_name: str, source_branch: str, target_branch: str) -> bool:
        """Check if source branch is merged to target branch."""
        try:
            if not self.gitlab.branch_exists(repo_name, source_branch):
                return False
            
            if not self.gitlab.branch_exists(repo_name, target_branch):
                return False
            
            has_commits, commit_count = self.gitlab.validate_commits(repo_name, source_branch, target_branch)
            return not has_commits
                
        except Exception as e:
            logger.debug(f"Error checking merge status for {repo_name} {source_branch} -> {target_branch}: {e}")
            return False
    
    def _check_existing_mr(self, repo_name: str, source_branch: str, target_branch: str) -> bool:
        """Check if MR already exists for branch pair."""
        # This is a simplified implementation - would need actual GitLab API call
        # in real implementation
        return False