# Automated MR Script Requirements

## Overview
A comprehensive automated script/bot for creating and managing Merge Requests (MRs) across multiple GitLab repositories with specific branch strategies and deployment workflows.

**Status: ✅ IMPLEMENTED - Production Ready**

**Entry Point: `./mr-automation.sh`** - All functionality accessible through bash wrapper script

## Git Branch Strategy

### Strategy A: Direct to target
**Repositories:** `ms-self-serve`, `ms-self-serve-batch`
```
[source_branch] → ss-dev (deploy to dev2) → sit2 (deploy to sit2)
```

### Strategy B: Through dev2 branch
**Repositories:** `explore-go`, `proto`, `library-java-utility`, `ms-account-go`, `ms-bff-go`, `ms-bbff-go`, `ms-payment`
```
[source_branch] → ss-dev → dev2 (deploy to dev2) → sit2 (deploy to sit2)
```

**Note:** Source branches are now configured per repository in `config.yaml` under `branch_strategies.source_branch`

## Repository Categories

### Library Repositories (Priority 1 - Deploy First)
- `explore-go`
- `proto` 
- `library-java-utility`

### Service Repositories (Priority 2 - Deploy After Libraries)
- `ms-account-go`
- `ms-bff-go` 
- `ms-bbff-go`
- `ms-payment`
- `ms-self-serve`
- `ms-self-serve-batch`

## Business Rules

### Merge Prerequisites & Auto-Merge Rules
1. **Commit Validation**: Only merge branches with new commits
2. **Pipeline Validation**: Only merge if CI/CD pipeline passes
3. **Dependency Order**: Library repos must be merged before service repos
4. **Auto-Merge**: Automatically merge MR when all conditions are met
5. **Auto-progression**: Automatically create MR to next branch upon successful merge
6. **No Manual Approval**: Skip manual approval process for automation

### Deployment Flow
1. Merge libraries first (explore-go, proto, library-java-utility)
2. Wait for successful deployment to target environment
3. Merge service repositories
4. Auto-create next MR in sequence (ss-dev → dev2 → sit2)

## ✅ Implementation Status

### ✅ Core Features Implemented
- ✅ Multi-repository support
- ✅ GitLab API integration
- ✅ Pipeline status monitoring
- ✅ Branch existence validation
- ✅ Commit difference detection
- ✅ Dependency-aware merge ordering (libraries first)
- ✅ Auto MR creation for next branch
- ✅ Environment deployment status tracking
- ✅ Error handling and retry mechanisms
- ✅ Comprehensive logging system
- ✅ Discord webhook notifications with rich embeds
- ✅ Virtual environment management
- ✅ Configuration validation
- ✅ Dry run mode
- ✅ Auto-merge functionality

### Configuration Structure
```yaml
repositories:
  libraries: [explore-go, proto, library-java-utility]
  services: [ms-account-go, ms-bff-go, ms-bbff-go, ms-payment, ms-self-serve, ms-self-serve-batch]

branch_strategies:
  strategy_a: # ms-self-serve, ms-self-serve-batch
    repos: [ms-self-serve, ms-self-serve-batch]
    source_branch: sprint4/all
    flow: [sprint4/all, ss-dev, sit2]
  strategy_b: # all others
    repos: [explore-go, proto, library-java-utility, ms-account-go, ms-bff-go, ms-bbff-go, ms-payment]
    source_branch: ss/sprint4/all
    flow: [ss/sprint4/all, ss-dev, dev2, sit2]

environments:
  dev2: [ss-dev, dev2]  # branches that deploy to dev2
  sit2: [sit2]          # branches that deploy to sit2
```

## ✅ Core Functions Implemented

### ✅ GitLab Client (`gitlab_client.py`)
1. ✅ `validate_commits()` - Check for new commits between branches
2. ✅ `monitor_merge_status()` - Monitor CI/CD pipeline completion and auto-merge
3. ✅ `create_merge_request()` - Create MR with proper title/description
4. ✅ `create_merge_request_with_commits()` - Enhanced MR creation with commit details
5. ✅ `branch_exists()` - Validate branch existence
6. ✅ `get_branches_with_new_commits()` - Find additional branches with new commits
7. ✅ `get_intermediate_branch_commits()` - Detect intermediate branch commits
8. ✅ `wait_for_deployment()` - Monitor environment deployment status

### ✅ MR Automation (`mr_automation.py`)
1. ✅ `get_repository_strategy()` - Determine branch flow strategy per repo
2. ✅ `order_repositories()` - Sort repos by dependency (libraries first)
3. ✅ `validate_repositories()` - Comprehensive repo validation
4. ✅ `create_merge_requests_for_phase()` - Phase-based MR creation
5. ✅ `monitor_merge_requests()` - Track MR completion
6. ✅ `process_additional_commits()` - Handle missed commits automatically
7. ✅ `find_intermediate_branch_commits()` - Advanced commit detection
8. ✅ `create_intermediate_merge_requests()` - Auto-create intermediate MRs

### ✅ Discord Integration (`discord_notifier.py`)
1. ✅ `send_discord_notification()` - Send rich embed notifications
2. ✅ `create_progress_embed()` - Generate visual progress updates
3. ✅ Rich embed messages with deployment status
4. ✅ @mention alerts for critical failures
5. ✅ Color-coded status indicators

### ✅ Error Handling Implemented
- ✅ Retry mechanisms for failed API calls with exponential backoff
- ✅ Comprehensive error logging and reporting
- ✅ Discord notification system for manual intervention alerts
- ✅ Graceful failure handling with detailed error messages
- ✅ State recovery and resume capabilities
- ✅ Validation checks before operations

### ✅ Output Features Implemented
- ✅ Colored CLI progress output with status tables
- ✅ Success/failure notifications via Discord webhooks
- ✅ Rich embed messages with deployment status per environment
- ✅ @mention alerts for critical failures requiring manual intervention
- ✅ Summary report of all MR activities with color-coded status
- ✅ Real-time progress updates during operations
- ✅ Detailed logging to `mr_automation.log`

## Usage Examples

### Command Line Interface
```bash
# Deploy to all environments (source branches from config)
./mr-automation.sh --target=all

# Deploy libraries only
./mr-automation.sh --libraries-only

# Deploy to specific environment
./mr-automation.sh --target=dev2

# Dry run mode  
./mr-automation.sh --dry-run

# Debug branch status and commits
./mr-automation.sh --debug-branches

# Process intermediate commits for libraries only (intermediate & progressive by default)
./mr-automation.sh --lib-only

# Process intermediate commits for services only (intermediate & progressive by default)
./mr-automation.sh --service-only

# Force merge specific MRs
./mr-automation.sh --force-merge="explore-go:1653,proto:2812"
```

### Expected Workflow
1. Script validates all repositories have commits using source branches from config
2. Creates MRs for all library repos: [source_branch] → ss-dev
3. **Enables auto-merge** on all MRs (merge when pipeline passes)
4. Waits for pipeline success and **automatic merge completion**
5. Creates MRs for service repos after libraries complete (also with auto-merge)
6. Monitors deployment to dev2 environment
7. Auto-creates next MRs (ss-dev → dev2 or ss-dev → sit2) with auto-merge enabled
8. Continues until all repos reach sit2
9. Sends completion notification to Discord with summary and deployment links

## ✅ Technology Stack Implemented
- ✅ **Language**: Python + Bash wrapper
- ✅ **Git API**: GitLab API v4
- ✅ **Configuration**: YAML config with environment variables
- ✅ **Logging**: Structured logging with timestamps and log levels
- ✅ **Notifications**: Discord webhooks with rich embeds
- ✅ **HTTP Client**: requests library with retry logic
- ✅ **Virtual Environment**: Automatic venv management
- ✅ **Dependencies**: Managed via requirements.txt

### Discord Integration Requirements

#### Webhook Configuration
```yaml
discord:
  webhook_url: "https://discord.com/api/webhooks/YOUR_WEBHOOK_URL"
  channels:
    deployment: "deployment-alerts"
    success: "deployment-success" 
    errors: "deployment-errors"
  mentions:
    critical_failure: "@DevOps @TeamLead"
    success: "@dev-team"
```

#### Message Types Needed
1. **Deployment Start**: Blue embed with repository list and sprint info
2. **Library Phase Complete**: Green embed showing completed libraries
3. **Service Phase Start**: Yellow embed with service deployment status
4. **Environment Deployment**: Info embed per environment (dev2, sit2)
5. **Critical Failure**: Red embed with error details and @mentions
6. **Final Success**: Green embed with complete deployment summary
7. **Progress Updates**: Regular status updates during long operations

#### Sample Discord Embed Structure
```json
{
  "title": "🚀 Sprint4 Deployment - Phase 1 (Libraries)",
  "description": "Starting automated MR creation and deployment",
  "color": 3447003,
  "fields": [
    {"name": "📦 Libraries", "value": "explore-go ✅\nproto ⏳\nlibrary-java-utility ⏸️", "inline": true},
    {"name": "🏗️ Environment", "value": "dev2", "inline": true},
    {"name": "⏱️ Started", "value": "2024-03-15 14:30 UTC", "inline": true}
  ],
  "footer": {"text": "MR Automation Bot"}
}
```

## ✅ Additional Features Implemented

### 🆕 Advanced Commit Detection
- ✅ **Intermediate Branch Commits**: Detects commits in intermediate branches (ss-dev, dev2) that aren't in source branches
- ✅ **Additional Branch Scanning**: Finds branches with new commits not included in standard deployment flow  
- ✅ **Smart MR Creation**: Automatically creates MRs for missed commits with detailed descriptions
- ✅ **Enhanced Reporting**: Detailed Discord notifications for discovered additional commits

### 🆕 Debug and Force Merge Features  
- ✅ **Debug Mode**: `--debug-branches` to analyze branch status and commits without making changes
- ✅ **Force Merge**: `--force-merge` to manually merge specific MRs by ID
- ✅ **Process Intermediate**: `--process-intermediate` to handle intermediate branch commits directly

### 🆕 Production Enhancements
- ✅ **Comprehensive Error Handling**: Graceful failure recovery with detailed reporting
- ✅ **State Management**: Track deployment progress across phases
- ✅ **Dependency Management**: Libraries deploy before services automatically  
- ✅ **Auto-retry Logic**: Configurable retry attempts with exponential backoff
- ✅ **Configuration Validation**: Validates config and environment setup before execution

## ✅ Status: Production Ready
The automated MR script is fully implemented and production-ready with all required features, robust error handling, comprehensive logging, and flexible configuration for different sprint branches and repository sets.