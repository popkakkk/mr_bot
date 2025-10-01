#!/bin/bash

# MR Automation Script Wrapper
# This script provides a convenient interface for the Python MR automation tool

set -e

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/main.py"
VENV_DIR="$SCRIPT_DIR/venv"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if virtual environment exists
check_venv() {
    if [ ! -d "$VENV_DIR" ]; then
        print_warning "Virtual environment not found. Creating..."
        python3 -m venv "$VENV_DIR"
        source "$VENV_DIR/bin/activate"
        pip install --upgrade pip
        pip install -r "$SCRIPT_DIR/requirements.txt"
        print_success "Virtual environment created and dependencies installed"
    fi
}

# Function to activate virtual environment
activate_venv() {
    source "$VENV_DIR/bin/activate"
}

# Function to check dependencies
check_dependencies() {
    print_status "Checking dependencies..."
    
    # Check Python 3
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is required but not installed"
        exit 1
    fi
    
    # Check if config file exists
    if [ ! -f "$SCRIPT_DIR/config.yaml" ]; then
        print_error "config.yaml not found. Please copy and configure from config.yaml.example"
        exit 1
    fi
    
    # Check if .env file exists (optional but recommended)
    if [ ! -f "$SCRIPT_DIR/.env" ]; then
        print_warning ".env file not found. Using environment variables or config defaults"
        print_warning "Consider copying .env.example to .env and configuring it"
    fi
    
    print_success "Dependencies check passed"
}

# Function to display help
show_help() {
    cat << EOF
MR Automation Script

USAGE:
    $0 [OPTIONS]

OPTIONS:
    --target=TARGET         Target environment (dev2, sit2, all) [default: all]
    --libraries-only        Deploy libraries only
    --dry-run              Dry run mode - no changes made
    --debug-branches       Debug branch status and commits
    --lib-only             Process intermediate commits for libraries only (intermediate & progressive by default)
    --service-only         Process intermediate commits for services only (intermediate & progressive by default)
    --disable-progressive    Disable progressive MR creation
    --force-merge=MR_LIST  Force merge specific MRs (format: repo:mr_id,repo:mr_id)
    --merge=MR_LIST        Directly merge specific MRs (format: repo:mr_id,repo:mr_id)
    --config=CONFIG_FILE    Config file path [default: config.yaml]
    --log-level=LEVEL       Log level (DEBUG, INFO, WARNING, ERROR) [default: INFO]
    --help                  Show this help message

EXAMPLES:
    # Deploy to all environments
    $0 --target=all

    # Deploy libraries only
    $0 --libraries-only

    # Deploy to specific environment
    $0 --target=dev2

    # Dry run mode
    $0 --dry-run

    # Debug mode with verbose logging
    $0 --log-level=DEBUG
    
    # Debug branch status and commits
    $0 --debug-branches
    
    # Process intermediate commits for libraries only (intermediate & progressive by default)
    $0 --lib-only
    
    # Process intermediate commits for services only (intermediate & progressive by default)
    $0 --service-only
    
    # Disable progressive MRs if needed
    $0 --lib-only --disable-progressive
    $0 --service-only --disable-progressive
    
    # Force merge specific MRs
    $0 --force-merge="explore-go:1653,proto:2812"
    
    # Directly merge specific MRs
    $0 --merge="explore-go:1653,proto:2812"

ENVIRONMENT SETUP:
    1. Copy .env.example to .env and configure:
       - GITLAB_TOKEN: Your GitLab personal access token
       - DISCORD_WEBHOOK_URL: Discord webhook URL (optional)

    2. Update config.yaml with your repository and environment settings:
       - Configure source_branch for each strategy in branch_strategies
       - Each repository can have different source branches

    3. Ensure you have access to the GitLab repositories and appropriate permissions

REQUIREMENTS:
    - Python 3.7+
    - GitLab personal access token with API access
    - Network access to GitLab instance
    - (Optional) Discord webhook for notifications

For more information, see the documentation in the project directory.
EOF
}

# Function to validate arguments
validate_args() {
    local has_help=false
    
    for arg in "$@"; do
        case $arg in
            --help)
                has_help=true
                ;;
        esac
    done
    
    if [ "$has_help" = true ]; then
        show_help
        exit 0
    fi
}

# Main execution
main() {
    print_status "Starting MR Automation Script"
    
    # Parse arguments first to check for help
    validate_args "$@"
    
    # Check dependencies
    check_dependencies
    
    # Setup virtual environment
    check_venv
    activate_venv
    
    # Change to script directory
    cd "$SCRIPT_DIR"
    
    # Run the Python script with all arguments
    print_status "Executing MR automation..."
    if python3 "$PYTHON_SCRIPT" "$@"; then
        print_success "MR automation completed successfully!"
    else
        print_error "MR automation failed!"
        exit 1
    fi
}

# Handle special cases
case "${1:-}" in
    --help|-h|help)
        show_help
        exit 0
        ;;
    "")
        print_status "Running with default settings (source branches from config)"
        ;;
esac

# Run main function
main "$@"