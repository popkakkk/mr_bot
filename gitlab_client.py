import logging
import time
from typing import Dict, List, Optional, Tuple
import gitlab
import requests
from gitlab.exceptions import GitlabGetError, GitlabCreateError

logger = logging.getLogger(__name__)

class GitLabClient:
    def __init__(self, base_url: str, token: str, group_name: str, discord_notifier=None):
        self.gl = gitlab.Gitlab(base_url, private_token=token)
        self.group_name = group_name
        self.group = self._get_group()
        self.current_user = self._get_current_user()
        self.discord_notifier = discord_notifier
        
    def _get_group(self):
        try:
            return self.gl.groups.get(self.group_name)
        except GitlabGetError as e:
            logger.error(f"Failed to get group {self.group_name}: {e}")
            raise
    
    def _get_current_user(self):
        try:
            # Use the correct GitLab API method to get current user
            user = self.gl.users.get(id=self.gl.user.id, lazy=True)
            if user:
                logger.info(f"Authenticated as GitLab user: {user.username} ({user.name})")
                return user
            else:
                logger.warning("Could not retrieve current user information")
                return None
        except Exception as e:
            logger.debug(f"Failed to get current user: {e}")
            # Fallback: try to get user info directly
            try:
                current_user = self.gl.user
                if current_user and hasattr(current_user, 'id'):
                    logger.info(f"Authenticated as GitLab user ID: {current_user.id}")
                    return current_user
                else:
                    logger.warning("Current user information not available - assignee will be skipped")
                    return None
            except Exception as fallback_error:
                logger.warning(f"Failed to get current user info: {fallback_error} - assignee will be skipped")
                return None
    
    def get_project(self, repo_name: str):
        try:
            project_path = f"{self.group_name}/{repo_name}"
            return self.gl.projects.get(project_path)
        except GitlabGetError as e:
            logger.error(f"Failed to get project {repo_name}: {e}")
            raise
    
    def validate_commits(self, repo_name: str, source_branch: str, target_branch: str) -> Tuple[bool, int]:
        try:
            project = self.get_project(repo_name)
            
            # Get commits in source but not in target
            commits = project.repository_compare(from_=target_branch, to=source_branch)
            commit_count = len(commits.get('commits', []))
            
            has_new_commits = commit_count > 0
            logger.info(f"{repo_name}: {commit_count} new commits from {source_branch} to {target_branch}")
            
            return has_new_commits, commit_count
            
        except GitlabGetError as e:
            logger.error(f"Failed to validate commits for {repo_name}: {e}")
            return False, 0
    
    def branch_exists(self, repo_name: str, branch_name: str) -> bool:
        try:
            project = self.get_project(repo_name)
            project.branches.get(branch_name)
            return True
        except GitlabGetError:
            return False
    
    def check_pipeline_status(self, repo_name: str, branch_name: str) -> Optional[str]:
        try:
            project = self.get_project(repo_name)
            pipelines = project.pipelines.list(ref=branch_name, per_page=1)
            
            if not pipelines:
                logger.warning(f"No pipelines found for {repo_name}:{branch_name}")
                return None
                
            pipeline = pipelines[0]
            status = pipeline.status
            logger.info(f"Pipeline status for {repo_name}:{branch_name}: {status}")
            
            return status
            
        except GitlabGetError as e:
            logger.error(f"Failed to check pipeline status for {repo_name}: {e}")
            return None
    
    def create_merge_request(self, repo_name: str, source_branch: str, target_branch: str, 
                           sprint_name: str, auto_merge: bool = True) -> Optional[Dict]:
        try:
            project = self.get_project(repo_name)
            
            # Check if MR already exists
            existing_mrs = project.mergerequests.list(
                source_branch=source_branch,
                target_branch=target_branch,
                state='opened'
            )
            
            if existing_mrs:
                mr = existing_mrs[0]
                logger.info(f"MR already exists for {repo_name}: {source_branch} → {target_branch} (MR #{mr.iid})")
                
                # Set assignee for existing MR if not already assigned
                self._ensure_mr_assignee(project, mr.iid)
                
                # Check if existing MR needs auto-merge setup
                if auto_merge and mr.state == 'opened':
                    logger.info(f"Setting up auto-merge for existing MR #{mr.iid}")
                    self._enable_auto_merge(project, mr.iid)
                
                return {
                    'id': mr.iid,
                    'web_url': mr.web_url,
                    'title': mr.title,
                    'state': mr.state,
                    'existing': True  # Flag to indicate this was an existing MR
                }
            
            title = f"{source_branch} -> {target_branch}"
            description = f"""
**{source_branch} -> {target_branch}**

Auto-merge enabled - {sprint_name}
            """.strip()
            
            mr_data = {
                'source_branch': source_branch,
                'target_branch': target_branch,
                'title': title,
                'description': description,
                'remove_source_branch': False,
                'squash': False
            }
            
            # Add assignee if current user is available
            if self.current_user:
                mr_data['assignee_id'] = self.current_user.id
            
            mr = project.mergerequests.create(mr_data)
            logger.info(f"Created MR for {repo_name}: {source_branch} → {target_branch}")
            
            # Enable auto-merge if requested
            if auto_merge:
                self._enable_auto_merge(project, mr.iid)
            
            return {
                'id': mr.iid,
                'web_url': mr.web_url,
                'title': mr.title,
                'state': mr.state
            }
            
        except GitlabCreateError as e:
            logger.error(f"Failed to create MR for {repo_name}: {e}")
            return None
    
    def create_merge_request_with_commits(self, repo_name: str, source_branch: str, target_branch: str, 
                                        sprint_name: str, commit_details: List[Dict], 
                                        auto_merge: bool = True) -> Optional[Dict]:
        """
        สร้าง MR พร้อมกับรายละเอียด commits
        
        Args:
            repo_name: ชื่อ repository
            source_branch: source branch
            target_branch: target branch
            sprint_name: ชื่อ sprint
            commit_details: รายละเอียด commits
            auto_merge: เปิด auto-merge หรือไม่
        
        Returns:
            MR information dictionary or None if failed
        """
        try:
            project = self.get_project(repo_name)
            
            # Check if MR already exists
            existing_mrs = project.mergerequests.list(
                source_branch=source_branch,
                target_branch=target_branch,
                state='opened'
            )
            
            if existing_mrs:
                mr = existing_mrs[0]
                logger.info(f"MR already exists for {repo_name}: {source_branch} → {target_branch} (MR #{mr.iid})")
                
                # Set assignee for existing MR if not already assigned
                self._ensure_mr_assignee(project, mr.iid)
                
                # Check if existing MR needs auto-merge setup
                if auto_merge and mr.state == 'opened':
                    logger.info(f"Setting up auto-merge for existing MR #{mr.iid}")
                    self._enable_auto_merge(project, mr.iid)
                
                return {
                    'id': mr.iid,
                    'web_url': mr.web_url,
                    'title': mr.title,
                    'state': mr.state,
                    'existing': True  # Flag to indicate this was an existing MR
                }
            
            title = f"{source_branch} -> {target_branch}"
            
            description = f"""
**{source_branch} -> {target_branch}**

{len(commit_details)} commits - Auto-merge enabled - {sprint_name}
            """.strip()
            
            mr_data = {
                'source_branch': source_branch,
                'target_branch': target_branch,
                'title': title,
                'description': description,
                'remove_source_branch': False,
                'squash': False
            }
            
            # Add assignee if current user is available
            if self.current_user:
                mr_data['assignee_id'] = self.current_user.id
            
            mr = project.mergerequests.create(mr_data)
            logger.info(f"Created enhanced MR for {repo_name}: {source_branch} → {target_branch}")
            
            # Enable auto-merge if requested
            if auto_merge:
                self._enable_auto_merge(project, mr.iid)
            
            return {
                'id': mr.iid,
                'web_url': mr.web_url,
                'title': mr.title,
                'state': mr.state
            }
            
        except GitlabCreateError as e:
            logger.error(f"Failed to create enhanced MR for {repo_name}: {e}")
            return None
    
    def _enable_auto_merge(self, project, mr_iid: int):
        try:
            mr = project.mergerequests.get(mr_iid)
            
            # First, check if MR can be merged at all
            logger.info(f"Checking MR {mr_iid} merge status: {mr.merge_status}, state: {mr.state}")
            
            # Refresh MR data to get latest merge status
            mr = project.mergerequests.get(mr_iid, lazy=False)
            
            if mr.state == 'merged':
                logger.info(f"MR {mr_iid} is already merged")
                return True
            
            if mr.state != 'opened':
                logger.warning(f"MR {mr_iid} is not open (state: {mr.state})")
                return False
            
            # Check merge status
            if mr.merge_status == 'cannot_be_merged':
                logger.warning(f"⚠️  MR {mr_iid} has merge conflicts - cannot auto-merge")
                return False
            elif mr.merge_status == 'checking':
                logger.info(f"ℹ️  MR {mr_iid} merge status is still being checked - will retry")
                # Wait a bit for GitLab to finish checking
                import time
                time.sleep(5)
                mr = project.mergerequests.get(mr_iid, lazy=False)
            
            # Check current pipeline status
            pipeline_status = self.check_pipeline_status(project.name.split('/')[-1], mr.source_branch)
            
            if pipeline_status == 'success':
                # Pipeline already passed, try direct merge
                try:
                    merge_result = mr.merge(
                        should_remove_source_branch=False
                    )
                    logger.info(f"Direct merged MR {mr_iid} - pipeline already succeeded")
                    return True
                except Exception as direct_merge_error:
                    logger.debug(f"Direct merge failed for MR {mr_iid}: {direct_merge_error}")
                    # Fall through to set auto-merge flag
            elif pipeline_status is None:
                # No pipeline exists, try direct merge
                try:
                    merge_result = mr.merge(
                        should_remove_source_branch=False
                    )
                    logger.info(f"Direct merged MR {mr_iid} - no pipeline required")
                    return True
                except Exception as direct_merge_error:
                    logger.debug(f"Direct merge failed for MR {mr_iid}: {direct_merge_error}")
                    # Fall through to set auto-merge flag
            
            # Use the correct GitLab API endpoint for merge when pipeline succeeds
            # This requires calling the merge endpoint with the merge_when_pipeline_succeeds flag
            try:
                # Get the base GitLab URL without /api/v4
                gitlab_base_url = self.gl._url.rstrip('/').replace('/api/v4', '')
                headers = {'PRIVATE-TOKEN': self.gl.private_token}
                project_id = project.id
                
                # Use the merge endpoint with merge_when_pipeline_succeeds=true
                merge_url = f"{gitlab_base_url}/api/v4/projects/{project_id}/merge_requests/{mr_iid}/merge"
                
                merge_data = {
                    'merge_when_pipeline_succeeds': True,
                    'should_remove_source_branch': False
                }
                
                logger.debug(f"Calling GitLab merge API for MR {mr_iid} with data: {merge_data}")
                response = requests.put(merge_url, headers=headers, json=merge_data)
                
                logger.debug(f"GitLab API response for MR {mr_iid}: {response.status_code}")
                
                if response.status_code in [200, 202]:
                    try:
                        result = response.json()
                        logger.debug(f"Merge response data for MR {mr_iid}: {result}")
                        
                        if result.get('merge_when_pipeline_succeeds'):
                            logger.info(f"✅ Successfully enabled auto-merge for MR {mr_iid} - will merge when pipeline succeeds")
                            return True
                        elif result.get('state') == 'merged':
                            logger.info(f"✅ MR {mr_iid} merged immediately")
                            return True
                        else:
                            logger.info(f"✅ MR {mr_iid} auto-merge configured (state: {result.get('state', 'unknown')})")
                            return True
                    except Exception as json_error:
                        logger.info(f"✅ Auto-merge request accepted for MR {mr_iid} (response parsing failed: {json_error})")
                        return True
                        
                elif response.status_code == 405:
                    # Method not allowed - try alternative approach
                    logger.warning(f"⚠️  MR {mr_iid} method not allowed (405) - trying alternative approach")
                    logger.debug(f"Response text: {response.text}")
                    # จะรีเทิร์น False เพื่อให้ enhanced method จัดการ
                    return False
                elif response.status_code == 406:
                    # Not acceptable - usually means merge conflicts or other issues
                    logger.warning(f"⚠️  MR {mr_iid} not acceptable (406) - checking detailed error")
                    try:
                        error_response = response.json()
                        logger.warning(f"Detailed error: {error_response.get('message', 'Unknown error')}")
                    except:
                        logger.debug(f"Response text: {response.text}")
                    # จะรีเทิร์น False เพื่อให้ enhanced method จัดการ
                    return False
                else:
                    logger.warning(f"❌ Failed to enable auto-merge for MR {mr_iid}: {response.status_code}")
                    logger.warning(f"API endpoint: {merge_url}")
                    logger.warning(f"Request data: {merge_data}")
                    try:
                        error_response = response.json()
                        logger.warning(f"Response JSON: {error_response}")
                    except:
                        logger.warning(f"Response text: {response.text}")
                    # จะรีเทิร์น False เพื่อให้ enhanced method จัดการ
                    return False
                
            except Exception as merge_error:
                logger.error(f"Failed to enable auto-merge for MR {mr_iid}: {merge_error}")
                
                # Final fallback - try using the python-gitlab library merge method
                try:
                    # This might work in some cases where direct API doesn't
                    mr.merge(
                        merge_when_pipeline_succeeds=True,
                        should_remove_source_branch=False
                    )
                    logger.info(f"Enabled auto-merge for MR {mr_iid} via python-gitlab library")
                    return True
                except Exception as lib_error:
                    logger.debug(f"Python-gitlab library method also failed: {lib_error}")
                    return False
            
        except Exception as e:
            logger.error(f"Failed to enable auto-merge for MR {mr_iid}: {e}")
            return False
    
    def _try_alternative_auto_merge(self, project, mr_iid: int):
        """
        ลองวิธีการอื่นในการเปิด auto-merge เมื่อวิธีแรกไม่ได้ผล
        """
        try:
            mr = project.mergerequests.get(mr_iid, lazy=False)
            
            # วิธีที่ 1: ใช้ python-gitlab library
            logger.info(f"Trying python-gitlab library method for MR {mr_iid}")
            try:
                mr.merge(
                    merge_when_pipeline_succeeds=True,
                    should_remove_source_branch=False
                )
                logger.info(f"✅ Successfully enabled auto-merge for MR {mr_iid} via python-gitlab library")
                return True
            except Exception as lib_error:
                logger.debug(f"Python-gitlab library method failed: {lib_error}")
            
            # วิธีที่ 2: ตรวจสอบและ retry หากมี pipeline running
            pipeline_status = self.check_pipeline_status(project.name.split('/')[-1], mr.source_branch)
            if pipeline_status in ['running', 'pending', 'created']:
                logger.info(f"Pipeline is {pipeline_status} for MR {mr_iid} - will monitor and retry")
                return self._monitor_and_enable_auto_merge(project, mr_iid)
            
            # วิธีที่ 3: ลองทำ direct merge หาก pipeline success
            if pipeline_status == 'success':
                logger.info(f"Pipeline succeeded for MR {mr_iid} - attempting direct merge")
                try:
                    merge_result = mr.merge(should_remove_source_branch=False)
                    logger.info(f"✅ Successfully merged MR {mr_iid} directly")
                    return True
                except Exception as direct_merge_error:
                    logger.warning(f"Direct merge failed for MR {mr_iid}: {direct_merge_error}")
            
            # วิธีที่ 4: ใช้ raw API call แบบต่าง
            return self._try_raw_api_auto_merge(project, mr_iid)
            
        except Exception as e:
            logger.error(f"All alternative auto-merge methods failed for MR {mr_iid}: {e}")
            return False
    
    def _monitor_and_enable_auto_merge(self, project, mr_iid: int, max_retries: int = 3):
        """
        รอให้ pipeline เสร็จแล้วจึงลอง enable auto-merge
        """
        import time
        
        for retry in range(max_retries):
            try:
                mr = project.mergerequests.get(mr_iid, lazy=False)
                pipeline_status = self.check_pipeline_status(project.name.split('/')[-1], mr.source_branch)
                
                logger.info(f"Retry {retry + 1}/{max_retries}: Pipeline status for MR {mr_iid}: {pipeline_status}")
                
                if pipeline_status == 'success':
                    # Pipeline เสร็จแล้ว ลองทำ auto-merge
                    return self._try_raw_api_auto_merge(project, mr_iid)
                elif pipeline_status == 'failed':
                    logger.warning(f"Pipeline failed for MR {mr_iid} - cannot enable auto-merge")
                    return False
                elif pipeline_status in ['running', 'pending', 'created']:
                    # รอ pipeline ให้เสร็จ
                    wait_time = 30 * (retry + 1)  # รอนานขึ้นเรื่อยๆ
                    logger.info(f"Waiting {wait_time} seconds for pipeline to complete...")
                    time.sleep(wait_time)
                else:
                    logger.warning(f"Unknown pipeline status: {pipeline_status}")
                    break
                    
            except Exception as e:
                logger.error(f"Error in monitor retry {retry + 1}: {e}")
                break
        
        return False
    
    def _try_raw_api_auto_merge(self, project, mr_iid: int):
        """
        ลอง raw API call แบบต่างๆ
        """
        try:
            gitlab_url = self.gl._url
            headers = {
                'PRIVATE-TOKEN': self.gl.private_token,
                'Content-Type': 'application/json'
            }
            project_id = project.id
            
            # ลองใช้ merge endpoint แบบไม่มี merge_when_pipeline_succeeds ก่อน
            merge_url = f"{gitlab_url}/api/v4/projects/{project_id}/merge_requests/{mr_iid}/merge"
            
            merge_data = {
                'should_remove_source_branch': False,
                'squash': False
            }
            
            logger.info(f"Trying raw API merge for MR {mr_iid}")
            response = requests.put(merge_url, headers=headers, json=merge_data)
            
            if response.status_code in [200, 202]:
                logger.info(f"✅ Successfully merged MR {mr_iid} via raw API")
                return True
            else:
                logger.debug(f"Raw API merge failed with status {response.status_code}: {response.text}")
                return False
            
        except Exception as e:
            logger.error(f"Raw API auto-merge failed for MR {mr_iid}: {e}")
            return False
    
    def _enable_auto_merge_enhanced(self, project, mr_iid: int):
        """
        ปรับปรุงแล้วของวิธีการ enable auto-merge ที่มีประสิทธิภาพมากขึ้น
        รีเทิร์น True ถ้าสำเร็จ, False ถ้าล้มเหลว
        """
        try:
            logger.debug(f"Starting enhanced auto-merge process for MR {mr_iid}")
            
            # ตรวจสอบสถานะ MR ก่อน
            mr = project.mergerequests.get(mr_iid, lazy=False)
            logger.debug(f"MR {mr_iid} current state: {mr.state}, merge_status: {mr.merge_status}")
            
            # ลองวิธีเดิมก่อน
            result = self._enable_auto_merge(project, mr_iid)
            if result:
                logger.info(f"✅ Primary auto-merge succeeded for MR {mr_iid}")
                return True
                
            # ถ้าวิธีเดิมไม่ได้ผล ลองวิธีอื่น
            logger.info(f"Primary auto-merge failed for MR {mr_iid}, trying alternative methods")
            alt_result = self._try_alternative_auto_merge(project, mr_iid)
            
            if alt_result:
                logger.info(f"✅ Alternative auto-merge succeeded for MR {mr_iid}")
            else:
                logger.warning(f"❌ All auto-merge methods failed for MR {mr_iid}")
                # เพิ่มข้อมูลสำหรับ debugging
                self._log_mr_blocking_reasons(project, mr_iid)
            
            return alt_result
            
        except Exception as e:
            logger.error(f"Enhanced auto-merge failed for MR {mr_iid}: {e}")
            return False
    
    def _log_mr_blocking_reasons(self, project, mr_iid: int):
        """
        ล็อกสาเหตุที่ MR ไม่สามารถ auto-merge ได้
        """
        try:
            mr = project.mergerequests.get(mr_iid, lazy=False)
            repo_name = project.name.split('/')[-1]
            
            logger.info(f"\nการวิเคราะห์สาเหตุที่ MR {mr_iid} ไม่สามารถ auto-merge ได้:")
            logger.info(f"  - MR State: {mr.state}")
            logger.info(f"  - Merge Status: {mr.merge_status}")
            logger.info(f"  - Source Branch: {mr.source_branch}")
            logger.info(f"  - Target Branch: {mr.target_branch}")
            logger.info(f"  - Has Conflicts: {mr.has_conflicts if hasattr(mr, 'has_conflicts') else 'Unknown'}")
            logger.info(f"  - Work in Progress: {mr.work_in_progress if hasattr(mr, 'work_in_progress') else 'Unknown'}")
            
            # ตรวจสอบสถานะ pipeline
            pipeline_status = self.check_pipeline_status(repo_name, mr.source_branch)
            logger.info(f"  - Pipeline Status: {pipeline_status}")
            
            # ให้คำแนะนำแก้ไข
            if mr.merge_status == 'cannot_be_merged':
                logger.warning(f"  ➜ MR {mr_iid} มี merge conflicts - ต้องแก้ conflicts ก่อน")
            elif mr.state != 'opened':
                logger.warning(f"  ➜ MR {mr_iid} ไม่ได้เปิด - ตรวจสอบสถานะ MR")
            elif pipeline_status == 'failed':
                logger.warning(f"  ➜ Pipeline ล้มเหลว - ต้องแก้ pipeline ก่อน")
            elif pipeline_status in [None, 'manual']:
                logger.info(f"  ➜ ไม่มี pipeline หรือต้องกดมือ - ลอง merge ด้วยมือ")
            else:
                logger.info(f"  ➜ สามารถ merge ด้วยมือที่ GitLab UI")
            
        except Exception as e:
            logger.debug(f"Failed to log MR blocking reasons: {e}")
    
    def _ensure_mr_assignee(self, project, mr_iid: int):
        """Ensure MR has an assignee (current user)"""
        try:
            if not self.current_user:
                logger.debug(f"No current user available to assign MR {mr_iid}")
                return
                
            mr = project.mergerequests.get(mr_iid)
            
            # Check if MR already has an assignee
            if mr.assignee:
                logger.debug(f"MR {mr_iid} already has assignee: {mr.assignee['username']}")
                return
            
            # Assign current user
            mr.assignee_id = self.current_user.id
            mr.save()
            
            # Log with username if available, otherwise use ID
            user_info = getattr(self.current_user, 'username', f"ID:{self.current_user.id}")
            logger.info(f"Assigned MR {mr_iid} to current user: {user_info}")
            
        except Exception as e:
            logger.error(f"Failed to set assignee for MR {mr_iid}: {e}")
    
    def _check_mr_pipeline(self, project, mr_iid: int, source_branch: str) -> bool:
        """Check if MR has a pipeline or if one is expected"""
        try:
            # Get MR pipelines
            mr = project.mergerequests.get(mr_iid)
            pipelines = mr.pipelines()
            
            if pipelines:
                latest_pipeline = pipelines[0]
                logger.info(f"MR {mr_iid} has pipeline {latest_pipeline.id} with status: {latest_pipeline.status}")
                return latest_pipeline.status in ['pending', 'running', 'created']
            
            # Check branch pipelines
            branch_pipelines = project.pipelines.list(ref=source_branch, per_page=1)
            if branch_pipelines:
                latest_pipeline = branch_pipelines[0]
                logger.info(f"Branch {source_branch} has recent pipeline with status: {latest_pipeline.status}")
                return latest_pipeline.status in ['pending', 'running', 'created']
            
            logger.info(f"No active pipeline found for MR {mr_iid}")
            return False
            
        except Exception as e:
            logger.debug(f"Error checking pipeline for MR {mr_iid}: {e}")
            return False
    
    
    def monitor_merge_status(self, repo_name: str, mr_id: int, timeout: int = 1800) -> Tuple[bool, str]:
        try:
            project = self.get_project(repo_name)
            start_time = time.time()
            pipeline_success_notified = False  # Track if we've already sent notification
            auto_merge_waiting_notified = False  # Track if we've already sent auto-merge waiting notification
            
            while time.time() - start_time < timeout:
                mr = project.mergerequests.get(mr_id)
                state = mr.state
                
                if state == 'merged':
                    logger.info(f"MR {mr_id} for {repo_name} successfully merged")
                    return True, "merged"
                elif state == 'closed':
                    logger.warning(f"MR {mr_id} for {repo_name} was closed")
                    return False, "closed"
                elif state == 'opened':
                    # Check pipeline status
                    pipeline_status = self.check_pipeline_status(repo_name, mr.source_branch)
                    
                    if pipeline_status == 'failed':
                        logger.error(f"Pipeline failed for MR {mr_id} in {repo_name}")
                        return False, "pipeline_failed"
                    elif pipeline_status == 'success':
                        logger.info(f"Pipeline succeeded for MR {mr_id} in {repo_name}, waiting for auto-merge...")
                        
                        # Send Discord notification once for pipeline success
                        if not pipeline_success_notified and self.discord_notifier:
                            try:
                                self.discord_notifier.send_pipeline_success_notification(
                                    repo_name=repo_name,
                                    mr_id=mr_id,
                                    mr_url=mr.web_url
                                )
                                pipeline_success_notified = True
                                logger.info(f"Discord notification sent for pipeline success in {repo_name}")
                            except Exception as e:
                                logger.warning(f"Failed to send Discord notification for {repo_name}: {e}")
                        
                        # Pipeline succeeded, wait for GitLab to auto-merge
                        time.sleep(10)
                        continue
                    elif pipeline_status is None:
                        logger.info(f"No pipeline for MR {mr_id} in {repo_name}, attempting direct merge...")
                        
                        # No pipeline exists, try to merge directly
                        try:
                            merge_result = mr.merge(should_remove_source_branch=False)
                            logger.info(f"Direct merged MR {mr_id} for {repo_name} - no pipeline required")
                            return True, "merged"
                        except Exception as merge_error:
                            logger.warning(f"Direct merge failed for MR {mr_id} in {repo_name}: {merge_error}")
                            
                            # Send Discord notification once for auto-merge waiting as fallback
                            if not auto_merge_waiting_notified and self.discord_notifier:
                                try:
                                    self.discord_notifier.send_auto_merge_waiting_notification(
                                        repo_name=repo_name,
                                        mr_id=mr_id,
                                        mr_url=mr.web_url
                                    )
                                    auto_merge_waiting_notified = True
                                    logger.info(f"Discord notification sent for auto-merge waiting in {repo_name}")
                                except Exception as e:
                                    logger.warning(f"Failed to send Discord auto-merge waiting notification for {repo_name}: {e}")
                            
                            time.sleep(20)
                    else:
                        # Pipeline is running/pending
                        logger.info(f"MR {mr_id} for {repo_name} still open, pipeline: {pipeline_status}")
                        time.sleep(30)
                else:
                    logger.warning(f"Unknown MR state for {repo_name}: {state}")
                    time.sleep(30)
            
            logger.error(f"Timeout waiting for MR {mr_id} in {repo_name}")
            return False, "timeout"
            
        except GitlabGetError as e:
            logger.error(f"Failed to monitor MR {mr_id} for {repo_name}: {e}")
            return False, "error"
    
    def get_deployment_status(self, repo_name: str, environment: str) -> Optional[str]:
        try:
            project = self.get_project(repo_name)
            deployments = project.deployments.list(environment=environment, per_page=1)
            
            if not deployments:
                return None
                
            deployment = deployments[0]
            return deployment.status
            
        except GitlabGetError as e:
            logger.error(f"Failed to get deployment status for {repo_name}:{environment}: {e}")
            return None
    
    def wait_for_deployment(self, repo_name: str, environment: str, timeout: int = 3600) -> bool:
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            status = self.get_deployment_status(repo_name, environment)
            
            if status == 'success':
                logger.info(f"Deployment successful for {repo_name} in {environment}")
                return True
            elif status == 'failed':
                logger.error(f"Deployment failed for {repo_name} in {environment}")
                return False
            elif status in ['running', 'created']:
                logger.info(f"Deployment in progress for {repo_name} in {environment}: {status}")
                time.sleep(60)
            else:
                logger.info(f"Waiting for deployment to start for {repo_name} in {environment}")
                time.sleep(30)
        
        logger.error(f"Timeout waiting for deployment of {repo_name} in {environment}")
        return False
    
    def enable_auto_merge_for_ready_mrs(self, repo_name: str, mr_ids: List[int]) -> Dict[int, bool]:
        """Enable auto-merge for MRs that are ready"""
        results = {}
        
        try:
            project = self.get_project(repo_name)
            
            for mr_id in mr_ids:
                try:
                    mr = project.mergerequests.get(mr_id)
                    
                    if mr.state == 'merged':
                        results[mr_id] = True
                        logger.info(f"MR {mr_id} already merged")
                        continue
                    
                    if mr.state != 'opened':
                        results[mr_id] = False
                        logger.warning(f"MR {mr_id} is not open (state: {mr.state})")
                        continue
                    
                    # Check merge status first - refresh to get latest status
                    mr = project.mergerequests.get(mr_id, lazy=False)
                    
                    if mr.merge_status == 'cannot_be_merged':
                        results[mr_id] = False
                        logger.warning(f"MR {mr_id} has merge conflicts - cannot be merged")
                        continue
                    elif mr.merge_status == 'checking':
                        logger.info(f"MR {mr_id} merge status is still being checked - will proceed and retry if needed")
                        # ดำเนินการต่อเพื่อลองเปิด auto-merge
                    
                    # Set assignee if not already assigned
                    self._ensure_mr_assignee(project, mr_id)
                    
                    # Check pipeline status and enable appropriate auto-merge behavior
                    pipeline_status = self.check_pipeline_status(repo_name, mr.source_branch)
                    
                    if pipeline_status == 'success':
                        # Pipeline already passed, try direct merge
                        try:
                            merge_result = mr.merge(
                                should_remove_source_branch=False
                            )
                            results[mr_id] = True
                            logger.info(f"Direct merged MR {mr_id} - pipeline already succeeded")
                        except Exception as merge_error:
                            logger.debug(f"Direct merge failed for MR {mr_id}: {merge_error}")
                            # Fall back to auto-merge with improved method
                            success = self._enable_auto_merge_enhanced(project, mr_id)
                            results[mr_id] = success
                            if success:
                                logger.info(f"Enabled auto-merge for MR {mr_id}")
                            else:
                                logger.warning(f"Failed to enable auto-merge for MR {mr_id}")
                    elif pipeline_status in ['running', 'pending', 'created']:
                        # Pipeline is running, enable auto-merge with enhanced method
                        success = self._enable_auto_merge_enhanced(project, mr_id)
                        results[mr_id] = success
                        if success:
                            logger.info(f"Enabled auto-merge for MR {mr_id} - waiting for pipeline")
                        else:
                            logger.warning(f"Failed to enable auto-merge for MR {mr_id} while pipeline is running")
                    elif pipeline_status == 'failed':
                        results[mr_id] = False
                        logger.warning(f"MR {mr_id} pipeline failed - cannot auto-merge")
                    else:
                        # No pipeline or unknown status, try direct merge first
                        if pipeline_status is None:
                            logger.info(f"No pipeline detected for MR {mr_id} - attempting direct merge")
                            try:
                                merge_result = mr.merge(should_remove_source_branch=False)
                                results[mr_id] = True
                                logger.info(f"Direct merged MR {mr_id} - no pipeline required")
                                continue
                            except Exception as merge_error:
                                logger.debug(f"Direct merge failed for MR {mr_id}: {merge_error}")
                                # Fall through to enhanced auto-merge
                        
                        # Unknown status, try auto-merge anyway with enhanced method
                        success = self._enable_auto_merge_enhanced(project, mr_id)
                        results[mr_id] = success
                        if success:
                            logger.info(f"Enabled auto-merge for MR {mr_id} - no pipeline detected")
                        else:
                            logger.warning(f"Failed to enable auto-merge for MR {mr_id} with unknown pipeline status")
                
                except Exception as e:
                    results[mr_id] = False
                    logger.error(f"Failed to enable auto-merge for MR {mr_id}: {e}")
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to enable auto-merge for MRs in {repo_name}: {e}")
            return {mr_id: False for mr_id in mr_ids}
    
    def get_branches_with_new_commits(self, repo_name: str, after_merge_branch: str, 
                                    final_target_branch: str) -> List[Tuple[str, int]]:
        """
        หาว่า branch ไหนมี new commits ระหว่าง merge และ final target branch
        
        Args:
            repo_name: ชื่อ repository
            after_merge_branch: branch หลังจาก merge แล้ว (เช่น ss-dev, dev2)
            final_target_branch: final target branch (เช่น sit2)
        
        Returns:
            List of (branch_name, commit_count) tuples that have new commits
        """
        try:
            project = self.get_project(repo_name)
            branches_with_commits = []
            
            # Get all branches
            branches = project.branches.list(all=True)
            
            for branch in branches:
                branch_name = branch.name
                
                # Skip if this is the target branch itself
                if branch_name == final_target_branch:
                    continue
                
                # Check if this branch has commits that are not in final_target_branch
                # but might be newer than after_merge_branch
                try:
                    # Get commits in this branch but not in final target
                    commits_vs_final = project.repository_compare(from_=final_target_branch, to=branch_name)
                    final_commit_count = len(commits_vs_final.get('commits', []))
                    
                    if final_commit_count > 0:
                        # Also check commits vs after_merge_branch to see if they're new
                        commits_vs_merge = project.repository_compare(from_=after_merge_branch, to=branch_name)
                        merge_commit_count = len(commits_vs_merge.get('commits', []))
                        
                        if merge_commit_count > 0:
                            branches_with_commits.append((branch_name, final_commit_count))
                            logger.info(f"Branch {branch_name} has {final_commit_count} new commits not in {final_target_branch}")
                
                except GitlabGetError as e:
                    logger.debug(f"Could not compare {branch_name} with {final_target_branch}: {e}")
                    continue
            
            logger.info(f"Found {len(branches_with_commits)} branches with new commits in {repo_name}")
            return branches_with_commits
            
        except GitlabGetError as e:
            logger.error(f"Failed to get branches with new commits for {repo_name}: {e}")
            return []
    
    def get_commit_details(self, repo_name: str, source_branch: str, target_branch: str) -> List[Dict]:
        """
        ดึงรายละเอียด commits ที่แตกต่างระหว่าง source และ target branch
        
        Args:
            repo_name: ชื่อ repository
            source_branch: source branch
            target_branch: target branch
        
        Returns:
            List of commit details with id, message, author, created_at
        """
        try:
            project = self.get_project(repo_name)
            
            # Get commits in source but not in target
            comparison = project.repository_compare(from_=target_branch, to=source_branch)
            commits = comparison.get('commits', [])
            
            commit_details = []
            for commit in commits:
                commit_details.append({
                    'id': commit['id'][:8],
                    'short_id': commit['short_id'],
                    'message': commit['message'].split('\n')[0],  # First line only
                    'author_name': commit['author_name'],
                    'created_at': commit['created_at'],
                    'web_url': commit.get('web_url', '')
                })
            
            return commit_details
            
        except GitlabGetError as e:
            logger.error(f"Failed to get commit details for {repo_name}: {e}")
            return []
    
    def get_intermediate_branch_commits(self, repo_name: str, branch_flow: List[str], 
                                      final_target_branch: str) -> Dict[str, Tuple[int, List[Dict]]]:
        """
        หา commits ที่อยู่ใน intermediate branches แต่ไม่อยู่ใน final target branch
        สำหรับกรณีที่มี commits ใหม่ใน branch ระหว่างทาง (เช่น ss-dev) แต่ไม่มีใน source branch (เช่น ss/sprint4/all)
        
        Args:
            repo_name: ชื่อ repository
            branch_flow: ลำดับ branches ตาม strategy (เช่น ['ss/sprint4/all', 'ss-dev', 'dev2', 'sit2'])
            final_target_branch: final target branch (เช่น sit2)
        
        Returns:
            Dictionary mapping branch_name to (commit_count, commit_details)
        """
        try:
            project = self.get_project(repo_name)
            intermediate_commits = {}
            
            # ตรวจสอบแต่ละ branch ใน flow (ยกเว้น final target)
            for i, current_branch in enumerate(branch_flow):
                if current_branch == final_target_branch:
                    continue
                
                try:
                    # ตรวจสอบว่า branch มีอยู่จริงหรือไม่
                    if not self.branch_exists(repo_name, current_branch):
                        logger.debug(f"Branch {current_branch} does not exist in {repo_name}")
                        continue
                    
                    # หา commits ใน current_branch ที่ไม่อยู่ใน final_target_branch
                    comparison = project.repository_compare(from_=final_target_branch, to=current_branch)
                    commits = comparison.get('commits', [])
                    
                    if not commits:
                        continue
                    
                    # ตรวจสอบว่า commits เหล่านี้มาจาก branches ก่อนหน้าใน flow หรือไม่
                    unique_commits = []
                    for commit in commits:
                        is_from_previous_branch = False
                        
                        # ตรวจสอบกับ branches ก่อนหน้าใน flow
                        for j in range(i):
                            prev_branch = branch_flow[j]
                            if not self.branch_exists(repo_name, prev_branch):
                                continue
                                
                            try:
                                prev_comparison = project.repository_compare(from_=prev_branch, to=current_branch)
                                prev_commits = prev_comparison.get('commits', [])
                                
                                # ถ้า commit นี้อยู่ใน comparison จาก previous branch แสดงว่ามาจาก previous branch
                                if any(prev_commit['id'] == commit['id'] for prev_commit in prev_commits):
                                    is_from_previous_branch = True
                                    break
                            except GitlabGetError:
                                continue
                        
                        # ถ้า commit ไม่ได้มาจาก previous branches แสดงว่าเป็น commit ใหม่ใน intermediate branch
                        if not is_from_previous_branch:
                            unique_commits.append(commit)
                    
                    if unique_commits:
                        # สร้างรายละเอียด commits
                        commit_details = []
                        for commit in unique_commits:
                            commit_details.append({
                                'id': commit['id'][:8],
                                'short_id': commit['short_id'],
                                'message': commit['message'].split('\n')[0],
                                'author_name': commit['author_name'],
                                'created_at': commit['created_at'],
                                'web_url': commit.get('web_url', '')
                            })
                        
                        intermediate_commits[current_branch] = (len(unique_commits), commit_details)
                        logger.info(f"Found {len(unique_commits)} intermediate commits in {repo_name}:{current_branch}")
                
                except GitlabGetError as e:
                    logger.debug(f"Could not analyze branch {current_branch} in {repo_name}: {e}")
                    continue
            
            return intermediate_commits
            
        except GitlabGetError as e:
            logger.error(f"Failed to get intermediate branch commits for {repo_name}: {e}")
            return {}