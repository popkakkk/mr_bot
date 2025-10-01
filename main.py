#!/usr/bin/env python3

import os
import sys
import time
import logging
import yaml
import click
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from typing import List, Dict, Optional

from gitlab_client import GitLabClient
from discord_notifier import DiscordNotifier
from mr_automation import MRAutomation
from models import DeploymentPhase, MRStatus

# Load environment variables
load_dotenv()

console = Console()

def debug_branch_status(config: Dict):
    """Debug function to check branch status and commits"""
    console.print(Panel("🔍 Branch Debug Mode", style="bold cyan"))
    
    # Initialize GitLab client
    gitlab_config = config['gitlab']
    gitlab_client = GitLabClient(
        gitlab_config['base_url'],
        gitlab_config['api_token'],
        gitlab_config['project_group']
    )
    
    # Get all repositories
    all_repos = config['repositories']['libraries'] + config['repositories']['services']
    
    for repo in all_repos:
        try:
            console.print(f"\n[bold blue]🔍 Repository: {repo}[/bold blue]")
            
            # Get strategy and flow
            strategy_found = False
            flow = []
            for strategy_name, strategy_config in config['branch_strategies'].items():
                if repo in strategy_config['repos']:
                    flow = strategy_config['flow']
                    strategy_found = True
                    console.print(f"  Strategy: {strategy_name}")
                    console.print(f"  Flow: {' → '.join(flow)}")
                    break
            
            if not strategy_found:
                console.print("  [red]❌ No strategy found for this repository[/red]")
                continue
            
            # Check each branch in flow
            for i, branch in enumerate(flow):
                exists = gitlab_client.branch_exists(repo, branch)
                status = "✅ exists" if exists else "❌ missing"
                console.print(f"  Branch {branch}: {status}")
                
                if exists and i < len(flow) - 1:
                    next_branch = flow[i + 1]
                    if gitlab_client.branch_exists(repo, next_branch):
                        has_commits, count = gitlab_client.validate_commits(repo, branch, next_branch)
                        if has_commits:
                            console.print(f"    → {count} commits ahead of {next_branch}")
                        else:
                            console.print(f"    → no new commits vs {next_branch}")
            
            # Check for intermediate commits
            if len(flow) >= 2:
                console.print(f"  [yellow]Checking intermediate commits...[/yellow]")
                intermediate_commits = gitlab_client.get_intermediate_branch_commits(repo, flow, flow[-1])
                if intermediate_commits:
                    for branch, (count, details) in intermediate_commits.items():
                        console.print(f"    🔍 {branch}: {count} intermediate commits")
                        for detail in details[:3]:  # Show first 3 commits
                            console.print(f"      • {detail['short_id']}: {detail['message']}")
                        if len(details) > 3:
                            console.print(f"      ... and {len(details) - 3} more")
                else:
                    console.print(f"    ✅ No intermediate commits found")
                    
        except Exception as e:
            console.print(f"  [red]❌ Error checking {repo}: {e}[/red]")

def process_intermediate_commits_directly(config: Dict, dry_run: bool = False, repo_filter: str = None, progressive_enabled: bool = True):
    """Process intermediate commits directly without requiring source branch commits"""
    console.print(Panel("🔄 Processing Intermediate Commits", style="bold green"))
    
    if dry_run:
        console.print("[yellow]Running in DRY RUN mode - no changes will be made[/yellow]")
    
    # Initialize clients
    gitlab_config = config['gitlab']
    discord_webhook = config['discord']['webhook_url']
    discord_notifier = DiscordNotifier(discord_webhook, config)
    
    gitlab_client = GitLabClient(
        gitlab_config['base_url'],
        gitlab_config['api_token'],
        gitlab_config['project_group'],
        discord_notifier
    )
    
    automation = MRAutomation(gitlab_client, discord_notifier, config)
    
    # Get repositories based on filter
    if repo_filter == 'libraries':
        all_repos = config['repositories']['libraries']
        console.print("[yellow]Processing intermediate commits for LIBRARIES only[/yellow]")
    elif repo_filter == 'services':
        all_repos = config['repositories']['services']
        console.print("[yellow]Processing intermediate commits for SERVICES only[/yellow]")
    else:
        all_repos = config['repositories']['libraries'] + config['repositories']['services']
        console.print("[blue]Processing intermediate commits for ALL repositories[/blue]")
    
    if not dry_run:
        discord_notifier.send_deployment_start("intermediate", [], all_repos)
    
    all_mrs = []
    
    # Process each repository
    for repo in all_repos:
        try:
            console.print(f"\n[bold blue]🔍 Processing {repo}[/bold blue]")
            
            # Get strategy and flow
            _, flow = automation.get_repository_strategy(repo)
            
            # Process each step in flow looking for commits to merge forward
            # เพิ่มการตรวจสอบ dependency - ต้อง merge จาก branch แรกสุดก่อน
            for i in range(len(flow) - 1):
                source_branch = flow[i]
                target_branch = flow[i + 1]
                
                # Skip if source branch doesn't exist
                if not gitlab_client.branch_exists(repo, source_branch):
                    console.print(f"  Branch {source_branch}: ❌ missing")
                    continue
                
                # ตรวจสอบว่ามี branches ก่อนหน้าที่ยังมี commits ค้างอยู่หรือไม่
                has_pending_previous_commits = False
                if i > 0:  # ถ้าไม่ใช่ branch แรก
                    for prev_i in range(i):  # ตรวจสอบ branches ก่อนหน้า
                        prev_source = flow[prev_i]
                        prev_target = flow[prev_i + 1]
                        
                        if (gitlab_client.branch_exists(repo, prev_source) and 
                            gitlab_client.branch_exists(repo, prev_target)):
                            prev_has_commits, prev_count = gitlab_client.validate_commits(repo, prev_source, prev_target)
                            if prev_has_commits:
                                console.print(f"  ⚠️  Skipping {source_branch} → {target_branch}: Previous branch {prev_source} → {prev_target} has {prev_count} unmerged commits")
                                has_pending_previous_commits = True
                                break
                
                if has_pending_previous_commits:
                    continue
                
                # ตรวจสอบว่า target branch นี้ trigger environment ที่มี wait_for_deployment = true หรือไม่
                should_stop_at_target = False
                for env_name, env_config in config.get('environments', {}).items():
                    triggered_by = env_config.get('triggered_by', [])
                    wait_for_deployment = env_config.get('wait_for_deployment', False)
                    if target_branch in triggered_by and wait_for_deployment:
                        should_stop_at_target = True
                        break
                
                # Check for commits
                has_commits, commit_count = gitlab_client.validate_commits(repo, source_branch, target_branch)
                
                if has_commits:
                    console.print(f"  {source_branch} → {target_branch}: ✅ {commit_count} commits")
                    
                    if not dry_run:
                        # Get commit details
                        commit_details = gitlab_client.get_commit_details(repo, source_branch, target_branch)
                        
                        # Create MR (or use existing one)
                        mr_result = gitlab_client.create_merge_request_with_commits(
                            repo, source_branch, target_branch, "intermediate",
                            commit_details, auto_merge=config['automation']['auto_merge']
                        )
                        
                        if mr_result:
                            mr_status = MRStatus(
                                repo_name=repo,
                                source_branch=source_branch,
                                target_branch=target_branch,
                                mr_id=mr_result['id'],
                                mr_url=mr_result['web_url'],
                                state="created",
                                commit_count=commit_count
                            )
                            all_mrs.append(mr_status)
                            
                            if mr_result.get('existing'):
                                console.print(f"    📋 Found existing MR: {mr_result['web_url']} (will monitor & merge)")
                                mr_status.state = "existing"  # Mark as existing for table display
                            else:
                                console.print(f"    🚀 Created MR: {mr_result['web_url']}")
                        else:
                            console.print(f"    ❌ Failed to create MR")
                        
                        # หยุดสร้าง MR เพิ่มเติมสำหรับ repo นี้เมื่อเจอ branch ที่มี commits หรือถึง deploy branch
                        if should_stop_at_target:
                            console.print(f"    ⏸️  Stopping at deploy branch {target_branch} due to wait_for_deployment=true")
                        break
                    else:
                        console.print(f"    🚀 Would create MR: {source_branch} → {target_branch}")
                        if should_stop_at_target:
                            console.print(f"    ⏸️  Would stop at deploy branch {target_branch} due to wait_for_deployment=true")
                        break  # ใน dry run mode ก็ต้อง break เพื่อแสดงว่าจะทำ sequential
                else:
                    console.print(f"  {source_branch} → {target_branch}: ✅ up to date")
                    # แม้ไม่มี commits ก็ยังต้องตรวจสอบว่าต้องหยุดที่ target branch นี้หรือไม่
                    if should_stop_at_target:
                        console.print(f"    ⏸️  Stopping at deploy branch {target_branch} due to wait_for_deployment=true")
                        break
                    
        except Exception as e:
            console.print(f"  [red]❌ Error processing {repo}: {e}[/red]")
    
    # Display results
    if all_mrs:
        display_mr_status_table(all_mrs, "Intermediate Branch MRs Created")
        
        if not dry_run:
            # Monitor MRs
            console.print("[blue]Monitoring merge requests...[/blue]")
            monitored_mrs = automation.monitor_merge_requests(all_mrs)
            
            # Display final results
            display_mr_status_table(monitored_mrs, "Final MR Status")
            
            successful_mrs = [mr for mr in monitored_mrs if mr.state == "merged"]
            failed_mrs = [mr for mr in monitored_mrs if mr.state == "failed"]
            
            console.print(f"[green]✅ {len(successful_mrs)} MRs merged successfully[/green]")
            if failed_mrs:
                console.print(f"[red]❌ {len(failed_mrs)} MRs failed[/red]")
                console.print("[yellow]Failed MRs can often be merged manually at GitLab UI[/yellow]")
                for failed_mr in failed_mrs:
                    if failed_mr.mr_url:
                        console.print(f"  • {failed_mr.repo_name}: {failed_mr.mr_url}")
            
            # หลังจาก merge สำเร็จ ตรวจสอบและสร้าง MR ต่อเนื่อง
            if successful_mrs:
                console.print("\n[blue]สร้าง MR ต่อเนื่องไปจนถึงปลาย branch...[/blue]")
                successful_repos = list(set(mr.repo_name for mr in successful_mrs))
                
                # สร้าง MR ทั้งหมดตาม flow โดยไม่หยุดที่ ss-dev
                progressive_mrs = automation.create_complete_flow_merge_requests(successful_repos, "complete_flow")
                
                if progressive_mrs:
                    console.print(f"[green]✅ สร้าง MR ครบทั้ง flow เพิ่มอีก {len(progressive_mrs)} MR[/green]")
                    display_mr_status_table(progressive_mrs, "Complete Flow MRs Created")
                    
                    # Monitor progressive MRs
                    console.print("[blue]Monitoring progressive merge requests...[/blue]")
                    monitored_progressive_mrs = automation.monitor_merge_requests(progressive_mrs)
                    display_mr_status_table(monitored_progressive_mrs, "Progressive MRs - Final Status")
                    
                    # Add to final counts
                    progressive_successful = [mr for mr in monitored_progressive_mrs if mr.state == "merged"]
                    progressive_failed = [mr for mr in monitored_progressive_mrs if mr.state == "failed"]
                    
                    if progressive_successful:
                        console.print(f"[green]✅ Progressive MRs merged: {len(progressive_successful)}[/green]")
                    if progressive_failed:
                        console.print(f"[red]❌ Progressive MRs failed: {len(progressive_failed)}[/red]")
                        for failed_mr in progressive_failed:
                            if failed_mr.mr_url:
                                console.print(f"  • {failed_mr.repo_name}: {failed_mr.mr_url}")
                else:
                    console.print("[green]✓ ไม่มีโอกาสสำหรับ MR ต่อเนื่อง[/green]")
            elif successful_mrs and not progressive_enabled:
                console.print("[blue]ℹ️  Progressive MR creation disabled - skipping next branch MRs[/blue]")
            
            # Send final notification
            discord_notifier.send_additional_commits_update(
                "intermediate", len(all_mrs), 
                [mr.repo_name for mr in successful_mrs],
                [mr.repo_name for mr in failed_mrs],
                len(all_mrs)  # All are intermediate commits
            )
    else:
        console.print("[green]✅ All branches are up to date - no intermediate commits found[/green]")

def enable_auto_merge_mrs(config: Dict, force_merge_str: str):
    """Enable auto-merge for specified MRs"""
    console.print(Panel("🚀 Enabling Auto-Merge for MRs", style="bold green"))
    
    # Parse force merge string (format: repo:mr_id,repo:mr_id)
    mr_specs = []
    for spec in force_merge_str.split(','):
        if ':' in spec:
            repo, mr_id = spec.strip().split(':', 1)
            try:
                mr_specs.append((repo, int(mr_id)))
            except ValueError:
                console.print(f"[red]❌ Invalid MR ID: {spec}[/red]")
        else:
            console.print(f"[red]❌ Invalid format: {spec} (expected: repo:mr_id)[/red]")
    
    if not mr_specs:
        console.print("[red]❌ No valid MR specs found[/red]")
        return
    
    # Initialize GitLab client
    gitlab_config = config['gitlab']
    gitlab_client = GitLabClient(
        gitlab_config['base_url'],
        gitlab_config['api_token'],
        gitlab_config['project_group']
    )
    
    # Group by repository
    repo_mrs = {}
    for repo, mr_id in mr_specs:
        if repo not in repo_mrs:
            repo_mrs[repo] = []
        repo_mrs[repo].append(mr_id)
    
    # Force merge per repository
    total_success = 0
    total_failed = 0
    
    for repo, mr_ids in repo_mrs.items():
        console.print(f"\n[bold blue]🔍 Enabling auto-merge for MRs in {repo}[/bold blue]")
        results = gitlab_client.enable_auto_merge_for_ready_mrs(repo, mr_ids)
        
        for mr_id, success in results.items():
            if success:
                console.print(f"  MR {mr_id}: ✅ auto-merge enabled")
                total_success += 1
            else:
                console.print(f"  MR {mr_id}: ❌ failed to enable auto-merge")
                total_failed += 1
    
    console.print(f"\n[green]✅ {total_success} MRs configured for auto-merge[/green]")
    if total_failed > 0:
        console.print(f"[red]❌ {total_failed} MRs failed to configure auto-merge[/red]")

def directly_merge_mrs(config: Dict, merge_str: str):
    """Directly merge specified MRs"""
    console.print(Panel("🚀 Directly Merging MRs", style="bold green"))
    
    # Parse merge string (format: repo:mr_id,repo:mr_id)
    mr_specs = []
    for spec in merge_str.split(','):
        if ':' in spec:
            repo, mr_id = spec.strip().split(':', 1)
            try:
                mr_specs.append((repo, int(mr_id)))
            except ValueError:
                console.print(f"[red]❌ Invalid MR ID: {spec}[/red]")
        else:
            console.print(f"[red]❌ Invalid format: {spec} (expected: repo:mr_id)[/red]")
    
    if not mr_specs:
        console.print("[red]❌ No valid MR specs found[/red]")
        return
    
    # Initialize GitLab client
    gitlab_config = config['gitlab']
    gitlab_client = GitLabClient(
        gitlab_config['base_url'],
        gitlab_config['api_token'],
        gitlab_config['project_group']
    )
    
    # Group by repository
    repo_mrs = {}
    for repo, mr_id in mr_specs:
        if repo not in repo_mrs:
            repo_mrs[repo] = []
        repo_mrs[repo].append(mr_id)
    
    # Merge per repository
    total_success = 0
    total_failed = 0
    
    for repo, mr_ids in repo_mrs.items():
        console.print(f"\n[bold blue]🔍 Merging MRs in {repo}[/bold blue]")
        
        try:
            project = gitlab_client.get_project(repo)
            
            for mr_id in mr_ids:
                try:
                    mr = project.mergerequests.get(mr_id)
                    
                    # Check if MR is already merged
                    if mr.state == 'merged':
                        console.print(f"  MR {mr_id}: ⚠️  already merged")
                        continue
                    
                    # Check if MR can be merged
                    if mr.merge_status != 'can_be_merged':
                        console.print(f"  MR {mr_id}: ❌ cannot be merged (status: {mr.merge_status})")
                        total_failed += 1
                        continue
                    
                    # Perform direct merge
                    merge_result = mr.merge(should_remove_source_branch=False)
                    console.print(f"  MR {mr_id}: ✅ successfully merged")
                    total_success += 1
                    
                except Exception as e:
                    console.print(f"  MR {mr_id}: ❌ failed to merge ({str(e)})")
                    total_failed += 1
                    
        except Exception as e:
            console.print(f"[red]❌ Failed to access repository {repo}: {str(e)}[/red]")
            total_failed += len(mr_ids)
    
    console.print(f"\n[green]✅ {total_success} MRs merged successfully[/green]")
    if total_failed > 0:
        console.print(f"[red]❌ {total_failed} MRs failed to merge[/red]")

def setup_logging(log_level: str, log_file: str):
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )

def load_config(config_path: str) -> Dict:
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Replace environment variables
        def replace_env_vars(obj):
            if isinstance(obj, dict):
                return {k: replace_env_vars(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [replace_env_vars(item) for item in obj]
            elif isinstance(obj, str) and obj.startswith('${') and obj.endswith('}'):
                env_var = obj[2:-1]
                return os.getenv(env_var, obj)
            return obj
        
        return replace_env_vars(config)
    except Exception as e:
        console.print(f"[red]Error loading config: {e}[/red]")
        sys.exit(1)

def validate_environment():
    required_vars = ['GITLAB_TOKEN']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        console.print(f"[red]Missing required environment variables: {', '.join(missing_vars)}[/red]")
        console.print("Please set these variables in your environment or .env file")
        sys.exit(1)

def display_repository_summary(libraries: List[str], services: List[str]):
    table = Table(title="Repository Summary", show_header=True, header_style="bold blue")
    table.add_column("Phase", style="cyan", width=10)
    table.add_column("Repository", style="green")
    table.add_column("Type", style="yellow")
    
    for repo in libraries:
        table.add_row("Phase 1", repo, "Library")
    
    for repo in services:
        table.add_row("Phase 2", repo, "Service")
    
    console.print(table)

def display_mr_status_table(mr_statuses: List[MRStatus], title: str):
    table = Table(title=title, show_header=True, header_style="bold blue")
    table.add_column("Repository", style="cyan")
    table.add_column("Source → Target", style="green")
    table.add_column("Status", style="yellow")
    table.add_column("Commits", style="magenta", justify="center")
    table.add_column("MR Link", style="blue")
    
    for mr in mr_statuses:
        status_emoji = {
            "pending": "⏸️",
            "created": "⏳",
            "existing": "📋",
            "merged": "✅",
            "failed": "❌",
            "no_commits": "📭"
        }.get(mr.state, "❓")
        
        status_text = f"{status_emoji} {mr.state}"
        branch_text = f"{mr.source_branch} → {mr.target_branch}"
        commits_text = str(mr.commit_count) if mr.commit_count > 0 else "-"
        link_text = f"[link={mr.mr_url}]View MR[/link]" if mr.mr_url else "-"
        
        table.add_row(mr.repo_name, branch_text, status_text, commits_text, link_text)
    
    console.print(table)

class MRDeploymentOrchestrator:
    def __init__(self, config: Dict, dry_run: bool = False, check_additional_commits: bool = True):
        self.config = config
        self.dry_run = dry_run
        self.check_additional_commits = check_additional_commits
        self.start_time = time.time()
        
        # Initialize clients
        gitlab_config = config['gitlab']
        discord_webhook = config['discord']['webhook_url']
        self.discord_notifier = DiscordNotifier(discord_webhook, config)
        
        self.gitlab_client = GitLabClient(
            gitlab_config['base_url'],
            gitlab_config['api_token'],
            gitlab_config['project_group'],
            self.discord_notifier
        )
        
        self.automation = MRAutomation(self.gitlab_client, self.discord_notifier, config)
        
    def run_deployment(self, target_env: str = "all", 
                      libraries_only: bool = False) -> bool:
        try:
            console.print(Panel(f"🚀 Starting Deployment", 
                              style="bold blue", expand=False))
            
            if self.dry_run:
                console.print("[yellow]Running in DRY RUN mode - no changes will be made[/yellow]")
            
            # Get repository lists
            all_repos = self.config['repositories']['libraries'] + self.config['repositories']['services']
            libraries, services = self.automation.order_repositories(all_repos)
            
            if libraries_only:
                services = []
                console.print("[yellow]Libraries only mode - skipping services[/yellow]")
            
            display_repository_summary(libraries, services)
            
            # Validate repositories
            valid_libraries = self.automation.validate_repositories_with_strategies(libraries)
            valid_services = self.automation.validate_repositories_with_strategies(services)
            
            if not valid_libraries and not valid_services:
                console.print("[red]No repositories have commits to deploy[/red]")
                return False
            
            # Send deployment start notification
            if not self.dry_run:
                self.discord_notifier.send_deployment_start("deployment", valid_libraries, valid_services)
            
            success = True
            
            # Phase 1: Deploy Libraries
            if valid_libraries:
                success &= self._deploy_phase(valid_libraries, DeploymentPhase.LIBRARIES)
            
            # Phase 2: Deploy Services (only if libraries succeeded)
            if valid_services and success:
                success &= self._deploy_phase(valid_services, DeploymentPhase.SERVICES)
            
            # Send final notification
            total_time = time.time() - self.start_time
            all_repos = valid_libraries + valid_services
            if not self.dry_run:
                self.discord_notifier.send_final_success(
                    "deployment", len(all_repos), all_repos if success else [], 
                    [] if success else all_repos, total_time
                )
            
            return success
            
        except Exception as e:
            console.print(f"[red]Critical error in deployment orchestration: {e}[/red]")
            if not self.dry_run:
                self.discord_notifier.send_critical_failure(str(e))
            return False
    
    def _deploy_phase(self, repos: List[str], phase: DeploymentPhase) -> bool:
        phase_name = phase.value.title()
        console.print(Panel(f"📦 Phase: {phase_name} Deployment", 
                          style="bold green", expand=False))
        
        if self.dry_run:
            console.print(f"[yellow]Would deploy {len(repos)} {phase_name.lower()} repositories[/yellow]")
            return True
        
        try:
            # Create MRs for this phase
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TimeElapsedColumn(),
                console=console
            ) as progress:
                task = progress.add_task(f"Creating {phase_name} MRs...", total=len(repos))
                
                mr_statuses = self.automation.create_merge_requests_for_phase(
                    repos, phase
                )
                progress.update(task, completed=len(repos))
            
            display_mr_status_table(mr_statuses, f"{phase_name} Merge Requests")
            
            # Send phase update
            progress_info = self.automation.get_deployment_progress(mr_statuses, phase)
            self.discord_notifier.send_phase_update(progress_info, mr_statuses)
            
            # Monitor MRs
            console.print(f"[blue]Monitoring {phase_name.lower()} merge requests...[/blue]")
            mr_statuses = self.automation.monitor_merge_requests(mr_statuses)
            
            # Update display
            display_mr_status_table(mr_statuses, f"{phase_name} Results")
            
            # Get successful repos
            successful_repos = [mr.repo_name for mr in mr_statuses if mr.state == "merged"]
            failed_repos = [mr.repo_name for mr in mr_statuses if mr.state == "failed"]
            
            # Send phase completion
            progress_info = self.automation.get_deployment_progress(mr_statuses, phase)
            self.discord_notifier.send_phase_complete(
                phase, successful_repos, failed_repos, progress_info.environment
            )
            
            if failed_repos:
                console.print(f"[yellow]Some {phase_name.lower()} repositories failed: {', '.join(failed_repos)}[/yellow]")
            
            # Wait for environment deployment if needed
            if successful_repos:
                # Determine environment from first successful MR
                env_name = progress_info.environment
                if env_name != "unknown":
                    console.print(f"[blue]Waiting for deployment to {env_name.upper()}...[/blue]")
                    deployment_success = self.automation.wait_for_environment_deployment(
                        successful_repos, env_name
                    )
                    
                    self.discord_notifier.send_environment_deployment(
                        env_name, successful_repos, deployment_success
                    )
                    
                    if not deployment_success:
                        console.print(f"[red]Deployment to {env_name.upper()} failed[/red]")
                        return False
                
                # Check for additional commits that need to be merged to final target
                # Only process additional commits if wait_for_deployment is False for this environment
                env_config = self.config.get('environments', {}).get(env_name, {})
                should_wait_for_deployment = env_config.get('wait_for_deployment', False)
                
                if env_name != "unknown" and self.check_additional_commits and not should_wait_for_deployment:
                    self._process_additional_commits(successful_repos, mr_statuses)
                elif should_wait_for_deployment:
                    console.print(f"[yellow]Stopping at deploy branch due to wait_for_deployment=true for {env_name}[/yellow]")
            
            return len(successful_repos) > 0
            
        except Exception as e:
            console.print(f"[red]Error in {phase_name.lower()} phase: {e}[/red]")
            self.discord_notifier.send_critical_failure(str(e))
            return False
    
    def _process_additional_commits(self, successful_repos: List[str], mr_statuses: List[MRStatus]):
        """
        ประมวลผล additional commits จาก branches อื่นๆ หลังจาก deployment สำเร็จ
        """
        try:
            console.print(Panel("🔍 Checking for Additional Commits", style="bold cyan", expand=False))
            
            if self.dry_run:
                console.print("[yellow]Dry run: Would check for additional commits[/yellow]")
                return
            
            # หา final target branch (ปกติจะเป็น sit2)
            final_target_branch = "sit2"
            current_target_branch = mr_statuses[0].target_branch if mr_statuses else "ss-dev"
            
            console.print(f"[blue]Scanning for branches with commits between {current_target_branch} and {final_target_branch}...[/blue]")
            
            # Process additional commits
            additional_mrs = self.automation.process_additional_commits(
                successful_repos, current_target_branch, final_target_branch, "additional"
            )
            
            if additional_mrs:
                console.print(f"[green]Found {len(additional_mrs)} additional branches with commits[/green]")
                
                # Display additional MRs
                display_mr_status_table(additional_mrs, "Additional Merge Requests")
                
                # Monitor additional MRs
                console.print("[blue]Monitoring additional merge requests...[/blue]")
                monitored_mrs = self.automation.monitor_merge_requests(additional_mrs)
                
                # Display final results
                display_mr_status_table(monitored_mrs, "Additional MRs - Final Status")
                
                # Send notification about additional commits
                successful_additional = [mr.repo_name for mr in monitored_mrs if mr.state == "merged"]
                failed_additional = [mr.repo_name for mr in monitored_mrs if mr.state == "failed"]
                
                if successful_additional:
                    console.print(f"[green]Successfully merged additional commits from {len(successful_additional)} branches[/green]")
                
                if failed_additional:
                    console.print(f"[yellow]Failed to merge additional commits from {len(failed_additional)} branches[/yellow]")
                
                # Count intermediate commits for better reporting
                intermediate_count = sum(1 for mr in additional_mrs if mr.source_branch in ['ss-dev', 'dev2'])
                
                # Send Discord notification
                self.discord_notifier.send_additional_commits_update(
                    "additional", len(additional_mrs), successful_additional, failed_additional, intermediate_count
                )
                
            else:
                console.print("[green]No additional branches with new commits found[/green]")
                
        except Exception as e:
            console.print(f"[red]Error processing additional commits: {e}[/red]")
            logger.error(f"Failed to process additional commits: {e}")
            if not self.dry_run:
                self.discord_notifier.send_critical_failure(f"Additional commits processing failed: {str(e)}")

@click.command()
@click.option('--target', default='all', help='Target environment (dev2, sit2, all)')
@click.option('--libraries-only', is_flag=True, help='Deploy libraries only')
@click.option('--dry-run', is_flag=True, help='Dry run mode - no changes made')
@click.option('--check-additional-commits', is_flag=True, default=True, help='Check for additional commits after deployment (default: enabled)')
@click.option('--debug-branches', is_flag=True, help='Debug branch status and commits')
@click.option('--lib-only', is_flag=True, help='Process intermediate commits for libraries only (intermediate & progressive by default)')
@click.option('--service-only', is_flag=True, help='Process intermediate commits for services only (intermediate & progressive by default)')
@click.option('--disable-progressive', is_flag=True, help='Disable progressive MR creation')
@click.option('--force-merge', help='Enable auto-merge for specific MR IDs (comma-separated, format: repo:mr_id)')
@click.option('--merge', help='Directly merge specific MRs (comma-separated, format: repo:mr_id)')
@click.option('--config', default='config.yaml', help='Config file path')
@click.option('--log-level', default='INFO', help='Log level (DEBUG, INFO, WARNING, ERROR)')
def main(target: str, libraries_only: bool, dry_run: bool, 
         check_additional_commits: bool, debug_branches: bool, 
         lib_only: bool, service_only: bool, 
         disable_progressive: bool, force_merge: str, merge: str, config: str, log_level: str):
    """
    Automated MR Script for multi-repository deployment workflows.
    
    This script automates the creation and management of Merge Requests
    across multiple repositories with dependency-aware ordering and
    environment-specific deployment strategies.
    
    Source branches are now configured per repository in the config file
    under branch_strategies, eliminating the need for sprint parameters.
    """
    
    console.print(Panel.fit("🤖 MR Automation Bot", style="bold blue"))
    
    # Setup
    validate_environment()
    config_data = load_config(config)
    setup_logging(log_level, config_data['logging']['file'])
    
    # Debug branches if requested
    if debug_branches:
        debug_branch_status(config_data)
        return
    
    # Process intermediate commits if requested
    if lib_only or service_only:
        repo_filter = None
        progressive_enabled = True  # Default enabled for intermediate commands
        
        if lib_only:
            repo_filter = 'libraries'
        elif service_only:
            repo_filter = 'services'
        
        # Allow disabling progressive if explicitly requested
        if disable_progressive:
            progressive_enabled = False
            
        process_intermediate_commits_directly(config_data, dry_run, repo_filter, progressive_enabled)
        return
    
    # Enable auto-merge if requested
    if force_merge:
        enable_auto_merge_mrs(config_data, force_merge)
        return
    
    # Directly merge MRs if requested
    if merge:
        directly_merge_mrs(config_data, merge)
        return
    
    # Create orchestrator
    orchestrator = MRDeploymentOrchestrator(config_data, dry_run, check_additional_commits)
    
    # Run deployment
    console.print(f"[green]Starting deployment[/green]")
    success = orchestrator.run_deployment(target, libraries_only)
    
    if success:
        console.print(Panel("✅ Deployment completed successfully!", 
                          style="bold green", expand=False))
        sys.exit(0)
    else:
        console.print(Panel("❌ Deployment failed or incomplete!", 
                          style="bold red", expand=False))
        sys.exit(1)

if __name__ == '__main__':
    main()