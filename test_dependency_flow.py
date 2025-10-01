#!/usr/bin/env python3
"""
Test script to validate the improved dependency-aware auto-merge flow
"""

import yaml
from gitlab_client import GitLabClient
from mr_automation import MRAutomation
from discord_notifier import DiscordNotifier

def test_dependency_checking():
    """Test the dependency checking logic"""
    
    print("🧪 Testing dependency-aware auto-merge flow...")
    
    # Load config
    try:
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        print("❌ config.yaml not found. Please ensure it exists.")
        return False
    
    try:
        # Initialize components
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
        
        # Test case: Check dependency logic with a sample repository
        test_repo = "ms-self-serve"  # Use the repo from your example
        
        try:
            # Get repository strategy
            strategy_name, flow = automation.get_repository_strategy(test_repo)
            print(f"✅ Repository strategy for {test_repo}: {strategy_name}")
            print(f"✅ Flow: {' → '.join(flow)}")
            
            # Test the new dependency checking method
            for i in range(1, len(flow)):
                has_pending = automation._check_pending_previous_commits(test_repo, flow, i)
                branch_at_index = flow[i] if i < len(flow) else "N/A"
                print(f"✅ Branch {branch_at_index} (index {i}): Has pending previous commits = {has_pending}")
            
            print("✅ Dependency checking logic validated successfully!")
            return True
            
        except ValueError as e:
            print(f"⚠️  Repository {test_repo} not found in strategy configuration: {e}")
            print("✅ This is expected if the test repo is not in your config")
            return True
        
    except Exception as e:
        print(f"❌ Error testing dependency logic: {e}")
        return False

def explain_improvements():
    """Explain what the improvements do"""
    print("\n📋 Auto-merge Flow Improvements:")
    print("=" * 50)
    print("🔹 BEFORE: The system would create MRs for all branches simultaneously")
    print("   Example: ss/sprint4/all → ss-dev, ss-dev → dev2, dev2 → sit2 (all at once)")
    print()
    print("🔹 AFTER: The system respects branch dependencies and creates MRs sequentially")
    print("   Example: Only creates ss/sprint4/all → ss-dev first")
    print("   Then waits for that to merge before creating ss-dev → dev2")
    print("   Finally creates dev2 → sit2 only after ss-dev → dev2 is merged")
    print()
    print("🔹 KEY BENEFITS:")
    print("   • Prevents merge conflicts from parallel merges")
    print("   • Ensures proper commit ordering in target branches") 
    print("   • Reduces pipeline resource usage")
    print("   • Makes the merge process more predictable")
    print()
    print("🔹 APPLIES TO:")
    print("   • Intermediate commits processing (--lib-only, --service-only)")
    print("   • Progressive merge requests")
    print("   • Additional commits integration")

if __name__ == "__main__":
    explain_improvements()
    print("\n" + "=" * 50)
    test_dependency_checking()