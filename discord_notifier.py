import logging
import requests
import time
from typing import Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass

from models import DeploymentProgress, MRStatus, DeploymentPhase

logger = logging.getLogger(__name__)

@dataclass
class DiscordEmbed:
    title: str
    description: str
    color: int
    fields: List[Dict[str, any]]
    footer: Optional[Dict[str, str]] = None
    timestamp: Optional[str] = None

class DiscordNotifier:
    def __init__(self, webhook_url: str, config: Dict):
        self.webhook_url = webhook_url
        self.config = config
        
        # Discord colors
        self.colors = {
            'blue': 3447003,    # Info/Starting
            'green': 65280,     # Success
            'yellow': 16776960, # Warning/In Progress
            'red': 16711680,    # Error/Failed
            'purple': 10181046  # Special/Final
        }
    
    def send_embed(self, embed: DiscordEmbed, mentions: Optional[str] = None) -> bool:
        try:
            embed_dict = {
                'title': embed.title,
                'description': embed.description,
                'color': embed.color,
                'fields': embed.fields,
                'timestamp': embed.timestamp or datetime.utcnow().isoformat()
            }
            
            if embed.footer:
                embed_dict['footer'] = embed.footer
            
            payload = {
                'embeds': [embed_dict]
            }
            
            if mentions:
                payload['content'] = mentions
            
            response = requests.post(self.webhook_url, json=payload)
            response.raise_for_status()
            
            logger.info(f"Discord notification sent: {embed.title}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send Discord notification: {e}")
            return False
    
    def send_deployment_start(self, sprint_name: str, libraries: List[str], services: List[str]) -> bool:
        libraries_text = "\n".join([f"📦 {repo}" for repo in libraries])
        services_text = "\n".join([f"⚙️ {repo}" for repo in services])
        
        embed = DiscordEmbed(
            title=f"🚀 {sprint_name} Deployment Started",
            description="Automated MR creation and deployment workflow initiated",
            color=self.colors['blue'],
            fields=[
                {
                    'name': '📚 Libraries (Phase 1)',
                    'value': libraries_text or "None",
                    'inline': True
                },
                {
                    'name': '🔧 Services (Phase 2)', 
                    'value': services_text or "None",
                    'inline': True
                },
                {
                    'name': '📋 Strategy',
                    'value': "• Libraries deploy first\n• Auto-merge enabled\n• Pipeline validation required",
                    'inline': False
                }
            ],
            footer={'text': 'MR Automation Bot'}
        )
        
        return self.send_embed(embed)
    
    def send_phase_update(self, progress: DeploymentProgress, mr_statuses: List[MRStatus]) -> bool:
        phase_emoji = "📦" if progress.phase == DeploymentPhase.LIBRARIES else "⚙️"
        phase_name = progress.phase.value.title()
        
        # Create status indicators
        completed_text = "\n".join([f"✅ {repo}" for repo in progress.completed_repos]) or "None"
        in_progress_text = "\n".join([f"⏳ {repo}" for repo in progress.in_progress_repos]) or "None"
        failed_text = "\n".join([f"❌ {repo}" for repo in progress.failed_repos]) or "None"
        
        # Determine color based on progress
        if progress.failed_repos:
            color = self.colors['red']
        elif progress.in_progress_repos:
            color = self.colors['yellow']
        elif progress.completed_repos:
            color = self.colors['green']
        else:
            color = self.colors['blue']
        
        embed = DiscordEmbed(
            title=f"{phase_emoji} {phase_name} Phase - {progress.environment.upper()}",
            description=f"Deployment progress for {phase_name.lower()} repositories",
            color=color,
            fields=[
                {
                    'name': '✅ Completed',
                    'value': completed_text,
                    'inline': True
                },
                {
                    'name': '⏳ In Progress',
                    'value': in_progress_text,
                    'inline': True
                },
                {
                    'name': '❌ Failed',
                    'value': failed_text,
                    'inline': True
                }
            ],
            footer={'text': 'MR Automation Bot'}
        )
        
        # Add MR links for completed repos
        if progress.completed_repos:
            mr_links = []
            for mr_status in mr_statuses:
                if mr_status.repo_name in progress.completed_repos and mr_status.mr_url:
                    mr_links.append(f"[{mr_status.repo_name}]({mr_status.mr_url})")
            
            if mr_links:
                embed.fields.append({
                    'name': '🔗 Merge Requests',
                    'value': " • ".join(mr_links),
                    'inline': False
                })
        
        return self.send_embed(embed)
    
    def send_phase_complete(self, phase: DeploymentPhase, successful_repos: List[str], 
                          failed_repos: List[str], environment: str) -> bool:
        phase_emoji = "📦" if phase == DeploymentPhase.LIBRARIES else "⚙️"
        phase_name = phase.value.title()
        
        if failed_repos:
            color = self.colors['yellow']  # Partial success
            title = f"{phase_emoji} {phase_name} Phase Completed (Partial)"
        else:
            color = self.colors['green']
            title = f"{phase_emoji} {phase_name} Phase Completed Successfully"
        
        success_text = "\n".join([f"✅ {repo}" for repo in successful_repos]) or "None"
        failed_text = "\n".join([f"❌ {repo}" for repo in failed_repos]) or "None"
        
        embed = DiscordEmbed(
            title=title,
            description=f"All {phase_name.lower()} repositories processed for {environment.upper()}",
            color=color,
            fields=[
                {
                    'name': '✅ Successful',
                    'value': success_text,
                    'inline': True
                },
                {
                    'name': '❌ Failed',
                    'value': failed_text,
                    'inline': True
                },
                {
                    'name': '📊 Summary',
                    'value': f"**Success Rate:** {len(successful_repos)}/{len(successful_repos) + len(failed_repos)}",
                    'inline': False
                }
            ],
            footer={'text': 'MR Automation Bot'}
        )
        
        return self.send_embed(embed)
    
    def send_environment_deployment(self, environment: str, repos: List[str], success: bool) -> bool:
        if success:
            color = self.colors['green']
            title = f"🌍 {environment.upper()} Deployment Successful"
            description = f"All repositories successfully deployed to {environment}"
        else:
            color = self.colors['red']
            title = f"🌍 {environment.upper()} Deployment Failed"
            description = f"Deployment to {environment} encountered errors"
        
        repos_text = "\n".join([f"{'✅' if success else '❌'} {repo}" for repo in repos])
        
        embed = DiscordEmbed(
            title=title,
            description=description,
            color=color,
            fields=[
                {
                    'name': '📦 Repositories',
                    'value': repos_text,
                    'inline': False
                },
                {
                    'name': '🔗 Environment',
                    'value': f"[View {environment.upper()} Environment](https://your-deployment-url/{environment})",
                    'inline': False
                }
            ],
            footer={'text': 'MR Automation Bot'}
        )
        
        mentions = None
        if not success:
            mentions = self.config['discord']['mentions']['critical_failure']
        
        return self.send_embed(embed, mentions)
    
    def send_critical_failure(self, error_message: str, repo_name: Optional[str] = None) -> bool:
        embed = DiscordEmbed(
            title="🚨 Critical Deployment Failure",
            description="Manual intervention required for deployment workflow",
            color=self.colors['red'],
            fields=[
                {
                    'name': '❌ Error Details',
                    'value': error_message[:1000],  # Discord field limit
                    'inline': False
                }
            ],
            footer={'text': 'MR Automation Bot'}
        )
        
        if repo_name:
            embed.fields.append({
                'name': '📦 Repository',
                'value': repo_name,
                'inline': True
            })
        
        embed.fields.append({
            'name': '🔧 Next Steps',
            'value': "• Check pipeline logs\n• Review merge conflicts\n• Verify branch permissions\n• Contact DevOps if needed",
            'inline': False
        })
        
        mentions = self.config['discord']['mentions']['critical_failure']
        return self.send_embed(embed, mentions)
    
    def send_final_success(self, sprint_name: str, total_repos: int, successful_repos: List[str], 
                          failed_repos: List[str], total_time: float) -> bool:
        success_rate = len(successful_repos) / total_repos * 100
        
        if failed_repos:
            color = self.colors['yellow']
            title = f"🎯 {sprint_name} Deployment Completed (Partial Success)"
        else:
            color = self.colors['green']
            title = f"🎉 {sprint_name} Deployment Completed Successfully"
        
        success_text = "\n".join([f"✅ {repo}" for repo in successful_repos]) or "None"
        failed_text = "\n".join([f"❌ {repo}" for repo in failed_repos]) or "None"
        
        # Format time
        hours = int(total_time // 3600)
        minutes = int((total_time % 3600) // 60)
        time_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
        
        embed = DiscordEmbed(
            title=title,
            description=f"Automated deployment workflow completed for {sprint_name}",
            color=color,
            fields=[
                {
                    'name': '✅ Successful Deployments',
                    'value': success_text,
                    'inline': True
                },
                {
                    'name': '❌ Failed Deployments',
                    'value': failed_text,
                    'inline': True
                },
                {
                    'name': '📊 Statistics',
                    'value': f"**Success Rate:** {success_rate:.1f}%\n**Total Time:** {time_str}\n**Repositories:** {total_repos}",
                    'inline': False
                },
                {
                    'name': '🔗 Environments',
                    'value': "[DEV2](https://your-deployment-url/dev2) • [SIT2](https://your-deployment-url/sit2)",
                    'inline': False
                }
            ],
            footer={'text': 'MR Automation Bot'}
        )
        
        mentions = self.config['discord']['mentions']['success']
        return self.send_embed(embed, mentions)
    
    def send_progress_update(self, current_step: str, total_steps: int, current_step_num: int) -> bool:
        progress_bar = "▓" * current_step_num + "░" * (total_steps - current_step_num)
        progress_percent = (current_step_num / total_steps) * 100
        
        embed = DiscordEmbed(
            title="⚡ Deployment Progress Update",
            description=current_step,
            color=self.colors['blue'],
            fields=[
                {
                    'name': '📊 Progress',
                    'value': f"```{progress_bar}``` {progress_percent:.1f}% Complete ({current_step_num}/{total_steps})",
                    'inline': False
                }
            ],
            footer={'text': 'MR Automation Bot'}
        )
        
        return self.send_embed(embed)
    
    def send_additional_commits_update(self, sprint_name: str, total_branches: int, 
                                     successful_repos: List[str], failed_repos: List[str],
                                     intermediate_count: int = 0) -> bool:
        """
        ส่งการแจ้งเตือนเกี่ยวกับ additional commits ที่พบและประมวลผل
        
        Args:
            sprint_name: ชื่อ sprint
            total_branches: จำนวน branches ทั้งหมดที่พบ
            successful_repos: repositories ที่ merge สำเร็จ
            failed_repos: repositories ที่ merge ไม่สำเร็จ
        """
        if total_branches == 0:
            # No additional commits found
            embed = DiscordEmbed(
                title="✅ Additional Commits Check Complete",
                description=f"**{sprint_name}** - No additional branches with new commits found",
                color=self.colors['green'],
                fields=[
                    {
                        'name': '🔍 Scan Result',
                        'value': 'All repositories are up to date with the latest commits',
                        'inline': False
                    }
                ],
                footer={'text': 'MR Automation Bot - Additional Commits Check'}
            )
            return self.send_embed(embed)
        
        # Additional commits were found and processed
        status_icon = "✅" if not failed_repos else "⚠️"
        status_color = self.colors['green'] if not failed_repos else self.colors['yellow']
        
        # Create summary text
        summary_parts = []
        if successful_repos:
            summary_parts.append(f"✅ **{len(successful_repos)}** branches merged successfully")
        if failed_repos:
            summary_parts.append(f"❌ **{len(failed_repos)}** branches failed to merge")
        
        summary = "\n".join(summary_parts)
        
        # Enhanced summary with intermediate commits info
        regular_branches = total_branches - intermediate_count
        summary_text = f"Found **{total_branches}** branches with new commits\n"
        
        if intermediate_count > 0 and regular_branches > 0:
            summary_text += f"• **{intermediate_count}** intermediate branch commits\n• **{regular_branches}** additional branch commits\n"
        elif intermediate_count > 0:
            summary_text += f"• **{intermediate_count}** intermediate branch commits\n"
        else:
            summary_text += f"• **{regular_branches}** additional branch commits\n"
        
        summary_text += summary
        
        fields = [
            {
                'name': '📊 Summary',
                'value': summary_text,
                'inline': False
            }
        ]
        
        # Add successful repos if any
        if successful_repos:
            repos_text = "\n".join([f"• {repo}" for repo in successful_repos[:10]])
            if len(successful_repos) > 10:
                repos_text += f"\n... and {len(successful_repos) - 10} more"
            
            fields.append({
                'name': '✅ Successfully Merged',
                'value': repos_text,
                'inline': True
            })
        
        # Add failed repos if any
        if failed_repos:
            repos_text = "\n".join([f"• {repo}" for repo in failed_repos[:10]])
            if len(failed_repos) > 10:
                repos_text += f"\n... and {len(failed_repos) - 10} more"
            
            fields.append({
                'name': '❌ Failed to Merge',
                'value': repos_text,
                'inline': True
            })
        
        embed = DiscordEmbed(
            title=f"{status_icon} Additional Commits Integration - {sprint_name}",
            description="Discovered and processed additional branches with new commits that were not included in the original deployment flow.",
            color=status_color,
            fields=fields,
            footer={'text': 'MR Automation Bot - Additional Commits Integration'}
        )
        
        # Add mentions if there are failures
        mentions = None
        if failed_repos:
            mentions = self.config['discord']['mentions'].get('critical_failure', '@DevOps')
        
        return self.send_embed(embed, mentions)
    
    def send_pipeline_success_notification(self, repo_name: str, mr_id: int, mr_url: Optional[str] = None) -> bool:
        """
        Send notification when pipeline succeeds and MR is waiting for auto-merge
        
        Args:
            repo_name: Repository name
            mr_id: Merge request ID
            mr_url: Optional MR URL
            
        Returns:
            True if notification sent successfully
        """
        embed = DiscordEmbed(
            title="🔄 Pipeline Success - Waiting for Auto-merge",
            description=f"Pipeline passed for MR in **{repo_name}** and is now waiting for GitLab's auto-merge to complete",
            color=self.colors['yellow'],
            fields=[
                {
                    'name': '📦 Repository',
                    'value': repo_name,
                    'inline': True
                },
                {
                    'name': '🔗 Merge Request',
                    'value': f"[MR #{mr_id}]({mr_url})" if mr_url else f"MR #{mr_id}",
                    'inline': True
                },
                {
                    'name': '⏳ Status',
                    'value': "Pipeline succeeded, auto-merge in progress...",
                    'inline': False
                }
            ],
            footer={'text': 'MR Automation Bot - Pipeline Monitor'}
        )
        
        return self.send_embed(embed)
    
    def send_auto_merge_waiting_notification(self, repo_name: str, mr_id: int, mr_url: Optional[str] = None) -> bool:
        """
        Send notification when MR has no pipeline but is waiting for auto-merge conditions
        
        Args:
            repo_name: Repository name
            mr_id: Merge request ID
            mr_url: Optional MR URL
            
        Returns:
            True if notification sent successfully
        """
        embed = DiscordEmbed(
            title="⏸️ Waiting for Auto-merge Conditions",
            description=f"MR in **{repo_name}** has no active pipeline and is waiting for auto-merge conditions to be satisfied",
            color=self.colors['blue'],
            fields=[
                {
                    'name': '📦 Repository',
                    'value': repo_name,
                    'inline': True
                },
                {
                    'name': '🔗 Merge Request',
                    'value': f"[MR #{mr_id}]({mr_url})" if mr_url else f"MR #{mr_id}",
                    'inline': True
                },
                {
                    'name': '📋 Status',
                    'value': "• No pipeline detected\n• Waiting for approval or other conditions\n• Auto-merge will trigger when ready",
                    'inline': False
                },
                {
                    'name': '🔧 Possible Actions',
                    'value': "• Check if manual approval is required\n• Verify branch protection rules\n• Ensure all merge conditions are met",
                    'inline': False
                }
            ],
            footer={'text': 'MR Automation Bot - Auto-merge Monitor'}
        )
        
        return self.send_embed(embed)