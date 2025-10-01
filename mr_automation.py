import logging
import time
from typing import Dict, List, Optional, Tuple

from gitlab_client import GitLabClient
from models import DeploymentPhase, MRStatus, DeploymentProgress

logger = logging.getLogger(__name__)

class MRAutomation:
    def __init__(self, gitlab_client: GitLabClient, discord_notifier, config: Dict):
        self.gitlab = gitlab_client
        self.discord = discord_notifier
        self.config = config
        self.mr_statuses: List[MRStatus] = []
        
    def get_repository_strategy(self, repo_name: str) -> Tuple[str, List[str]]:
        for strategy_name, strategy_config in self.config['branch_strategies'].items():
            if repo_name in strategy_config['repos']:
                return strategy_name, strategy_config['flow']
        
        raise ValueError(f"No strategy found for repository: {repo_name}")
    
    def get_repository_source_branch(self, repo_name: str) -> str:
        for strategy_name, strategy_config in self.config['branch_strategies'].items():
            if repo_name in strategy_config['repos']:
                return strategy_config['source_branch']
        
        raise ValueError(f"No strategy found for repository: {repo_name}")
    
    def get_next_branch(self, repo_name: str, current_branch: str) -> Optional[str]:
        _, flow = self.get_repository_strategy(repo_name)
        
        try:
            current_index = flow.index(current_branch)
            if current_index < len(flow) - 1:
                return flow[current_index + 1]
        except ValueError:
            logger.error(f"Branch {current_branch} not found in flow for {repo_name}")
        
        return None
    
    def order_repositories(self, repos: List[str]) -> Tuple[List[str], List[str]]:
        libraries = [repo for repo in repos if repo in self.config['repositories']['libraries']]
        services = [repo for repo in repos if repo in self.config['repositories']['services']]
        
        # Order within categories based on config order
        ordered_libraries = [repo for repo in self.config['repositories']['libraries'] if repo in libraries]
        ordered_services = [repo for repo in self.config['repositories']['services'] if repo in services]
        
        return ordered_libraries, ordered_services
    
    def validate_repositories(self, repos: List[str], source_branch: str) -> List[str]:
        valid_repos = []
        
        for repo in repos:
            try:
                # Check if source branch exists
                if not self.gitlab.branch_exists(repo, source_branch):
                    logger.warning(f"Source branch {source_branch} does not exist in {repo}")
                    continue
                
                # Get target branch for this repo
                _, flow = self.get_repository_strategy(repo)
                source_index = flow.index(source_branch)
                if source_index >= len(flow) - 1:
                    logger.warning(f"Source branch {source_branch} is already the final branch in {repo}")
                    continue
                
                target_branch = flow[source_index + 1]
                
                # Check if target branch exists
                if not self.gitlab.branch_exists(repo, target_branch):
                    logger.warning(f"Target branch {target_branch} does not exist in {repo}")
                    continue
                
                # Check for new commits
                has_commits, commit_count = self.gitlab.validate_commits(repo, source_branch, target_branch)
                if not has_commits:
                    logger.info(f"No new commits in {repo} from {source_branch} to {target_branch}")
                    continue
                
                valid_repos.append(repo)
                logger.info(f"Repository {repo} is valid for deployment ({commit_count} commits)")
                
            except Exception as e:
                logger.error(f"Failed to validate repository {repo}: {e}")
                continue
        
        return valid_repos
    
    def validate_repositories_with_strategies(self, repos: List[str]) -> List[str]:
        valid_repos = []
        
        for repo in repos:
            try:
                # Get source branch for this repo from strategy
                source_branch = self.get_repository_source_branch(repo)
                
                # Check if source branch exists
                if not self.gitlab.branch_exists(repo, source_branch):
                    logger.warning(f"Source branch {source_branch} does not exist in {repo}")
                    continue
                
                # Get target branch for this repo
                _, flow = self.get_repository_strategy(repo)
                try:
                    source_index = flow.index(source_branch)
                except ValueError:
                    logger.warning(f"Source branch {source_branch} not found in flow for {repo}")
                    continue
                    
                if source_index >= len(flow) - 1:
                    logger.warning(f"Source branch {source_branch} is already the final branch in {repo}")
                    continue
                
                target_branch = flow[source_index + 1]
                
                # Check if target branch exists
                if not self.gitlab.branch_exists(repo, target_branch):
                    logger.warning(f"Target branch {target_branch} does not exist in {repo}")
                    continue
                
                # Check for new commits
                has_commits, commit_count = self.gitlab.validate_commits(repo, source_branch, target_branch)
                if not has_commits:
                    logger.info(f"No new commits in {repo} from {source_branch} to {target_branch}")
                    continue
                
                valid_repos.append(repo)
                logger.info(f"Repository {repo} is valid for deployment ({commit_count} commits)")
                
            except Exception as e:
                logger.error(f"Failed to validate repository {repo}: {e}")
                continue
        
        return valid_repos
    
    def create_merge_requests_for_phase(self, repos: List[str], phase: DeploymentPhase) -> List[MRStatus]:
        phase_mrs = []
        
        for repo in repos:
            try:
                # Get source branch for this repo from strategy
                source_branch = self.get_repository_source_branch(repo)
                _, flow = self.get_repository_strategy(repo)
                source_index = flow.index(source_branch)
                target_branch = flow[source_index + 1]
                
                # Validate commits one more time
                has_commits, commit_count = self.gitlab.validate_commits(repo, source_branch, target_branch)
                
                mr_status = MRStatus(
                    repo_name=repo,
                    source_branch=source_branch,
                    target_branch=target_branch,
                    commit_count=commit_count
                )
                
                if not has_commits:
                    mr_status.state = "no_commits"
                    mr_status.error = "No new commits to merge"
                    phase_mrs.append(mr_status)
                    continue
                
                # Create MR
                mr_result = self.gitlab.create_merge_request(
                    repo, source_branch, target_branch, f"{phase.value}_deployment",
                    auto_merge=self.config['automation']['auto_merge']
                )
                
                if mr_result:
                    mr_status.mr_id = mr_result['id']
                    mr_status.mr_url = mr_result['web_url']
                    mr_status.state = "created"
                    logger.info(f"Created MR for {repo}: {mr_result['web_url']}")
                else:
                    mr_status.state = "failed"
                    mr_status.error = "Failed to create MR"
                
                phase_mrs.append(mr_status)
                
            except Exception as e:
                logger.error(f"Failed to create MR for {repo}: {e}")
                try:
                    source_branch = self.get_repository_source_branch(repo)
                    _, flow = self.get_repository_strategy(repo)
                    source_index = flow.index(source_branch)
                    target_branch = flow[source_index + 1]
                except:
                    source_branch = "unknown"
                    target_branch = "unknown"
                    
                mr_status = MRStatus(
                    repo_name=repo,
                    source_branch=source_branch,
                    target_branch=target_branch,
                    state="failed",
                    error=str(e)
                )
                phase_mrs.append(mr_status)
        
        return phase_mrs
    
    def monitor_merge_requests(self, mr_statuses: List[MRStatus]) -> List[MRStatus]:
        active_mrs = [mr for mr in mr_statuses if mr.state in ["created", "existing"] and mr.mr_id]
        
        if not active_mrs:
            return mr_statuses
        
        logger.info(f"Monitoring {len(active_mrs)} active merge requests...")
        
        # Monitor all MRs concurrently
        completed_mrs = []
        for mr_status in active_mrs:
            try:
                success, final_state = self.gitlab.monitor_merge_status(
                    mr_status.repo_name, 
                    mr_status.mr_id,
                    timeout=self.config['automation']['pipeline_timeout']
                )
                
                if success:
                    mr_status.state = "merged"
                    logger.info(f"MR merged successfully for {mr_status.repo_name}")
                else:
                    mr_status.state = "failed"
                    mr_status.error = f"Merge failed: {final_state}"
                    logger.error(f"MR failed for {mr_status.repo_name}: {final_state}")
                
                completed_mrs.append(mr_status)
                
            except Exception as e:
                logger.error(f"Error monitoring MR for {mr_status.repo_name}: {e}")
                mr_status.state = "failed"
                mr_status.error = str(e)
                completed_mrs.append(mr_status)
        
        return mr_statuses
    
    def wait_for_environment_deployment(self, repos: List[str], environment: str) -> bool:
        if environment not in self.config['environments']:
            logger.warning(f"Environment {environment} not configured for deployment monitoring")
            return True
        
        env_config = self.config['environments'][environment]
        if not env_config.get('wait_for_deployment', False):
            return True
        
        logger.info(f"Waiting for deployment to {environment} environment...")
        
        all_deployed = True
        for repo in repos:
            try:
                success = self.gitlab.wait_for_deployment(
                    repo, environment,
                    timeout=self.config['automation']['deployment_timeout']
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
    
    def create_next_phase_mrs(self, successful_repos: List[str]) -> List[MRStatus]:
        next_mrs = []
        
        for repo in successful_repos:
            try:
                _, flow = self.get_repository_strategy(repo)
                
                # Find current position and create MR for next step
                for i in range(len(flow) - 2):  # Skip last branch (no next step)
                    current_branch = flow[i + 1]  # Target from previous step becomes source
                    next_branch = flow[i + 2]
                    
                    # Check if we need to create this MR
                    has_commits, commit_count = self.gitlab.validate_commits(repo, current_branch, next_branch)
                    
                    if has_commits:
                        mr_result = self.gitlab.create_merge_request(
                            repo, current_branch, next_branch, "next_phase",
                            auto_merge=self.config['automation']['auto_merge']
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
    
    def get_deployment_progress(self, mr_statuses: List[MRStatus], phase: DeploymentPhase) -> DeploymentProgress:
        completed = [mr.repo_name for mr in mr_statuses if mr.state == "merged"]
        failed = [mr.repo_name for mr in mr_statuses if mr.state == "failed"]
        in_progress = [mr.repo_name for mr in mr_statuses if mr.state == "created"]
        pending = [mr.repo_name for mr in mr_statuses if mr.state == "pending"]
        
        # Determine environment based on target branches
        environment = "unknown"
        if mr_statuses:
            target_branch = mr_statuses[0].target_branch
            for env_name, env_config in self.config['environments'].items():
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
    
    def find_branches_with_new_commits(self, repos: List[str], after_merge_branch: str, 
                                     final_target_branch: str) -> Dict[str, List[Tuple[str, int]]]:
        """
        หาว่า branch ไหนมี new commits ระหว่าง merge และ final target branch สำหรับแต่ละ repo
        
        Args:
            repos: รายการ repositories ที่จะตรวจสอบ
            after_merge_branch: branch หลังจาก merge แล้ว (เช่น ss-dev, dev2)
            final_target_branch: final target branch (เช่น sit2)
        
        Returns:
            Dictionary mapping repo_name to list of (branch_name, commit_count)
        """
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
                                       final_target_branch: str, mr_title: str = "additional") -> List[MRStatus]:
        """
        สร้าง MRs สำหรับ branches ที่มี new commits ไป final target branch
        
        Args:
            repo_branches: Dictionary mapping repo to list of (branch_name, commit_count)
            final_target_branch: final target branch (เช่น sit2)
            mr_title: Title for the merge request
        
        Returns:
            List of MRStatus for created MRs
        """
        additional_mrs = []
        
        for repo, branches in repo_branches.items():
            for branch_name, commit_count in branches:
                try:
                    # Get commit details for better MR description
                    commit_details = self.gitlab.get_commit_details(repo, branch_name, final_target_branch)
                    
                    mr_status = MRStatus(
                        repo_name=repo,
                        source_branch=branch_name,
                        target_branch=final_target_branch,
                        commit_count=commit_count
                    )
                    
                    # Create MR with enhanced description
                    mr_result = self.gitlab.create_merge_request_with_commits(
                        repo, branch_name, final_target_branch, mr_title,
                        commit_details, auto_merge=self.config['automation']['auto_merge']
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
        """
        หา commits ใน intermediate branches ที่ไม่อยู่ใน final target branch
        
        Args:
            repos: รายการ repositories
            final_target_branch: final target branch
        
        Returns:
            Dictionary mapping repo_name to branch_commits
        """
        repo_intermediate_commits = {}
        
        for repo in repos:
            try:
                # Get branch flow for this repo
                _, flow = self.get_repository_strategy(repo)
                
                # Find intermediate commits
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
                                         final_target_branch: str, mr_title: str = "intermediate") -> List[MRStatus]:
        """
        สร้าง MRs สำหรับ intermediate branch commits
        
        Args:
            repo_intermediate_commits: Dictionary mapping repo to branch to (commit_count, commit_details)
            final_target_branch: final target branch
            mr_title: Title for the merge request
        
        Returns:
            List of MRStatus for created MRs
        """
        intermediate_mrs = []
        
        for repo, branch_commits in repo_intermediate_commits.items():
            try:
                # Get repository flow to check dependencies
                _, flow = self.get_repository_strategy(repo)
                
                for branch_name, (commit_count, commit_details) in branch_commits.items():
                    try:
                        # หา index ของ branch ปัจจุบันใน flow
                        current_branch_index = -1
                        try:
                            current_branch_index = flow.index(branch_name)
                        except ValueError:
                            # ถ้า branch ไม่อยู่ใน main flow สามารถ merge ได้เลย
                            logger.debug(f"{repo}: {branch_name} not in main flow, allowing direct merge")
                            current_branch_index = -1
                        
                        # ตรวจสอบ dependency ถ้า branch อยู่ใน main flow
                        if current_branch_index > 0:
                            has_pending_commits = self._check_pending_previous_commits(repo, flow, current_branch_index)
                            if has_pending_commits:
                                logger.info(f"Skipping intermediate MR for {repo}: {branch_name} → {final_target_branch} due to pending previous commits")
                                continue
                        
                        mr_status = MRStatus(
                            repo_name=repo,
                            source_branch=branch_name,
                            target_branch=final_target_branch,
                            commit_count=commit_count
                        )
                        
                        # Create enhanced MR for intermediate commits (or use existing)
                        mr_result = self.gitlab.create_merge_request_with_commits(
                            repo, branch_name, final_target_branch, mr_title,
                            commit_details, auto_merge=self.config['automation']['auto_merge']
                        )
                        
                        if mr_result:
                            mr_status.mr_id = mr_result['id']
                            mr_status.mr_url = mr_result['web_url']
                            mr_status.state = "existing" if mr_result.get('existing') else "created"
                            
                            if mr_result.get('existing'):
                                logger.info(f"Found existing MR for {repo}: {branch_name} → {final_target_branch} (MR #{mr_result['id']})")
                            else:
                                logger.info(f"Created intermediate MR for {repo}: {branch_name} → {final_target_branch}")
                        else:
                            mr_status.state = "failed"
                            mr_status.error = "Failed to create intermediate MR"
                        
                        intermediate_mrs.append(mr_status)
                    
                    except Exception as e:
                        logger.error(f"Failed to create intermediate MR for {repo}:{branch_name}: {e}")
                        mr_status = MRStatus(
                            repo_name=repo,
                            source_branch=branch_name,
                            target_branch=final_target_branch,
                            state="failed",
                            error=str(e),
                            commit_count=commit_count
                        )
                        intermediate_mrs.append(mr_status)
                        
            except Exception as e:
                logger.error(f"Failed to process intermediate commits for {repo}: {e}")
                continue
        
        return intermediate_mrs
    
    def process_additional_commits(self, repos: List[str], current_target_branch: str, 
                                 final_target_branch: str, mr_title: str = "additional") -> List[MRStatus]:
        """
        ประมวลผล additional commits จาก branches อื่นๆ และ intermediate branches ที่อาจมี commits ใหม่
        สำหรับทั้ง libraries และ services
        
        Args:
            repos: รายการ repositories ที่สำเร็จแล้ว
            current_target_branch: branch ปัจจุบันที่ merge เสร็จแล้ว
            final_target_branch: final target branch
            mr_title: Title for the merge request
        
        Returns:
            List of MRStatus for additional MRs created
        """
        logger.info(f"Processing additional commits for {len(repos)} repositories")
        
        # Determine repository type for logging
        libraries = [repo for repo in repos if repo in self.config['repositories']['libraries']]
        services = [repo for repo in repos if repo in self.config['repositories']['services']]
        
        if libraries:
            logger.info(f"Processing intermediate commits for {len(libraries)} libraries: {', '.join(libraries)}")
        if services:
            logger.info(f"Processing intermediate commits for {len(services)} services: {', '.join(services)}")
        
        all_additional_mrs = []
        
        # 1. หา branches ที่มี new commits (original functionality) - ทำงานกับทั้ง libraries และ services
        repo_branches = self.find_branches_with_new_commits(repos, current_target_branch, final_target_branch)
        
        if repo_branches:
            total_branches = sum(len(branches) for branches in repo_branches.values())
            logger.info(f"Found {total_branches} additional branches with new commits across {len(repo_branches)} repositories")
            
            additional_mrs = self.create_additional_merge_requests(repo_branches, final_target_branch, mr_title)
            all_additional_mrs.extend(additional_mrs)
        
        # 2. หา commits ใน intermediate branches (new functionality)
        repo_intermediate_commits = self.find_intermediate_branch_commits(repos, final_target_branch)
        
        if repo_intermediate_commits:
            total_intermediate_commits = sum(
                sum(count for count, _ in branch_commits.values()) 
                for branch_commits in repo_intermediate_commits.values()
            )
            logger.info(f"Found {total_intermediate_commits} intermediate branch commits across {len(repo_intermediate_commits)} repositories")
            
            intermediate_mrs = self.create_intermediate_merge_requests(repo_intermediate_commits, final_target_branch, mr_title)
            all_additional_mrs.extend(intermediate_mrs)
        
        # 3. ตรวจสอบและสร้าง MR ต่อเนื่องสำหรับ branches ที่ merge แล้ว (new functionality)
        progressive_mrs = self.create_progressive_merge_requests(repos, mr_title)
        if progressive_mrs:
            logger.info(f"Created {len(progressive_mrs)} progressive merge requests")
            all_additional_mrs.extend(progressive_mrs)
        
        if not all_additional_mrs:
            logger.info("No additional commits found in any branches")
            return []
        
        logger.info(f"Created {len(all_additional_mrs)} total additional merge requests")
        return all_additional_mrs
    
    def create_progressive_merge_requests(self, repos: List[str], mr_title: str = "progressive") -> List[MRStatus]:
        """
        ตรวจสอบและสร้าง MR ต่อเนื่องสำหรับ branches ที่ merge เสร็จแล้ว
        เช่น ถ้า source branch -> intermediate branch merge แล้ว ให้สร้าง MR intermediate -> target โดยอัตโนมัติ
        แก้ไขให้ไม่หยุดเมื่อเจอ ss-dev แต่จะทำต่อไปจนถึงปลาย branch
        
        Args:
            repos: รายการ repositories ที่จะตรวจสอบ
            mr_title: Title for the merge request
        
        Returns:
            List of MRStatus for progressive MRs created
        """
        progressive_mrs = []
        
        for repo in repos:
            try:
                # หา strategy และ flow สำหรับ repo นี้
                _, flow = self.get_repository_strategy(repo)
                
                logger.debug(f"Checking progressive opportunities for {repo} with flow: {flow}")
                
                # ตรวจสอบแต่ละ step ใน flow โดยไม่หยุดที่ ss-dev
                for i in range(len(flow) - 1):
                    source_branch = flow[i]
                    target_branch = flow[i + 1]
                    
                    # ตรวจสอบว่า source branch ได้ merge เข้า target แล้วหรือไม่
                    if not self._is_branch_merged_to_target(repo, source_branch, target_branch):
                        continue
                    
                    # หา target branch มี next branch หรือไม่
                    if i + 1 >= len(flow) - 1:  # target เป็น branch สุดท้ายแล้ว
                        continue
                    
                    next_branch = flow[i + 2]
                    
                    # ตรวจสอบว่ามี commits ใหม่ใน target -> next
                    has_commits, commit_count = self.gitlab.validate_commits(repo, target_branch, next_branch)
                    
                    if has_commits:
                        logger.info(f"Found progressive opportunity: {repo} {target_branch} -> {next_branch} ({commit_count} commits)")
                        
                        # ตรวจสอบว่ามี MR อยู่แล้วหรือไม่
                        existing_mrs = self._check_existing_mr(repo, target_branch, next_branch)
                        if existing_mrs:
                            logger.info(f"MR already exists for {repo}: {target_branch} -> {next_branch}")
                            continue
                        
                        # สร้าง MR ใหม่
                        mr_result = self.gitlab.create_merge_request(
                            repo, target_branch, next_branch, mr_title,
                            auto_merge=self.config['automation']['auto_merge']
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
                            logger.info(f"✅ Created progressive MR for {repo}: {target_branch} -> {next_branch}")
                        else:
                            mr_status.state = "failed"
                            mr_status.error = "Failed to create progressive MR"
                            logger.error(f"❌ Failed to create progressive MR for {repo}: {target_branch} -> {next_branch}")
                        
                        progressive_mrs.append(mr_status)
                        # ลบ break ออกเพื่อให้ทำต่อไปจนถึงปลาย branch
                        
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
            for env_name, env_config in self.config.get('environments', {}).items():
                triggered_by = env_config.get('triggered_by', [])
                wait_for_deployment = env_config.get('wait_for_deployment', False)
                
                if target_branch in triggered_by and wait_for_deployment:
                    logger.debug(f"Target branch {target_branch} triggers {env_name} with wait_for_deployment=true")
                    return True
            
            return False
        except Exception as e:
            logger.debug(f"Error checking deploy branch stop condition for {target_branch}: {e}")
            return False
    
    def create_complete_flow_merge_requests(self, repos: List[str], mr_title: str = "complete_flow") -> List[MRStatus]:
        """
        สร้าง MR ทั้งหมดตาม flow ที่กำหนดไว้ไปจนถึงปลาย branch โดยไม่หยุดที่ ss-dev
        เหมาะสำหรับกรณีที่ต้องการสร้าง MR ทั้งหมดในครั้งเดียว
        
        Args:
            repos: รายการ repositories ที่จะสร้าง MR
            mr_title: Title for the merge request
        
        Returns:
            List of MRStatus for all MRs created
        """
        complete_flow_mrs = []
        
        for repo in repos:
            try:
                # หา strategy และ flow สำหรับ repo นี้
                _, flow = self.get_repository_strategy(repo)
                
                logger.info(f"Creating complete flow MRs for {repo} with flow: {flow}")
                
                # สร้าง MR สำหรับทุก step ใน flow ที่มี commits
                for i in range(len(flow) - 1):
                    source_branch = flow[i]
                    target_branch = flow[i + 1]
                    
                    # ตรวจสอบว่า target branch นี้ trigger environment ที่มี wait_for_deployment = true หรือไม่
                    should_stop_at_target = self._should_stop_at_deploy_branch(target_branch)
                    
                    # ตรวจสอบว่า branches มีอยู่จริง
                    if not self.gitlab.branch_exists(repo, source_branch):
                        logger.warning(f"Source branch {source_branch} does not exist in {repo}")
                        continue
                    
                    if not self.gitlab.branch_exists(repo, target_branch):
                        logger.warning(f"Target branch {target_branch} does not exist in {repo}")
                        continue
                    
                    # ตรวจสอบว่ามี commits ใหม่
                    has_commits, commit_count = self.gitlab.validate_commits(repo, source_branch, target_branch)
                    
                    if has_commits:
                        # ตรวจสอบว่ามี MR อยู่แล้วหรือไม่
                        existing_mrs = self._check_existing_mr(repo, source_branch, target_branch)
                        if existing_mrs:
                            logger.info(f"MR already exists for {repo}: {source_branch} -> {target_branch}")
                            # ถ้าต้องหยุดที่ target branch นี้ ให้ break ออกจาก loop
                            if should_stop_at_target:
                                logger.info(f"Stopping at deploy branch {target_branch} due to wait_for_deployment=true")
                                break
                            continue
                        
                        # สร้าง MR ใหม่
                        mr_result = self.gitlab.create_merge_request(
                            repo, source_branch, target_branch, mr_title,
                            auto_merge=self.config['automation']['auto_merge']
                        )
                        
                        mr_status = MRStatus(
                            repo_name=repo,
                            source_branch=source_branch,
                            target_branch=target_branch,
                            commit_count=commit_count
                        )
                        
                        if mr_result:
                            mr_status.mr_id = mr_result['id']
                            mr_status.mr_url = mr_result['web_url']
                            mr_status.state = "created"
                            logger.info(f"✅ Created complete flow MR for {repo}: {source_branch} -> {target_branch} ({commit_count} commits)")
                        else:
                            mr_status.state = "failed"
                            mr_status.error = "Failed to create complete flow MR"
                            logger.error(f"❌ Failed to create complete flow MR for {repo}: {source_branch} -> {target_branch}")
                        
                        complete_flow_mrs.append(mr_status)
                        
                        # ถ้าต้องหยุดที่ target branch นี้ ให้ break ออกจาก loop
                        if should_stop_at_target:
                            logger.info(f"Stopping at deploy branch {target_branch} due to wait_for_deployment=true")
                            break
                    else:
                        logger.debug(f"No commits to merge for {repo}: {source_branch} -> {target_branch}")
                        # แม้ไม่มี commits ก็ยังต้องตรวจสอบว่าต้องหยุดที่ target branch นี้หรือไม่
                        if should_stop_at_target:
                            logger.info(f"Stopping at deploy branch {target_branch} due to wait_for_deployment=true")
                            break
                        
            except Exception as e:
                logger.error(f"Error creating complete flow MRs for {repo}: {e}")
                continue
        
        return complete_flow_mrs
    
    def _is_branch_merged_to_target(self, repo_name: str, source_branch: str, target_branch: str) -> bool:
        """
        ตรวจสอบว่า source branch ได้ merge เข้า target branch แล้วหรือไม่
        (โดยดูจากว่าไม่มี commits ใหม่ใน source ที่ไม่อยู่ใน target)
        
        Args:
            repo_name: ชื่อ repository
            source_branch: source branch
            target_branch: target branch
        
        Returns:
            True ถ้า source ได้ merge เข้า target แล้ว
        """
        try:
            # ตรวจสอบว่าทั้งสอง branch มีอยู่จริงหรือไม่
            if not self.gitlab.branch_exists(repo_name, source_branch):
                logger.debug(f"Source branch {source_branch} does not exist in {repo_name}")
                return False
            
            if not self.gitlab.branch_exists(repo_name, target_branch):
                logger.debug(f"Target branch {target_branch} does not exist in {repo_name}")
                return False
            
            # ตรวจสอบ commits - ถ้าไม่มี commits ใหม่ แสดงว่า merge แล้ว
            has_commits, commit_count = self.gitlab.validate_commits(repo_name, source_branch, target_branch)
            
            if has_commits:
                logger.debug(f"{repo_name}: {source_branch} has {commit_count} unmerged commits to {target_branch}")
                return False
            else:
                logger.debug(f"{repo_name}: {source_branch} is fully merged to {target_branch}")
                return True
                
        except Exception as e:
            logger.debug(f"Error checking merge status for {repo_name} {source_branch} -> {target_branch}: {e}")
            return False
    
    def _check_existing_mr(self, repo_name: str, source_branch: str, target_branch: str) -> bool:
        """
        ตรวจสอบว่ามี MR ที่เปิดอยู่สำหรับ branch pair นี้หรือไม่
        
        Args:
            repo_name: ชื่อ repository
            source_branch: source branch
            target_branch: target branch
        
        Returns:
            True ถ้ามี MR อยู่แล้ว
        """
        try:
            project = self.gitlab.get_project(repo_name)
            
            # หา MR ที่เปิดอยู่
            existing_mrs = project.mergerequests.list(
                source_branch=source_branch,
                target_branch=target_branch,
                state='opened'
            )
            
            return len(existing_mrs) > 0
            
        except Exception as e:
            logger.debug(f"Error checking existing MR for {repo_name} {source_branch} -> {target_branch}: {e}")
            return False
    
    def _check_pending_previous_commits(self, repo_name: str, flow: List[str], current_index: int) -> bool:
        """
        ตรวจสอบว่ามี branches ก่อนหน้า current_index ที่ยังมี commits ค้างอยู่หรือไม่
        
        Args:
            repo_name: ชื่อ repository
            flow: branch flow sequence
            current_index: index ปัจจุบันใน flow ที่ต้องการตรวจสอบ
        
        Returns:
            True ถ้ามี previous branches ที่มี commits ค้างอยู่
        """
        try:
            # ตรวจสอบ branches ทั้งหมดก่อนหน้า current_index
            for prev_i in range(current_index):
                prev_source = flow[prev_i]
                prev_target = flow[prev_i + 1]
                
                # ตรวจสอบว่า branch มีอยู่จริงหรือไม่
                if (not self.gitlab.branch_exists(repo_name, prev_source) or 
                    not self.gitlab.branch_exists(repo_name, prev_target)):
                    continue
                
                # ตรวจสอบว่ายังมี commits ค้างอยู่หรือไม่
                has_commits, commit_count = self.gitlab.validate_commits(repo_name, prev_source, prev_target)
                if has_commits:
                    logger.debug(f"{repo_name}: Found {commit_count} pending commits in {prev_source} -> {prev_target}")
                    return True
            
            return False
            
        except Exception as e:
            logger.debug(f"Error checking pending commits for {repo_name}: {e}")
            return False  # ในกรณี error ให้ดำเนินการต่อได้