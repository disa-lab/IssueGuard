# IssueGuard CLI Tool

A cross-platform CLI wrapper that intercepts `gh issue create` commands to scan issue bodies for secrets before they're published to GitHub.

## How It Works

When you run `gh issue create --body "..."`, the wrapper:

1. Extracts the issue body from the command arguments
2. Sends it to the IssueGuard API (`localhost:8000/detect`) for analysis
3. If **no secrets** are found → proceeds normally
4. If **secrets are found** → displays them and asks for confirmation
5. If the API is **unreachable** → warns and proceeds (fail-open)

## Supported `gh issue create` Variants

| Variant | Behavior |
|---|---|
| `--body` / `-b` | ✅ Body extracted and scanned |
| `--body-file` / `-F` | ✅ File contents read and scanned |
| `-F -` (stdin) | ✅ Stdin read and scanned |
| `--editor` / `-e` | ✅ Body extracted and scanned |
| Interactive mode | ✅ Body extracted and scanned |
| `--web` / `-w` | ⏭ Passed through (browser extension mode) |

All other `gh` commands (e.g., `gh pr create`, `gh repo view`) pass through unchanged.

## Prerequisites

- **Python 3.6+** (no third-party dependencies)
- **GitHub CLI (`gh`)** installed and on PATH
- **IssueGuard API** running on `localhost:8000` (or configure via env var)

## Installation

### macOS / Linux

```bash
cd cli-tool
chmod +x setup.sh
./setup.sh
source ~/.bashrc   # or ~/.zshrc
```

### Windows (PowerShell)

```powershell
cd cli-tool
.\setup.ps1
. $PROFILE.CurrentUserAllHosts
```

### Manual (any platform)

You can run the wrapper directly without installing an alias:

```bash
python3 issueguard.py issue create --title "Bug" --body "text with secrets"
```

## Configuration

| Environment Variable | Default | Description |
|---|---|---|
| `ISSUEGUARD_API_URL` | `http://localhost:8000/detect` | API endpoint URL |
| `ISSUEGUARD_TIMEOUT` | `30` | Request timeout in seconds |

## Examples

```bash
# Normal usage – scanned automatically
gh issue create --title "Bug report" --body "Error with API key AKIAIOSFODNN7EXAMPLE"

# Body from file
gh issue create -t "Config issue" -F ./body.md

# Body from stdin
echo "Some issue text" | gh issue create -t "Title" -F -

# Web mode – skipped
gh issue create --web

# All other gh commands – passed through
gh pr list
gh repo view
```

## Uninstall

### macOS / Linux

Remove the `# >>> IssueGuard CLI wrapper >>>` block from `~/.bashrc` (or `~/.zshrc`).

### Windows

Remove the `# >>> IssueGuard CLI wrapper >>>` block from your PowerShell profile (`$PROFILE.CurrentUserAllHosts`).
