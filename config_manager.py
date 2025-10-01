from typing import Dict, List, Optional, Tuple
import yaml
import os
from dataclasses import dataclass


@dataclass
class RepositoryConfig:
    libraries: List[str]
    services: List[str]


@dataclass
class BranchStrategy:
    name: str
    repos: List[str]
    flow: List[str]


@dataclass
class EnvironmentConfig:
    triggered_by: List[str]
    wait_for_deployment: bool


class ConfigManager:
    """Centralized configuration management for MR automation."""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self._config: Optional[Dict] = None
        self._repositories: Optional[RepositoryConfig] = None
        self._branch_strategies: Optional[List[BranchStrategy]] = None
        
    def load_config(self) -> Dict:
        """Load and parse configuration file with environment variable substitution."""
        if self._config is not None:
            return self._config
            
        with open(self.config_path, 'r') as file:
            config = yaml.safe_load(file)
        
        self._config = self._replace_env_vars(config)
        return self._config
    
    def _replace_env_vars(self, obj):
        """Recursively replace environment variables in configuration."""
        if isinstance(obj, dict):
            return {key: self._replace_env_vars(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._replace_env_vars(item) for item in obj]
        elif isinstance(obj, str) and obj.startswith('${') and obj.endswith('}'):
            env_var = obj[2:-1]
            return os.getenv(env_var, obj)
        return obj
    
    def get_repositories(self) -> RepositoryConfig:
        """Get repository configuration."""
        if self._repositories is None:
            config = self.load_config()
            repos = config['repositories']
            self._repositories = RepositoryConfig(
                libraries=repos['libraries'],
                services=repos['services']
            )
        return self._repositories
    
    def get_all_repositories(self) -> List[str]:
        """Get all repositories (libraries + services)."""
        repos = self.get_repositories()
        return repos.libraries + repos.services
    
    def get_branch_strategies(self) -> List[BranchStrategy]:
        """Get all branch strategies."""
        if self._branch_strategies is None:
            config = self.load_config()
            self._branch_strategies = []
            
            for name, strategy_config in config['branch_strategies'].items():
                self._branch_strategies.append(
                    BranchStrategy(
                        name=name,
                        repos=strategy_config['repos'],
                        flow=strategy_config['flow']
                    )
                )
        return self._branch_strategies
    
    def get_repository_strategy(self, repo_name: str) -> Optional[BranchStrategy]:
        """Get branch strategy for a specific repository."""
        strategies = self.get_branch_strategies()
        for strategy in strategies:
            if repo_name in strategy.repos:
                return strategy
        return None
    
    def get_repository_flow(self, repo_name: str) -> List[str]:
        """Get branch flow for a specific repository."""
        strategy = self.get_repository_strategy(repo_name)
        if strategy:
            return strategy.flow
        raise ValueError(f"No strategy found for repository: {repo_name}")
    
    def get_next_branch(self, repo_name: str, current_branch: str) -> Optional[str]:
        """Get next branch in flow for a repository."""
        flow = self.get_repository_flow(repo_name)
        
        try:
            current_index = flow.index(current_branch)
            if current_index < len(flow) - 1:
                return flow[current_index + 1]
        except ValueError:
            pass
        
        return None
    
    def is_library(self, repo_name: str) -> bool:
        """Check if repository is a library."""
        repos = self.get_repositories()
        return repo_name in repos.libraries
    
    def is_service(self, repo_name: str) -> bool:
        """Check if repository is a service."""
        repos = self.get_repositories()
        return repo_name in repos.services
    
    def order_repositories(self, repos: List[str]) -> Tuple[List[str], List[str]]:
        """Order repositories into libraries and services maintaining config order."""
        repo_config = self.get_repositories()
        
        libraries = [repo for repo in repos if repo in repo_config.libraries]
        services = [repo for repo in repos if repo in repo_config.services]
        
        # Maintain original order from config
        ordered_libraries = [repo for repo in repo_config.libraries if repo in libraries]
        ordered_services = [repo for repo in repo_config.services if repo in services]
        
        return ordered_libraries, ordered_services
    
    def get_environment_config(self, environment: str) -> Optional[EnvironmentConfig]:
        """Get configuration for a specific environment."""
        config = self.load_config()
        env_config = config.get('environments', {}).get(environment)
        
        if env_config:
            return EnvironmentConfig(
                triggered_by=env_config['triggered_by'],
                wait_for_deployment=env_config['wait_for_deployment']
            )
        return None
    
    def get_gitlab_config(self) -> Dict:
        """Get GitLab configuration."""
        config = self.load_config()
        return config['gitlab']
    
    def get_discord_config(self) -> Dict:
        """Get Discord configuration."""
        config = self.load_config()
        return config['discord']
    
    def get_automation_config(self) -> Dict:
        """Get automation configuration."""
        config = self.load_config()
        return config['automation']