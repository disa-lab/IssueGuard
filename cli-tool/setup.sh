#!/usr/bin/env bash
#
# IssueGuard CLI Setup Script (macOS / Linux)
#
# Creates a shell function that wraps `gh` so that
# `gh issue create` is automatically scanned for secrets.
#
# Usage:
#   chmod +x setup.sh && ./setup.sh
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WRAPPER="$SCRIPT_DIR/issueguard.py"

if [ ! -f "$WRAPPER" ]; then
    echo "Error: issueguard.py not found at $WRAPPER"
    exit 1
fi

# Make wrapper executable
chmod +x "$WRAPPER"

# Detect shell config file
if [ -n "$ZSH_VERSION" ] || [ "$SHELL" = "$(which zsh 2>/dev/null)" ]; then
    SHELL_RC="$HOME/.zshrc"
elif [ -n "$BASH_VERSION" ] || [ "$SHELL" = "$(which bash 2>/dev/null)" ]; then
    SHELL_RC="$HOME/.bashrc"
else
    SHELL_RC="$HOME/.profile"
fi

MARKER="# >>> IssueGuard CLI wrapper >>>"
MARKER_END="# <<< IssueGuard CLI wrapper <<<"

# Check if already installed
if grep -q "$MARKER" "$SHELL_RC" 2>/dev/null; then
    echo "IssueGuard CLI wrapper is already installed in $SHELL_RC"
    echo "To reinstall, remove the IssueGuard block from $SHELL_RC first."
    exit 0
fi

cat >> "$SHELL_RC" << EOF

$MARKER
# Wraps \`gh issue create/edit/comment\` to scan for secrets via IssueGuard.
# To remove, delete this block from $SHELL_RC.
gh() {
    # gh subcommands always come first: gh issue create/edit/comment ...
    if [ "\$1" = "issue" ] && { [ "\$2" = "create" ] || [ "\$2" = "edit" ] || [ "\$2" = "comment" ]; }; then
        python3 "$WRAPPER" "\$@"
    else
        command gh "\$@"
    fi
}
$MARKER_END
EOF

echo "✓ IssueGuard CLI wrapper installed in $SHELL_RC"
echo ""
echo "To activate now, run:"
echo "    source $SHELL_RC"
echo ""
echo "After that, \`gh issue create\` commands will be scanned automatically."
