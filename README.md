# MR Automation Bot

A comprehensive automated script for creating and managing Merge Requests (MRs) across multiple GitLab repositories with specific branch strategies and deployment workflows.

**🎯 Main Entry Point: Use `./mr-automation.sh` for all operations**

## ⚡ Quick Start

```bash
# 1. Clone and setup
git clone <repository-url>
cd mr_bot
chmod +x mr-automation.sh

# 2. Configure environment
cp .env.example .env
# Edit .env with your GITLAB_TOKEN and DISCORD_WEBHOOK_URL

# 3. Update config.yaml with your repositories and GitLab settings

# 4. Test setup
./mr-automation.sh --dry-run --debug-branches

# 5. Run automation
./mr-automation.sh --lib-only
```

## Features

- 🚀 **Multi-repository Support**: Automate MRs across multiple GitLab repositories
- 📦 **Dependency-aware Deployment**: Libraries deploy before services
- 🔄 **Auto-merge Capability**: Automatically merge when pipelines pass
- 🌍 **Environment-specific Workflows**: Support for dev2 and sit2 environments
- 📊 **Rich Progress Tracking**: Beautiful CLI progress indicators and status tables
- 🔔 **Discord Notifications**: Rich embed notifications with deployment status
- 🛡️ **Error Handling**: Comprehensive retry logic and error recovery
- 🏃 **Dry Run Mode**: Test workflows without making changes
- 🔍 **Additional Commits Detection**: Automatically find and merge commits from other branches that were not included in the original deployment
- ⚡ **Smart Branch Discovery**: Scan all branches to identify new commits between merge and final target branches
- 🎯 **Complete Flow Automation**: ✨ **NEW!** Continues merging through entire branch flow without stopping at intermediate branches like ss-dev

## New Simplified Commands

The MR Automation Bot now features **two simple commands** that handle intermediate commits with progressive MR creation by default:

- **`--lib-only`**: Process intermediate commits for libraries only
- **`--service-only`**: Process intermediate commits for services only

These commands automatically:
- ✅ Process intermediate branch commits (no need to specify `--process-intermediate`)
- ✅ Enable progressive MR creation (automatically create follow-up MRs after successful merges)
- ✅ Focus on specific repository types (libraries vs services)

**Simple Usage:**
```bash
# Libraries only - intermediate & progressive by default
./mr-automation.sh --lib-only

# Services only - intermediate & progressive by default  
./mr-automation.sh --service-only
```

## Installation & Setup

### Prerequisites

#### System Requirements
- **Python 3.7+** (required) - Python 3.8+ recommended for optimal compatibility
- **pip** (Python package installer) - Usually comes with Python
- **Git** (for cloning the repository and version control)
- **Virtual environment support** (venv or virtualenv)

#### Software Dependencies
- **GitLab Personal Access Token** with API permissions (see setup instructions below)
- **Network access** to your GitLab instance
- **Shell/Terminal access** (Bash on Linux/Mac, PowerShell/CMD on Windows)

#### Optional Components
- **Discord Webhook URL** (for deployment notifications and alerts)
- **Text editor** (for configuration file editing)

#### Access Requirements
- **GitLab repository access** with merge request permissions
- **Branch creation/modification permissions** on target repositories
- **Pipeline execution visibility** (to monitor deployment status)

### 1. Clone and Setup

```bash
# Clone the repository
git clone <repository-url>
cd mr_bot

# Make the script executable
chmod +x mr-automation.sh

# The script will automatically:
# - Create virtual environment if needed
# - Install dependencies from requirements.txt  
# - Validate configuration files
```

### 2. Install Dependencies

The automation script handles dependency installation automatically, but you can also install manually:

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate  # On Linux/Mac
# or
venv\Scripts\activate     # On Windows

# Install dependencies
pip install -r requirements.txt
```

### 3. Setup Environment Variables

```bash
# Copy environment template
cp .env.example .env

# Edit with your credentials
nano .env
```

Required environment variables in `.env`:
```bash
# GitLab Configuration
GITLAB_TOKEN=your_gitlab_personal_access_token

# Discord Notifications (optional)
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/your_webhook_url
```

### 4. Configure Repositories and Strategies

Update `config.yaml` with your repository and environment settings:
- Configure `source_branch` for each strategy in `branch_strategies`
- Each repository can have different source branches
- Update GitLab URL and project group

Example `config.yaml`:
```yaml
gitlab:
  base_url: "https://gitlab.orbitdigital.co.th"  # Your GitLab URL
  api_token: "${GITLAB_TOKEN}"
  project_group: "xplore"                        # Your project group

repositories:
  libraries:
    - explore-go
    - proto
  services:
    - ms-self-serve
    - ms-self-serve-batch

branch_strategies:
  strategy_a:
    repos: [ms-self-serve, ms-self-serve-batch]
    source_branch: sprint4/all
    flow: [sprint4/all, ss-dev, sit2]
```

### 5. First Run Test

```bash
# Test the setup with dry run
./mr-automation.sh --dry-run --debug-branches

# If everything looks good, start with libraries only
./mr-automation.sh --lib-only
```

## Usage

```bash
# Deploy to all environments (source branches from config)
./mr-automation.sh --target=all

# Deploy libraries only
./mr-automation.sh --libraries-only

# Dry run mode (no changes made)
./mr-automation.sh --dry-run

# Debug branch status and commits
./mr-automation.sh --debug-branches

# Process intermediate commits for libraries only (intermediate & progressive by default)
./mr-automation.sh --lib-only

# Process intermediate commits for services only (intermediate & progressive by default)
./mr-automation.sh --service-only

# Disable progressive MRs if needed
./mr-automation.sh --lib-only --disable-progressive
./mr-automation.sh --service-only --disable-progressive

# Force merge specific MRs
./mr-automation.sh --force-merge="explore-go:1653,proto:2812"
```

## Repository Strategies

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

**✨ NEW: Complete Flow Automation**

The system now automatically creates MRs for the **entire flow** without stopping at intermediate branches:
- When merge to `ss-dev` completes ✅
- **Strategy A**: Automatically creates `ss-dev` → `sit2` MR
- **Strategy B**: Automatically creates `ss-dev` → `dev2` **AND** `dev2` → `sit2` MRs
- **No manual intervention needed** - continues until reaching final target branch

**Note:** Source branches are now configured per repository in `config.yaml` under `branch_strategies.source_branch`

## Deployment Flow

1. **Libraries First** (Priority 1)
   - `explore-go`
   - `proto`
   - `library-java-utility`

2. **Services Second** (Priority 2)
   - `ms-account-go`
   - `ms-bff-go`
   - `ms-bbff-go`
   - `ms-payment`
   - `ms-self-serve`
   - `ms-self-serve-batch`

## Additional Commits Detection

The bot now includes intelligent **Additional Commits Detection** that automatically scans for branches with new commits that were not included in the original deployment flow.

### How It Works

1. **After Successful Deployment**: Once the standard deployment flow completes successfully
2. **Branch Scanning**: The bot scans all branches in each repository
3. **Commit Analysis**: Identifies branches with commits not present in the final target branch (sit2)
4. **Automatic MR Creation**: Creates additional MRs for these branches directly to the final target
5. **Enhanced Notifications**: Provides detailed Discord notifications about discovered additional commits

### Benefits

- 🔍 **Zero Missing Commits**: Ensures all relevant code changes are deployed
- ⚡ **Automatic Discovery**: No manual intervention needed to find missed commits
- 📋 **Detailed Reporting**: Clear visibility into what additional commits were found
- 🚀 **Seamless Integration**: Works transparently with existing deployment flows
- 🛡️ **Safety First**: Each additional MR includes detailed commit information for review

### Example Scenarios

#### Scenario 1: Regular Additional Commits
```
Original Flow:
[source_branch] → ss-dev → sit2 ✅

Additional Commits Found:
feature/new-payment-fix → sit2 (3 commits)
hotfix/urgent-bug-fix → sit2 (1 commit)
```

#### Scenario 2: Intermediate Branch Commits (New!)
```
Issue: proto has new commits in ss-dev but [source_branch] doesn't have them

Original Flow:
[source_branch] → ss-dev → sit2 ✅
     (empty)      (3 commits)

Intermediate Commits Found:
ss-dev → sit2 (3 commits) ✅ 
```

The bot now intelligently detects commits that exist in intermediate branches (like `ss-dev`, `dev2`) but are not present in the configured source branch, ensuring complete deployment coverage.

## Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--target=ENV` | Target environment (dev2, sit2, all) | all |
| `--libraries-only` | Deploy libraries only | false |
| `--dry-run` | Dry run mode - no changes made | false |
| `--debug-branches` | Debug branch status and commits | false |
| `--lib-only` | Process intermediate commits for libraries only (intermediate & progressive by default) | false |
| `--service-only` | Process intermediate commits for services only (intermediate & progressive by default) | false |
| `--disable-progressive` | Disable progressive MR creation | false |
| `--force-merge=MR_LIST` | Force merge specific MRs (format: repo:mr_id,repo:mr_id) | - |
| `--config=FILE` | Config file path | config.yaml |
| `--log-level=LEVEL` | Log level (DEBUG, INFO, WARNING, ERROR) | INFO |

**Note:** Source branches are no longer specified via command line. They are configured per repository in `config.yaml`.

## Configuration

### config.yaml Structure

```yaml
repositories:
  libraries:
    - explore-go
    - proto
    - library-java-utility
  services:
    - ms-account-go
    - ms-bff-go
    - ms-bbff-go
    - ms-payment
    - ms-self-serve
    - ms-self-serve-batch

branch_strategies:
  strategy_a:
    repos: [ms-self-serve, ms-self-serve-batch]
    source_branch: sprint4/all
    flow: [sprint4/all, ss-dev, sit2]
  strategy_b:
    repos: [explore-go, proto, library-java-utility, ms-account-go, ms-bff-go, ms-bbff-go, ms-payment]
    source_branch: ss/sprint4/all
    flow: [ss/sprint4/all, ss-dev, dev2, sit2]

environments:
  dev2:
    triggered_by: [ss-dev, dev2]
    wait_for_deployment: true
  sit2:
    triggered_by: [sit2]
    wait_for_deployment: true

gitlab:
  base_url: "https://gitlab.example.com"
  api_token: "${GITLAB_TOKEN}"
  project_group: "your-group"

discord:
  webhook_url: "${DISCORD_WEBHOOK_URL}"
  mentions:
    critical_failure: "@DevOps @TeamLead"
    success: "@dev-team"

automation:
  retry_attempts: 3
  retry_delay: 30
  pipeline_timeout: 1800
  deployment_timeout: 3600
  auto_merge: true
```

## Discord Notifications

The bot sends rich embed notifications to Discord with:

- 🚀 **Deployment Start**: Overview of libraries and services to deploy
- 📦 **Phase Updates**: Progress for libraries and services phases
- ✅ **Completion Status**: Success/failure summary with links
- 🚨 **Critical Failures**: Error alerts with @mentions for manual intervention
- 🌍 **Environment Status**: Deployment status per environment

## Error Handling

### Automatic Retry Logic
- API call failures with exponential backoff
- Network timeouts and transient errors
- Rate limiting with appropriate delays

### Manual Intervention Alerts
- Merge conflicts requiring resolution
- Pipeline failures needing investigation
- Permission or access issues
- Deployment failures

### Recovery Features
- Workflow state persistence
- Resume from failure points
- Rollback capabilities
- Comprehensive logging

## Examples

### New Simplified Commands (Recommended)
```bash
# Process intermediate commits for libraries only
# (intermediate & progressive by default)
./mr-automation.sh --lib-only

# Process intermediate commits for services only
# (intermediate & progressive by default)
./mr-automation.sh --service-only

# Dry run with new commands
./mr-automation.sh --lib-only --dry-run

# Disable progressive MRs if needed
./mr-automation.sh --lib-only --disable-progressive
```

### Full Deployment Commands
```bash
# Deploy to all environments with full automation
./mr-automation.sh --target=all

# Deploy only library repositories first
./mr-automation.sh --libraries-only

# Deploy to specific environment
./mr-automation.sh --target=dev2
```

### Debug and Testing
```bash
# Test the workflow without making any changes
./mr-automation.sh --dry-run --log-level=DEBUG

# Debug branch status and commits
./mr-automation.sh --debug-branches
```

## Project Structure

```
project_bot/
├── mr-automation.sh        # 🎯 Main entry script (USE THIS)
├── main.py                 # Python main script (called by wrapper)
├── mr_automation.py        # Core MR automation logic
├── gitlab_client.py        # GitLab API client
├── models.py              # Data models and classes
├── config.yaml            # Repository and environment configuration
├── .env                   # Environment variables (create from .env.example)
├── requirements.txt       # Python dependencies
└── mr_automation.log     # Application logs
```

## Requirements

- **Python 3.7+** (automatically managed by wrapper script)
- **GitLab Personal Access Token** with these specific scopes:
  - `api` - Full access to the API
  - `read_repository` - Read repository content
  - `write_repository` - Write to repository (for creating MRs)
  - `read_user` - Read user information
- **Network Access** to GitLab instance
- **Discord Webhook** (optional, for notifications)

### Creating GitLab Personal Access Token

1. Go to GitLab → User Settings → Access Tokens
2. Create new token with name: `MR Automation Bot`
3. Select scopes: `api`, `read_repository`, `write_repository`, `read_user`
4. Set expiration date (recommended: 1 year)
5. Copy the generated token to your `.env` file

### Setting up Discord Webhook (Optional)

1. Go to your Discord server → Server Settings → Integrations
2. Create a new Webhook
3. Choose the channel for notifications
4. Copy the Webhook URL to your `.env` file

## Troubleshooting

### Installation Issues

1. **Python Version Issues**
   ```bash
   # Check Python version
   python3 --version
   
   # If version is < 3.7, install newer Python
   # On Ubuntu/Debian:
   sudo apt update && sudo apt install python3.9
   
   # On macOS with Homebrew:
   brew install python@3.9
   ```

2. **Virtual Environment Issues**
   ```bash
   # If venv creation fails, try:
   python3 -m pip install --user virtualenv
   python3 -m virtualenv venv
   
   # Or use conda if available:
   conda create -n mr_bot python=3.9
   conda activate mr_bot
   ```

3. **Dependencies Installation Errors**
   ```bash
   # If pip install fails, try upgrading pip:
   pip install --upgrade pip
   
   # Install dependencies one by one to identify issues:
   pip install python-gitlab
   pip install discord-webhook
   pip install rich
   pip install pyyaml
   pip install python-dotenv
   ```

4. **Permission Issues**
   ```bash
   # Make sure script is executable
   chmod +x mr-automation.sh
   
   # If running on Windows, use:
   python main.py --help
   ```

### Configuration Issues

1. **GitLab Token Issues**
   ```bash
   # Verify token has correct permissions
   curl -H "PRIVATE-TOKEN: your_token" https://gitlab.orbitdigital.co.th/api/v4/user
   ```

2. **Missing Branches**
   - Ensure source branches exist in all repositories
   - Check branch naming conventions
   - Use `--debug-branches` to see branch status

3. **Pipeline Failures**
   - Review GitLab CI/CD pipeline logs
   - Ensure all tests pass before automation

4. **Discord Notifications Not Working**
   - Verify webhook URL is correct
   - Check Discord channel permissions
   - Test webhook manually:
     ```bash
     curl -X POST -H "Content-Type: application/json" \
          -d '{"content": "Test message"}' \
          YOUR_DISCORD_WEBHOOK_URL
     ```

5. **Configuration File Errors**
   ```bash
   # Validate YAML syntax
   python -c "import yaml; yaml.safe_load(open('config.yaml'))"
   
   # Check environment variables
   cat .env
   ```

### Debug Mode

Run with debug logging for detailed information:
```bash
./mr-automation.sh --dry-run --log-level=DEBUG
```

### Log Files

- **Application logs**: `mr_automation.log`
- **Error details**: Check console output for real-time status

## Security Considerations

- Store sensitive tokens in `.env` file (not tracked in git)
- Use GitLab tokens with minimal required permissions
- Rotate access tokens regularly
- Monitor automation logs for suspicious activity

## Contributing

1. Test changes with `--dry-run` mode first
2. Update configuration documentation for new features
3. Add appropriate error handling and logging
4. Test Discord notifications in a test channel

## License

This automation script is provided as-is for internal deployment workflows. Modify and adapt as needed for your organization's requirements.