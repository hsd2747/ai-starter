"""PreToolUse guard for Claude Code (.claude/settings.json).

AGENTS.md is context, not enforcement. This hook blocks the few actions that
cannot be undone or that leak secrets, regardless of what the model decided.
It reduces accidents; it is not a security boundary, and a command built to
evade it can still get through. Exit code 2 blocks the call and shows the
reason to the model. Anything the guard cannot parse is allowed: a broken hook
must not freeze the session.

Commands are tokenized with shell quoting, so text inside a commit message or
a heredoc that writes a file is data, not a command.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import shlex
import sys

from .secrets import is_env_file

FILE_TOOLS = {"Read", "Edit", "Write", "MultiEdit", "NotebookEdit"}
VIEWERS = {"cat", "less", "more", "head", "tail", "bat", "nl", "tac", "strings", "xxd", "od", "sed", "awk", "sort", "uniq",
           "base64", "hexdump", "diff", "cmp", "jq", "yq"}
SEARCHERS = {"grep", "egrep", "fgrep", "rg"}
QUIET_SEARCH_FLAGS = {"-q", "--quiet", "-c", "--count", "-l", "--files-with-matches", "-L", "--files-without-match"}
COPIERS = {"cp", "mv", "rsync", "scp"}
INTERPRETERS = {"python", "python3", "node", "ruby", "perl", "php", "deno", "bun"}
INLINE_CODE_FLAGS = {"-c", "-e", "-E", "-p", "-r", "--eval", "--print"}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
WRAPPERS = {"sudo", "doas", "nice", "nohup", "time", "command", "builtin", "exec", "xargs"}
WRAPPER_VALUE_OPTIONS = {"-u", "-g", "-n", "-p", "-I", "-P", "-L", "-s"}
GIT_GLOBAL_VALUE_OPTIONS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--super-prefix", "--config-env"}
GIT_CONTENT_READERS = {"show", "diff", "log", "cat-file", "blame", "annotate", "grep"}
GIT_SUMMARY_OPTIONS = {"--stat", "--shortstat", "--numstat", "--name-only", "--name-status", "--no-patch", "--quiet"}
GIT_PATCH_OPTIONS = {"--patch", "--patch-with-stat", "--patch-with-raw"}
GIT_PUSH_DELETE_OPTIONS = {"--delete", "--mirror", "--prune"}
# Short options of `git commit` whose value may follow in the same token or the next one, so a later "n" is not --no-verify.
GIT_COMMIT_VALUE_FLAGS = set("mFCct")

BROAD_TARGETS = {"/", "/*", "~", "~/", "~/*", "$HOME", "$HOME/", "$HOME/*", ".", "./", "./*", "..", "../", "../*", "*", ".*"}
FIND_NARROWING = {"-name", "-iname", "-path", "-ipath", "-wholename", "-iwholename", "-regex", "-iregex"}

SECRET_NAME_PARTS = {"KEY", "APIKEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD", "PASS", "CREDENTIAL", "CREDENTIALS", "PRIVATE", "DSN"}
CONNECTION_PARTS = {"URL", "URI"}
DATABASE_PARTS = {"DATABASE", "DB", "REDIS", "MONGO", "MONGODB", "POSTGRES", "MYSQL", "AMQP"}
_VAR_REF = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)")
_ENV_REF = re.compile(r"[\w./-]*\.env[\w.-]*")
# Shell globs skip dotfiles unless the pattern itself starts with a dot, so only such patterns can reach an env file.
_ENV_SAMPLES = (".env", ".env.local", ".env.development", ".env.production")

_SEPARATOR = re.compile(r"[;&|()\n]+\Z")
_FALLBACK_SPLIT = re.compile(r"\|\||&&|[;|&\n]")
_HEREDOC = re.compile(r"(?<!<)<<(-?)[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")
_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
MAX_DEPTH = 4


def _split_heredocs(command: str) -> tuple[str, list[str]]:
    """The command without heredoc bodies, and the bodies in order of appearance."""
    bodies: list[str] = []
    text, pos = command, 0
    while True:
        match = _HEREDOC.search(text, pos)
        if not match:
            return text, bodies
        line_end = text.find("\n", match.end())
        if line_end == -1:
            return text, bodies
        start = cursor = line_end + 1
        body_end = resume = len(text)
        while cursor <= len(text):
            newline = text.find("\n", cursor)
            line = text[cursor:newline if newline != -1 else len(text)]
            if (line.lstrip("\t") if match.group(1) else line) == match.group(3):
                body_end, resume = cursor, (newline + 1 if newline != -1 else len(text))
                break
            if newline == -1:
                break
            cursor = newline + 1
        bodies.append(text[start:body_end])
        text = text[:start] + text[resume:]
        pos = match.end()


def _segments(command: str) -> list[list[str]]:
    try:
        lexer = shlex.shlex(command.replace("`", "\n"), posix=True, punctuation_chars=";&|()<>\n")
        lexer.whitespace = " \t\r"
        lexer.whitespace_split = True
        lexer.commenters = ""
        tokens = list(lexer)
    except ValueError:
        return [part.split() for part in _FALLBACK_SPLIT.split(command)]
    segments: list[list[str]] = [[]]
    for token in tokens:
        if _SEPARATOR.match(token):
            segments.append([])
        else:
            segments[-1].append(token)
    return [segment for segment in segments if segment]


def _unwrap(tokens: list[str]) -> list[str]:
    """Drops leading assignments and wrappers such as sudo, so the real program comes first."""
    i = 0
    while i < len(tokens):
        name = os.path.basename(tokens[i])
        if _ASSIGNMENT.match(tokens[i]):
            i += 1
        elif name in WRAPPERS:
            i += 1
            while i < len(tokens) and tokens[i].startswith("-"):
                i += 2 if tokens[i] in WRAPPER_VALUE_OPTIONS else 1
        elif name == "env" and i + 1 < len(tokens):
            i += 1
            while i < len(tokens) and (tokens[i].startswith("-") or _ASSIGNMENT.match(tokens[i])):
                i += 1
        else:
            break
    return tokens[i:]


def _short_flags(args: list[str]) -> str:
    return "".join(a[1:] for a in args if a.startswith("-") and not a.startswith("--") and a != "-")


def _git_subcommand(args: list[str]) -> tuple[str | None, list[str]]:
    i = 0
    while i < len(args):
        if args[i] in GIT_GLOBAL_VALUE_OPTIONS:
            i += 2
        elif args[i].startswith("-"):
            i += 1
        else:
            return args[i], args[i + 1:]
    return None, []


def _git_reason(args: list[str]) -> str | None:
    sub, rest = _git_subcommand(args)
    flags = _short_flags(rest)
    if _overrides_hooks_path(args[:len(args) - len(rest)], sub, rest):
        return "changing core.hooksPath turns off the pre-commit verify hook (hooks-path)."
    if sub == "commit" and _skips_hooks(rest):
        return "git commit --no-verify skips the pre-commit verify hook (no-verify)."
    if sub == "push" and ("f" in flags or any(a.startswith("+") or a.split("=")[0] in ("--force", "--force-with-lease") for a in rest)):
        return "force push rewrites shared history (force-push)."
    if sub == "push" and ("d" in flags or any(a.split("=")[0] in GIT_PUSH_DELETE_OPTIONS or (a.startswith(":") and len(a) > 1)
                                              for a in rest)):
        return "this push deletes remote branches or tags (push-delete)."
    if _git_env_read(sub, rest):
        return "git would print env file contents from history or the index (env-read)."
    if sub == "reset" and "--hard" in rest:
        return "git reset --hard discards uncommitted work (reset-hard)."
    if sub == "clean" and ("f" in flags or "--force" in rest):
        return "git clean deletes untracked files (clean)."
    if sub == "checkout" and ("--" in rest or "." in rest or "f" in flags or "--force" in rest):
        return "git checkout with paths or --force discards changes (checkout-discard)."
    if sub == "switch" and ("f" in flags or "--force" in rest or "--discard-changes" in rest):
        return "git switch --discard-changes or --force discards changes (switch-discard)."
    if sub == "restore":
        staged_only = ("--staged" in rest or "S" in flags) and not ("--worktree" in rest or "W" in flags)
        if not staged_only:
            return "git restore on the worktree discards changes (restore)."
    if sub == "branch":
        deleting = "--delete" in rest or "d" in flags
        if "D" in flags or (deleting and ("--force" in rest or "f" in flags)):
            return "force-deleting a branch can lose unmerged commits (branch-force-delete)."
    if sub == "stash" and rest[:1] in (["drop"], ["clear"]):
        return "dropping a stash loses its changes (stash-drop)."
    return None


def _skips_hooks(rest: list[str]) -> bool:
    value_next = False
    for arg in rest:
        if value_next:
            value_next = False
            continue
        if arg == "--":
            return False
        if arg == "--no-verify":
            return True
        if arg.startswith("-") and not arg.startswith("--"):
            for i, letter in enumerate(arg[1:], start=1):
                if letter == "n":
                    return True
                if letter in GIT_COMMIT_VALUE_FLAGS:
                    value_next = i == len(arg) - 1
                    break
    return False


def _overrides_hooks_path(global_options: list[str], sub: str | None, rest: list[str]) -> bool:
    """`git -c core.hooksPath=...` for one command, or `git config` writing or removing it. Reading it stays allowed."""
    if any(option.lower().startswith("core.hookspath") for option in global_options):
        return True
    if sub != "config":
        return False
    words = [a for a in rest if not a.startswith("-")]
    keys = [i for i, word in enumerate(words) if word.lower() == "core.hookspath"]
    if not keys:
        return False
    writes = any(a.startswith(("--unset", "--add", "--replace-all", "--remove-section", "--rename-section")) for a in rest)
    return writes or words[0] in ("set", "unset") or len(words) > keys[0] + 1


def _git_env_read(sub: str | None, rest: list[str]) -> bool:
    """Env files reach git output through `<rev>:<path>` objects and pathspecs, even after they are deleted or ignored."""
    if sub not in GIT_CONTENT_READERS:
        return False
    if any(":" in a and _mentions_env(a.split(":", 1)[1]) for a in rest):
        return True
    if not any(_mentions_env(a) for a in rest):
        return False
    options = {a.split("=")[0] for a in rest}
    if sub == "log":
        # Listing the commits that touched an env file is how a leak is investigated; only patches print values.
        return bool(set(_short_flags(rest)) & set("pu") or options & GIT_PATCH_OPTIONS)
    if sub == "grep":
        return not _quiet_search(rest)
    if sub in ("diff", "show"):
        return not (options & GIT_SUMMARY_OPTIONS or (sub == "show" and "s" in _short_flags(rest)))
    return True


def _quiet_search(args: list[str]) -> bool:
    return any(a in QUIET_SEARCH_FLAGS or (a.startswith("-") and not a.startswith("--") and set(a[1:]) & set("qclL")) for a in args)


def _names_only_cut(args: list[str]) -> bool:
    return "-f1" in args or _after(args, "-f") == "1"


def _redirects_env(tokens: list[str]) -> bool:
    return any(token == "<" and i + 1 < len(tokens) and _mentions_env(tokens[i + 1]) for i, token in enumerate(tokens))


def _broad_rm(args: list[str]) -> bool:
    recursive = "r" in _short_flags(args).lower() or "--recursive" in args
    return recursive and any(a in BROAD_TARGETS for a in args if not a.startswith("-"))


def _broad_find(args: list[str]) -> bool:
    starts = []
    for arg in args:
        if arg.startswith("-") or arg == "!":
            break
        starts.append(arg)
    deletes = "-delete" in args or any(arg in ("-exec", "-execdir") and i + 1 < len(args) and os.path.basename(args[i + 1]) == "rm"
                                       for i, arg in enumerate(args))
    return deletes and any(s in BROAD_TARGETS for s in (starts or ["."])) and not FIND_NARROWING & set(args)


def _mentions_env(token: str) -> bool:
    clean = token.strip().strip("'\"")
    if is_env_file(clean):
        return True
    base = clean.rsplit("/", 1)[-1]
    return base.startswith(".") and bool(set(base) & set("*?[")) and any(fnmatch.fnmatchcase(s, base) for s in _ENV_SAMPLES)


def _refers_to_env(code: str) -> bool:
    return any(is_env_file(reference) for reference in _ENV_REF.findall(code))


def _secret_name(name: str) -> bool:
    parts = set(name.upper().split("_"))
    return bool(parts & SECRET_NAME_PARTS) or bool(parts & CONNECTION_PARTS and parts & DATABASE_PARTS)


def _after(args: list[str], flag: str) -> str | None:
    return args[args.index(flag) + 1] if flag in args and args.index(flag) + 1 < len(args) else None


def _env_leak(program: str, args: list[str], bodies: list[str]) -> bool:
    if program in ("env", "printenv", "set") and not args:
        return True
    if program == "printenv":
        return any(_secret_name(a) for a in args)
    if program in ("export", "declare", "typeset") and set(args) <= {"-p", "-x", "-px", "-xp"}:
        return True
    if program in ("echo", "printf"):
        return any(_secret_name(name) for arg in args for name in _VAR_REF.findall(arg))
    if program in INTERPRETERS:
        inline = [args[i + 1] for i, a in enumerate(args) if a in INLINE_CODE_FLAGS and i + 1 < len(args)]
        return any(_refers_to_env(code) for code in inline + bodies)
    if not any(_mentions_env(a) for a in args):
        return False
    if program in VIEWERS:
        return True
    if program in SEARCHERS:
        return not _quiet_search(args)
    if program == "cut":
        return not _names_only_cut(args)
    if program in COPIERS:
        operands = [a for a in args if not a.startswith("-")]
        return len(operands) >= 2 and any(_mentions_env(s) for s in operands[:-1]) and not _mentions_env(operands[-1])
    return False


def _segment_reason(tokens: list[str], bodies: list[str], depth: int) -> str | None:
    program, args = os.path.basename(tokens[0]), tokens[1:]
    if program in SHELLS:
        scripts = [args[args.index("-c") + 1]] if "-c" in args and args.index("-c") + 1 < len(args) else []
        for script in scripts + bodies:
            reason = command_reason(script, depth + 1)
            if reason:
                return reason
        return None
    if program == "eval":
        return command_reason(" ".join(args), depth + 1)
    if _redirects_env(tokens) and not ((program in SEARCHERS and _quiet_search(args)) or (program == "cut" and _names_only_cut(args))):
        return "input redirected from an env file can print its values (env-read)."
    if program == "git":
        return _git_reason(args)
    if program == "rm" and _broad_rm(args):
        return "recursive rm on a root, home, or current directory (broad-rm)."
    if program == "find" and _broad_find(args):
        return "find deleting from a root, home, or current directory without a name filter (broad-find)."
    if _env_leak(program, args, bodies):
        return "this would print or copy secret values from an env file or the environment (env-read)."
    return None


def command_reason(command: str, depth: int = 0) -> str | None:
    if depth > MAX_DEPTH:
        return None
    text, bodies = _split_heredocs(command)
    for segment in _segments(text):
        count = sum(1 for token in segment if token.startswith("<<") and not token.startswith("<<<"))
        own, bodies = bodies[:count], bodies[count:]
        tokens = _unwrap(segment)
        if tokens:
            reason = _segment_reason(tokens, own, depth)
            if reason:
                return reason
    return None


def evaluate(payload: dict) -> str | None:
    """Reason to block, or None to allow."""
    tool = payload.get("tool_name")
    arguments = payload.get("tool_input") or {}
    if tool in FILE_TOOLS:
        path = arguments.get("file_path") or arguments.get("notebook_path") or ""
        if is_env_file(path):
            return (f"{tool} on {os.path.basename(path)} would expose or overwrite secrets. Check key names with "
                    "`cut -d= -f1 <file>` or `grep -q KEY <file>` instead; the user edits values themselves.")
        return None
    if tool == "Grep":
        targets_env = _mentions_env(arguments.get("path") or "") or _mentions_env(arguments.get("glob") or "")
        if targets_env and arguments.get("output_mode") == "content":
            return "Grep with content output on an env file would print secret values (env-read)."
        return None
    if tool != "Bash":
        return None
    return command_reason(arguments.get("command", ""))


def main(stdin: str) -> int:
    try:
        payload = json.loads(stdin)
    except json.JSONDecodeError:
        return 0
    reason = evaluate(payload if isinstance(payload, dict) else {})
    if reason is None:
        return 0
    print(f"Blocked by the repository guard: {reason} If this is intended, show the user the exact command and "
          "the affected targets, and ask them to run it themselves with the `!` prefix.", file=sys.stderr)
    return 2
