#!/usr/bin/env python3
"""
IssueGuard CLI Wrapper for `gh issue create`

Intercepts `gh issue create` commands to scan the issue body for secrets
before the issue is actually created on GitHub.

Usage:
    Replace `gh` with this wrapper (via alias or PATH), or call directly:
        python issueguard.py issue create --title "Bug" --body "my secret text"

Supported modes:
    - --body / -b: body provided inline
    - --body-file / -F: body read from a file (or stdin with "-")
    - --web / -w: opens browser, passed through without scanning
    - --editor / -e: editor mode, passed through with a warning
    - Interactive mode: passed through with a warning
"""

import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

ISSUEGUARD_API_URL = os.environ.get("ISSUEGUARD_API_URL", "http://localhost:8000/detect")
ISSUEGUARD_TIMEOUT = int(os.environ.get("ISSUEGUARD_TIMEOUT", "30"))

# ANSI color helpers (auto-disabled on Windows without VT support)
_COLOR_SUPPORTED = None


def _supports_color():
    global _COLOR_SUPPORTED
    if _COLOR_SUPPORTED is not None:
        return _COLOR_SUPPORTED

    if os.environ.get("NO_COLOR"):
        _COLOR_SUPPORTED = False
        return False

    if not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
        _COLOR_SUPPORTED = False
        return False

    if platform.system() == "Windows":
        # Enable VT processing on Windows 10+
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            # STD_OUTPUT_HANDLE = -11
            handle = kernel32.GetStdHandle(-11)
            mode = ctypes.c_ulong()
            kernel32.GetConsoleMode(handle, ctypes.byref(mode))
            # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
            _COLOR_SUPPORTED = True
        except Exception:
            _COLOR_SUPPORTED = False
    else:
        _COLOR_SUPPORTED = True

    return _COLOR_SUPPORTED


def _c(code, text):
    if _supports_color():
        return f"\033[{code}m{text}\033[0m"
    return text


def red(t):
    return _c("31", t)


def green(t):
    return _c("32", t)


def yellow(t):
    return _c("33", t)


def bold(t):
    return _c("1", t)


def cyan(t):
    return _c("36", t)


def dim(t):
    return _c("2", t)


# ── Argument parsing ────────────────────────────────────────────────────────


def find_gh_executable():
    """Find the real `gh` executable, skipping this wrapper if aliased as `gh`."""
    gh = shutil.which("gh")
    if gh is None:
        print(red("Error: `gh` (GitHub CLI) not found on PATH."))
        sys.exit(1)
    return gh


def is_issue_create(args):
    """Check whether the command is `gh issue create`."""
    positional = [str(a) for a in args if not str(a).startswith("-")]
    return len(positional) >= 2 and positional[0] == "issue" and positional[1] == "create"


def is_issue_edit(args):
    """Check whether the command is `gh issue edit`."""
    positional = [str(a) for a in args if not str(a).startswith("-")]
    return len(positional) >= 2 and positional[0] == "issue" and positional[1] == "edit"


def is_issue_comment(args):
    """Check whether the command is `gh issue comment`."""
    positional = [str(a) for a in args if not str(a).startswith("-")]
    return len(positional) >= 2 and positional[0] == "issue" and positional[1] == "comment"


def extract_body(args):
    """
    Parse the argument list to extract the issue body text.

    Returns:
        (body_text, mode)
        mode is one of: "inline", "file", "stdin", "web", "editor", "interactive"
    """
    i = 0
    body = None
    mode = "interactive"  # default

    while i < len(args):
        arg = args[i]

        # --web / -w  →  browser mode, no body to check
        if arg in ("--web", "-w"):
            return None, "web"

        # --editor / -e  →  editor mode
        if arg in ("--editor", "-e"):
            return None, "editor"

        # --body <text> or -b <text>
        if arg in ("--body", "-b"):
            if i + 1 < len(args):
                body = args[i + 1]
                mode = "inline"
                i += 2
                continue
            else:
                # Missing value – let gh report the error
                return None, "interactive"

        # --body=<text> or -b=<text>  (equals form)
        if arg.startswith("--body="):
            body = arg[len("--body="):]
            mode = "inline"
            i += 1
            continue
        if arg.startswith("-b="):
            body = arg[len("-b="):]
            mode = "inline"
            i += 1
            continue

        # --body-file <file> or -F <file>
        if arg in ("--body-file", "-F"):
            if i + 1 < len(args):
                file_path = args[i + 1]
                if file_path == "-":
                    # Read from stdin
                    body = sys.stdin.read()
                    mode = "stdin"
                else:
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            body = f.read()
                    except OSError as e:
                        print(red(f"Error reading body file: {e}"))
                        sys.exit(1)
                    mode = "file"
                i += 2
                continue
            else:
                return None, "interactive"

        # --body-file=<file> or -F=<file>
        if arg.startswith("--body-file="):
            file_path = arg[len("--body-file="):]
            if file_path == "-":
                body = sys.stdin.read()
                mode = "stdin"
            else:
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        body = f.read()
                except OSError as e:
                    print(red(f"Error reading body file: {e}"))
                    sys.exit(1)
                mode = "file"
            i += 1
            continue
        if arg.startswith("-F="):
            file_path = arg[len("-F="):]
            if file_path == "-":
                body = sys.stdin.read()
                mode = "stdin"
            else:
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        body = f.read()
                except OSError as e:
                    print(red(f"Error reading body file: {e}"))
                    sys.exit(1)
                mode = "file"
            i += 1
            continue

        # Compound short flags (e.g., -webF) – rare but possible
        # For simplicity, treat them as unknown and skip
        i += 1

    return body, mode


def extract_edit_body(args):
    """
    Parse args for `gh issue edit` to extract the body.

    Returns:
        (body_text, mode)
        mode is one of: "inline", "file", "stdin", "interactive"
    """
    i = 0
    body = None
    mode = "interactive"  # default when no --body flag present

    while i < len(args):
        arg = args[i]

        # --body <text> or -b <text>
        if arg in ("--body", "-b"):
            if i + 1 < len(args):
                body = args[i + 1]
                mode = "inline"
                i += 2
                continue
            else:
                return None, "interactive"

        if arg.startswith("--body="):
            body = arg[len("--body="):]
            mode = "inline"
            i += 1
            continue
        if arg.startswith("-b="):
            body = arg[len("-b="):]
            mode = "inline"
            i += 1
            continue

        # --body-file <file> or -F <file>
        if arg in ("--body-file", "-F"):
            if i + 1 < len(args):
                file_path = args[i + 1]
                if file_path == "-":
                    body = sys.stdin.read()
                    mode = "stdin"
                else:
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            body = f.read()
                    except OSError as e:
                        print(red(f"Error reading body file: {e}"))
                        sys.exit(1)
                    mode = "file"
                i += 2
                continue
            else:
                return None, "interactive"

        if arg.startswith("--body-file="):
            file_path = arg[len("--body-file="):]
            if file_path == "-":
                body = sys.stdin.read()
                mode = "stdin"
            else:
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        body = f.read()
                except OSError as e:
                    print(red(f"Error reading body file: {e}"))
                    sys.exit(1)
                mode = "file"
            i += 1
            continue
        if arg.startswith("-F="):
            file_path = arg[len("-F="):]
            if file_path == "-":
                body = sys.stdin.read()
                mode = "stdin"
            else:
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        body = f.read()
                except OSError as e:
                    print(red(f"Error reading body file: {e}"))
                    sys.exit(1)
                mode = "file"
            i += 1
            continue

        i += 1

    return body, mode


def rebuild_edit_args(remaining, body=None):
    """
    Rebuild gh args for `issue edit`, injecting --body and stripping old body flags.
    """
    result = ["issue", "edit"]
    i = 0
    while i < len(remaining):
        arg = remaining[i]

        # Drop old --body / -b
        if body is not None and arg in ("--body", "-b"):
            i += 2
            continue
        if body is not None and (arg.startswith("--body=") or arg.startswith("-b=")):
            i += 1
            continue

        # Drop old --body-file / -F
        if body is not None and arg in ("--body-file", "-F"):
            i += 2
            continue
        if body is not None and (arg.startswith("--body-file=") or arg.startswith("-F=")):
            i += 1
            continue

        result.append(arg)
        i += 1

    if body is not None:
        result.extend(["--body", body])

    return result


def extract_title(args):
    """Extract --title / -t value from args, if present."""
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ("--title", "-t") and i + 1 < len(args):
            return args[i + 1]
        if arg.startswith("--title="):
            return arg[len("--title="):]
        if arg.startswith("-t="):
            return arg[len("-t="):]
        i += 1
    return None


def get_editor():
    """Get the user's preferred text editor."""
    editor = (
        os.environ.get("GH_EDITOR")
        or os.environ.get("VISUAL")
        or os.environ.get("EDITOR")
    )
    if editor:
        return editor
    if platform.system() == "Windows":
        return "notepad"
    for ed in ("nano", "vi", "vim"):
        if shutil.which(ed):
            return ed
    return "vi"


_EDITOR_SEPARATOR = "------------------------ >8 ------------------------"
_EDITOR_HELP = (
    "Please enter the title on the first line and the body on subsequent lines.\n"
    "Lines below the dotted line will be ignored, and an empty title aborts "
    "the creation process."
)


def collect_via_editor(existing_title=None):
    """
    Open an editor for the user to compose title and body (like gh --editor).
    Returns (title, body).  Returns (None, None) if aborted.
    """
    editor = get_editor()

    template_lines = [
        existing_title or "",
        "",
        "",
        _EDITOR_SEPARATOR,
        _EDITOR_HELP,
    ]

    fd, tmppath = tempfile.mkstemp(suffix=".md", prefix="issueguard_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(template_lines))

        cmd = editor.split() + [tmppath]
        proc = subprocess.run(cmd)
        if proc.returncode != 0:
            print(red("[IssueGuard] Editor exited with an error."))
            return None, None

        with open(tmppath, "r", encoding="utf-8") as f:
            content = f.read()
    finally:
        try:
            os.unlink(tmppath)
        except OSError:
            pass

    # Strip everything after the separator
    if _EDITOR_SEPARATOR in content:
        content = content[: content.index(_EDITOR_SEPARATOR)]

    lines = content.split("\n")
    title = lines[0].strip() if lines else ""
    body = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""

    if not title:
        print(yellow("[IssueGuard] Empty title — aborting issue creation."))
        return None, None

    return title, body


def open_editor_for_body():
    """Open an editor for body-only composition.  Returns body text."""
    editor = get_editor()

    fd, tmppath = tempfile.mkstemp(suffix=".md", prefix="issueguard_body_")
    try:
        os.close(fd)  # empty file
        subprocess.run(editor.split() + [tmppath])
        with open(tmppath, "r", encoding="utf-8") as f:
            return f.read().strip()
    finally:
        try:
            os.unlink(tmppath)
        except OSError:
            pass


def collect_title_interactively():
    """Prompt the user for the issue title."""
    while True:
        try:
            title = input(bold("? Title (required): ")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            print(red("[IssueGuard] Issue creation aborted."))
            sys.exit(2)
        if title:
            return title
        print(yellow("  Title cannot be empty."))


def collect_body_interactively():
    """Open an editor for the user to compose the issue body."""
    print(dim("[IssueGuard] Opening editor for issue body..."))
    return open_editor_for_body()


def rebuild_args(remaining, title=None, body=None):
    """
    Rebuild full gh args from *remaining* (flags without 'issue'/'create'),
    injecting --title/--body and removing --editor/-e.
    """
    result = ["issue", "create"]
    i = 0
    while i < len(remaining):
        arg = remaining[i]

        # Drop --editor / -e
        if arg in ("--editor", "-e"):
            i += 1
            continue

        # Drop old --body / -b  (flag + value)
        if body is not None and arg in ("--body", "-b"):
            i += 2
            continue
        if body is not None and (arg.startswith("--body=") or arg.startswith("-b=")):
            i += 1
            continue

        # Drop old --body-file / -F
        if body is not None and arg in ("--body-file", "-F"):
            i += 2
            continue
        if body is not None and (arg.startswith("--body-file=") or arg.startswith("-F=")):
            i += 1
            continue

        # Drop old --title / -t
        if title is not None and arg in ("--title", "-t"):
            i += 2
            continue
        if title is not None and (arg.startswith("--title=") or arg.startswith("-t=")):
            i += 1
            continue

        result.append(arg)
        i += 1

    if title is not None:
        result.extend(["--title", title])
    if body is not None:
        result.extend(["--body", body])

    return result


# ── Secret scanning ─────────────────────────────────────────────────────────


def check_for_secrets(text):
    """Send text to the IssueGuard API and return the parsed response."""
    if not text or not text.strip():
        return {"success": True, "secrets_detected": 0, "all_candidates": []}

    payload = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(
        ISSUEGUARD_API_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=ISSUEGUARD_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"success": False, "error": f"HTTP {e.code}: {body}"}
    except urllib.error.URLError as e:
        return {"success": False, "error": f"Connection failed: {e.reason}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Display ──────────────────────────────────────────────────────────────────


def display_secrets(result):
    """Pretty-print detected secrets."""
    candidates = result.get("all_candidates", [])
    secrets = [c for c in candidates if c.get("is_secret")]

    # Deduplicate: remove secrets that are substrings of longer secrets
    secrets = [
        s for i, s in enumerate(secrets)
        if not any(
            s["candidate_string"] != o["candidate_string"]
            and s["candidate_string"] in o["candidate_string"]
            for j, o in enumerate(secrets) if i != j
        )
    ]

    if not secrets:
        return

    print()
    print(bold(red("  ⚠  IssueGuard: Potential secrets detected!")))
    print(dim("  " + "─" * 52))
    print()

    for idx, s in enumerate(secrets, 1):
        secret_str = s.get("candidate_string", "")
        secret_type = s.get("secret_type", "unknown")
        # Truncate long strings for display
        display_str = secret_str if len(secret_str) <= 80 else secret_str[:77] + "..."
        print(f"  {bold(red(f'[{idx}]'))} {cyan(secret_type)}")
        print(f"      {yellow(display_str)}")
        print()

    print(dim("  " + "─" * 52))
    total = len(secrets)
    print(f"  {bold(f'{total} secret(s)')} flagged in the issue body.")
    print()


def prompt_user():
    """Ask the user whether to proceed. Returns True if yes."""
    try:
        answer = input(bold("  Are you sure you want to proceed? (y/N): ")).strip().lower()
        return answer == "y"
    except (EOFError, KeyboardInterrupt):
        print()
        return False


# ── Main ─────────────────────────────────────────────────────────────────────


def run_gh(gh, args):
    """Execute the real `gh` with the given arguments, returning its exit code."""
    result = subprocess.run([gh] + args)
    return result.returncode


def scan_and_confirm(body, gh, forward_args):
    """Scan body for secrets.  If found, prompt.  Then run gh or abort."""
    print(dim("[IssueGuard] Scanning issue body for secrets..."))

    result = check_for_secrets(body)

    if not result.get("success", False):
        error = result.get("error", "Unknown error")
        print(yellow(f"[IssueGuard] Warning: Could not reach the scanning server: {error}"))
        print(yellow("             Proceeding without scanning."))
        sys.exit(run_gh(gh, forward_args))

    if result.get("secrets_detected", 0) == 0:
        print(green("[IssueGuard] ✓ No secrets detected. Proceeding."))
        sys.exit(run_gh(gh, forward_args))

    # Secrets found – display and prompt
    display_secrets(result)

    if prompt_user():
        print()
        print(dim("[IssueGuard] Proceeding with issue creation..."))
        sys.exit(run_gh(gh, forward_args))
    else:
        print()
        print(red("[IssueGuard] Operation cancelled."))
        sys.exit(2)  # Exit code 2 = cancelled (matches gh convention)


def strip_subcommands(all_args, subcmds):
    """Strip the first occurrence of each subcommand word from args."""
    remaining = []
    to_strip = list(subcmds)
    for a in all_args:
        if to_strip and a == to_strip[0]:
            to_strip.pop(0)
            continue
        remaining.append(a)
    return remaining


def handle_issue_create(gh, all_args):
    remaining = strip_subcommands(all_args, ["issue", "create"])

    body, mode = extract_body(remaining)
    title = extract_title(remaining)

    # Web mode: pass through
    if mode == "web":
        print(dim("[IssueGuard] --web mode: opening browser, skipping secret scan."))
        sys.exit(run_gh(gh, all_args))

    # Editor mode: open editor, scan, then forward
    if mode == "editor":
        ed_title, ed_body = collect_via_editor(existing_title=title)
        if ed_title is None:
            print(red("[IssueGuard] Issue creation aborted."))
            sys.exit(2)
        forward = rebuild_args(remaining, title=ed_title, body=ed_body or "")
        if ed_body and ed_body.strip():
            scan_and_confirm(ed_body, gh, forward)
        else:
            sys.exit(run_gh(gh, forward))

    # Interactive mode: collect title/body, scan
    if mode == "interactive":
        if title is None:
            title = collect_title_interactively()
        body = collect_body_interactively()
        forward = rebuild_args(remaining, title=title, body=body)
        if body and body.strip():
            scan_and_confirm(body, gh, forward)
        else:
            sys.exit(run_gh(gh, forward))

    # Inline / file / stdin: body already extracted
    if not body or not body.strip():
        sys.exit(run_gh(gh, all_args))

    scan_and_confirm(body, gh, all_args)


def handle_issue_edit(gh, all_args):
    remaining = strip_subcommands(all_args, ["issue", "edit"])

    body, mode = extract_edit_body(remaining)

    # Interactive mode: open editor for body, scan, then forward
    if mode == "interactive":
        print(dim("[IssueGuard] Opening editor for issue body..."))
        body = open_editor_for_body()
        forward = rebuild_edit_args(remaining, body=body)
        if body and body.strip():
            scan_and_confirm(body, gh, forward)
        else:
            sys.exit(run_gh(gh, forward))

    # Inline / file / stdin: body already extracted
    if not body or not body.strip():
        sys.exit(run_gh(gh, all_args))

    scan_and_confirm(body, gh, all_args)


def rebuild_comment_args(remaining, body=None):
    """
    Rebuild gh args for `issue comment`, injecting --body and stripping old body flags.
    """
    result = ["issue", "comment"]
    i = 0
    while i < len(remaining):
        arg = remaining[i]

        if body is not None and arg in ("--body", "-b"):
            i += 2
            continue
        if body is not None and (arg.startswith("--body=") or arg.startswith("-b=")):
            i += 1
            continue
        if body is not None and arg in ("--body-file", "-F"):
            i += 2
            continue
        if body is not None and (arg.startswith("--body-file=") or arg.startswith("-F=")):
            i += 1
            continue

        result.append(arg)
        i += 1

    if body is not None:
        result.extend(["--body", body])

    return result


def handle_issue_comment(gh, all_args):
    remaining = strip_subcommands(all_args, ["issue", "comment"])

    body, mode = extract_edit_body(remaining)

    # Interactive mode: open editor for comment body, scan, then forward
    if mode == "interactive":
        print(dim("[IssueGuard] Opening editor for comment..."))
        body = open_editor_for_body()
        forward = rebuild_comment_args(remaining, body=body)
        if body and body.strip():
            scan_and_confirm(body, gh, forward)
        else:
            sys.exit(run_gh(gh, forward))

    # Inline / file / stdin: body already extracted
    if not body or not body.strip():
        sys.exit(run_gh(gh, all_args))

    scan_and_confirm(body, gh, all_args)


def main():
    all_args = sys.argv[1:]

    gh = find_gh_executable()

    if is_issue_create(all_args):
        handle_issue_create(gh, all_args)
    elif is_issue_edit(all_args):
        handle_issue_edit(gh, all_args)
    elif is_issue_comment(all_args):
        handle_issue_comment(gh, all_args)
    else:
        # Not an intercepted command — pass through
        sys.exit(run_gh(gh, all_args))


if __name__ == "__main__":
    main()
