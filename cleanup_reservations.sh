#!/bin/bash
#
# Cleanup expired reservations script
# Add to crontab with: crontab -e
# Example: */5 * * * * /path/to/backend/cleanup_reservations.sh
#

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

# Load environment variables
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# Run the cleanup command
poetry run python manage.py cleanup_expired_reservations

# Exit with the command's exit code
exit $?
