#!/usr/bin/env python3
"""
Test script to validate the pipeline success notification functionality
"""

import yaml
from discord_notifier import DiscordNotifier

def test_pipeline_notification():
    """Test the pipeline success notification"""
    
    # Load config
    try:
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        print("❌ config.yaml not found. Please ensure it exists.")
        return False
    
    try:
        # Initialize Discord notifier
        discord_webhook = config['discord']['webhook_url']
        notifier = DiscordNotifier(discord_webhook, config)
        
        # Test the pipeline success notification
        print("🧪 Testing pipeline success notification...")
        success1 = notifier.send_pipeline_success_notification(
            repo_name="ms-self-serve",
            mr_id=535,
            mr_url="https://gitlab.example.com/group/ms-self-serve/-/merge_requests/535"
        )
        
        if success1:
            print("✅ Pipeline success notification sent successfully!")
        else:
            print("❌ Failed to send pipeline success notification")
            
        # Test the auto-merge waiting notification  
        print("🧪 Testing auto-merge waiting notification...")
        success2 = notifier.send_auto_merge_waiting_notification(
            repo_name="explore-go",
            mr_id=1665,
            mr_url="https://gitlab.example.com/group/explore-go/-/merge_requests/1665"
        )
        
        if success2:
            print("✅ Auto-merge waiting notification sent successfully!")
        else:
            print("❌ Failed to send auto-merge waiting notification")
        
        return success1 and success2
            
    except Exception as e:
        print(f"❌ Error testing notification: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Testing MR monitoring Discord notifications...")
    test_pipeline_notification()