#!/usr/bin/env python3
import getpass
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


APP_NAME = "jira-attachments"
PROJECT_DIR = Path(__file__).resolve().parent
MCP_SERVER = PROJECT_DIR / "mcp_server.py"
DEFAULT_SITE = "https://vmockinc.atlassian.net"
DEFAULT_OUTPUT_ROOT = "~/Agents/Jira"
ENV_FILE = Path.home() / ".jira-agent-mcp.env"


def prompt(default: str | None, label: str, secret: bool = False) -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        if secret:
            value = getpass.getpass(f"{label}{suffix}: ").strip()
        else:
            value = input(f"{label}{suffix}: ").strip()
        if value:
            return value
        if default is not None:
            return default


def read_existing_env() -> dict[str, str]:
    if not ENV_FILE.exists():
        return {}

    values: dict[str, str] = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def quote_env(value: str) -> str:
    return json.dumps(value)


def write_env(email: str, token: str, site: str, output_root: str) -> None:
    contents = "\n".join(
        [
            "# Created by jira-attachment-downloader/init.py",
            "# Keep this file private. It contains an Atlassian API token.",
            f"ATLASSIAN_EMAIL={quote_env(email)}",
            f"ATLASSIAN_API_TOKEN={quote_env(token)}",
            f"JIRA_DEFAULT_SITE={quote_env(site)}",
            f"JIRA_ATTACHMENT_OUTPUT_ROOT={quote_env(output_root)}",
            "",
        ]
    )
    ENV_FILE.write_text(contents, encoding="utf-8")
    os.chmod(ENV_FILE, 0o600)


def mcp_config() -> dict[str, Any]:
    return {
        "command": sys.executable,
        "args": [str(MCP_SERVER)],
        "env": {
            "JIRA_AGENT_MCP_ENV": str(ENV_FILE),
        },
    }


def backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    backup_path = path.with_name(f"{path.name}.bak-{stamp}")
    shutil.copy2(path, backup_path)
    return backup_path


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup(path)
    path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def install_json_mcp(path: Path) -> None:
    data = read_json(path)
    servers = data.setdefault("mcpServers", {})
    servers[APP_NAME] = mcp_config()
    write_json(path, data)


def toml_string(value: str) -> str:
    return json.dumps(value)


def toml_array(values: list[str]) -> str:
    return "[" + ", ".join(toml_string(value) for value in values) + "]"


def install_codex(path: Path) -> None:
    block = "\n".join(
        [
            f'[mcp_servers."{APP_NAME}"]',
            f"command = {toml_string(sys.executable)}",
            f"args = {toml_array([str(MCP_SERVER)])}",
            "enabled = true",
            "",
            f'[mcp_servers."{APP_NAME}".env]',
            f"JIRA_AGENT_MCP_ENV = {toml_string(str(ENV_FILE))}",
            "",
        ]
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    backup(path)

    start = existing.find(f'[mcp_servers."{APP_NAME}"]')
    if start == -1:
        updated = existing.rstrip() + "\n\n" + block
    else:
        next_section = existing.find("\n[mcp_servers.", start + 1)
        if next_section == -1:
            updated = existing[:start].rstrip() + "\n\n" + block
        else:
            updated = existing[:start].rstrip() + "\n\n" + block + existing[next_section:]

    path.write_text(updated, encoding="utf-8")
    os.chmod(path, 0o600)


def install_claude_code() -> None:
    command = shutil.which("claude")
    if not command:
        raise RuntimeError("claude CLI was not found on PATH.")

    payload = json.dumps(mcp_config())
    subprocess.run(
        [command, "mcp", "add-json", APP_NAME, payload, "--scope", "user"],
        check=True,
    )


def detected_apps() -> list[dict[str, Any]]:
    return [
        {
            "id": "codex",
            "label": "Codex",
            "path": Path.home() / ".codex" / "config.toml",
            "install": lambda: install_codex(Path.home() / ".codex" / "config.toml"),
        },
        {
            "id": "cursor",
            "label": "Cursor",
            "path": Path.home() / ".cursor" / "mcp.json",
            "install": lambda: install_json_mcp(Path.home() / ".cursor" / "mcp.json"),
        },
        {
            "id": "claude-desktop",
            "label": "Claude Desktop",
            "path": Path.home()
            / "Library"
            / "Application Support"
            / "Claude"
            / "claude_desktop_config.json",
            "install": lambda: install_json_mcp(
                Path.home()
                / "Library"
                / "Application Support"
                / "Claude"
                / "claude_desktop_config.json"
            ),
        },
        {
            "id": "claude-code",
            "label": "Claude Code",
            "path": shutil.which("claude") or "claude CLI not found",
            "install": install_claude_code,
        },
    ]


def choose_apps(apps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    print("\nInstall MCP into which apps?")
    for index, app in enumerate(apps, start=1):
        exists = Path(app["path"]).exists() if isinstance(app["path"], Path) else bool(shutil.which("claude"))
        status = "detected" if exists else "will create / use CLI if available"
        print(f"  {index}. {app['label']} ({status})")
    print("  a. All detected")
    print("  n. None")

    value = input("Selection [a]: ").strip().lower() or "a"
    if value == "n":
        return []

    if value == "a":
        selected = []
        for app in apps:
            path = app["path"]
            if app["id"] == "claude-code":
                if shutil.which("claude"):
                    selected.append(app)
            elif isinstance(path, Path) and path.parent.exists():
                selected.append(app)
        return selected

    selected = []
    for part in value.replace(",", " ").split():
        try:
            selected.append(apps[int(part) - 1])
        except (ValueError, IndexError):
            raise RuntimeError(f"Invalid selection: {part}")
    return selected


def main() -> int:
    existing = read_existing_env()
    print("Jira Attachment MCP init")
    print(f"Project: {PROJECT_DIR}")
    print(f"Credentials file: {ENV_FILE}")

    email = prompt(existing.get("ATLASSIAN_EMAIL"), "Atlassian email")
    token_default = "keep existing token" if existing.get("ATLASSIAN_API_TOKEN") else None
    token = prompt(token_default, "Atlassian API token", secret=True)
    if token == "keep existing token":
        token = existing["ATLASSIAN_API_TOKEN"]
    site = prompt(existing.get("JIRA_DEFAULT_SITE", DEFAULT_SITE), "Default Jira site")
    output_root = prompt(
        existing.get("JIRA_ATTACHMENT_OUTPUT_ROOT", DEFAULT_OUTPUT_ROOT),
        "Attachment output root",
    )

    write_env(email, token, site, output_root)
    print(f"\nWrote credentials to {ENV_FILE} with mode 600.")

    apps = detected_apps()
    selected = choose_apps(apps)
    if not selected:
        print("Skipped MCP config installation.")
        return 0

    print("")
    for app in selected:
        try:
            app["install"]()
            print(f"Installed MCP for {app['label']}.")
        except Exception as error:
            print(f"Failed to install MCP for {app['label']}: {error}", file=sys.stderr)

    print("\nDone. Restart the selected apps so they reload MCP configuration.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
