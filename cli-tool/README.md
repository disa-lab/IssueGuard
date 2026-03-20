# IssueGuard CLI Tool

A cross-platform CLI wrapper that intercepts `gh issue create` and `glab issue create` commands to scan issue bodies for secrets before they're published to GitHub or GitLab.

## How It Works

When you run `gh issue create --body "..."` or `glab issue create -d "..."`, the wrapper:

1. Extracts the issue body/description from the command arguments
2. Sends it to the IssueGuard API (`localhost:8000/detect`) for analysis
3. If **no secrets** are found → proceeds normally
4. If **secrets are found** → displays them and asks for confirmation
5. If the API is **unreachable** → warns and proceeds (fail-open)

## Supported Variants

### GitHub (`gh`)

| Variant | Behavior |
|---|---|
| `--body` / `-b` | ✅ Body extracted and scanned |
| `--body-file` / `-F` | ✅ File contents read and scanned |
| `-F -` (stdin) | ✅ Stdin read and scanned |
| `--editor` / `-e` | ✅ Body extracted and scanned |
| Interactive mode | ✅ Body extracted and scanned |
| `--web` / `-w` | ⏭ Passed through (browser extension mode) |

Also intercepts `gh issue edit` and `gh issue comment`.

### GitLab (`glab`)

| Variant | Behavior |
|---|---|
| `--description` / `-d` | ✅ Description extracted and scanned |
| `-d -` (editor mode) | ✅ Editor opened, description scanned |
| Interactive mode | ✅ Title/description collected and scanned |
| `--web` / `-w` | ⏭ Passed through |

Also intercepts `glab issue update` and `glab issue note`.

All other `gh` / `glab` commands (e.g., `gh pr create`, `glab mr list`) pass through unchanged.

## Prerequisites

- **Python 3.6+** (no third-party dependencies)
- **GitHub CLI (`gh`)** and/or **GitLab CLI (`glab`)** installed and on PATH
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
# GitHub
python3 issueguard.py issue create --title "Bug" --body "text with secrets"

# GitLab
python3 issueguard.py --glab issue create --title "Bug" --description "text with secrets"
```

## Configuration

| Environment Variable | Default | Description |
|---|---|---|
| `ISSUEGUARD_API_URL` | `http://localhost:8000/detect` | API endpoint URL |
| `ISSUEGUARD_TIMEOUT` | `30` | Request timeout in seconds |

## Examples

### GitHub

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

### GitLab

```bash
# Inline description – scanned automatically
glab issue create -t "Bug report" -d "Error with API key AKIAIOSFODNN7EXAMPLE"

# Editor mode – opens editor, then scans
glab issue create -t "Title" -d -

# Interactive mode – collects title/description, scans before submitting
glab issue create

# All other glab commands – passed through
glab mr list
glab repo view
```

## Troubleshooting

### `glab` not found on PATH (Windows)

If `glab` is installed (e.g. via `winget`) but not recognized in your terminal, it may not be on PATH. Find and add it:

```powershell
# Locate the executable
Get-ChildItem -Path "C:\Program Files","C:\Program Files (x86)" -Recurse -Filter "glab.exe" -ErrorAction SilentlyContinue

# Add to user PATH permanently (adjust path if needed)
$glabDir = "C:\Program Files (x86)\glab"
[Environment]::SetEnvironmentVariable("PATH", "$([Environment]::GetEnvironmentVariable('PATH','User'));$glabDir", "User")

# Also add to current session
$env:PATH += ";$glabDir"
```

### Reinstalling / updating the wrapper

The setup script detects an existing IssueGuard block in your shell profile and refuses to overwrite it. If you need to reinstall (e.g. after adding glab support), remove the old block first:

**Windows (PowerShell):**

Open your profile (`notepad $PROFILE.CurrentUserAllHosts`) and delete everything between:
```
# >>> IssueGuard CLI wrapper >>>
...
# <<< IssueGuard CLI wrapper <<<
```

Then re-run `.\setup.ps1`.

**macOS / Linux:**

Edit your shell config (`~/.bashrc` or `~/.zshrc`) and remove the same block, then re-run `./setup.sh`.

### Wrapper points to old path

If you moved the IssueGuard folder, the profile still references the old `issueguard.py` path. Remove the old block and re-run setup from the new location.

## Uninstall

### macOS / Linux

Remove the `# >>> IssueGuard CLI wrapper >>>` block from `~/.bashrc` (or `~/.zshrc`).

### Windows

Remove the `# >>> IssueGuard CLI wrapper >>>` block from your PowerShell profile (`$PROFILE.CurrentUserAllHosts`).
