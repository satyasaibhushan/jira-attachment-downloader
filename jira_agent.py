from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


DEFAULT_OUTPUT_ROOT = "~/Agents/Jira"
DEFAULT_SITE = ""
DEFAULT_ENV_FILE = "~/.jira-agent-mcp.env"


class JiraAgentError(RuntimeError):
    pass


class JiraHttpError(JiraAgentError):
    def __init__(self, status: int, reason: str, body: str = ""):
        self.status = status
        self.reason = reason
        self.body = body
        detail = f"HTTP {status} {reason}"
        if body:
            detail = f"{detail}: {body}"
        super().__init__(detail)


def issue_permission_hint(issue_key: str) -> str:
    return (
        f"If {issue_key} exists in the browser, check that the API token belongs to "
        "the same Atlassian account and includes Jira scopes `read:issue:jira`, "
        "`read:project:jira`, and `read:attachment:jira`."
    )


def load_env_file(path: str | None = None) -> None:
    env_path = path or os.environ.get("JIRA_AGENT_MCP_ENV") or DEFAULT_ENV_FILE
    if not env_path:
        return

    file_path = Path(env_path).expanduser()
    if not file_path.exists():
        return

    for line in file_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def parse_ticket(value: str, fallback_site: str | None = None) -> tuple[str, str]:
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        match = re.search(r"/browse/([A-Z][A-Z0-9]+-\d+)", parsed.path, re.IGNORECASE)
        if not match:
            raise JiraAgentError(f"Could not find a Jira issue key in URL: {value}")
        return f"{parsed.scheme}://{parsed.netloc}", match.group(1).upper()

    if not re.fullmatch(r"[A-Z][A-Z0-9]+-\d+", value, re.IGNORECASE):
        raise JiraAgentError(f"Expected a Jira issue key or ticket URL, got: {value}")

    site = fallback_site or os.environ.get("JIRA_DEFAULT_SITE")
    if not site:
        raise JiraAgentError(
            "A Jira site is required when passing an issue key. "
            "Use --site, pass a full ticket URL, or run init.py."
        )

    return site.rstrip("/"), value.upper()


def auth_header() -> str:
    email = os.environ.get("ATLASSIAN_EMAIL")
    token = os.environ.get("ATLASSIAN_API_TOKEN")

    if not email or not token:
        raise JiraAgentError(
            "Missing auth. Set ATLASSIAN_EMAIL and ATLASSIAN_API_TOKEN, or run init.py."
        )

    encoded = base64.b64encode(f"{email}:{token}".encode("utf-8")).decode("ascii")
    return f"Basic {encoded}"


def bearer_auth_header() -> str:
    token = os.environ.get("ATLASSIAN_API_TOKEN")
    if not token:
        raise JiraAgentError(
            "Missing auth. Set ATLASSIAN_API_TOKEN, or run init.py."
        )
    return f"Bearer {token}"


def jira_request(url: str, authorization: str, accept: str = "application/json") -> bytes:
    request = Request(
        url,
        headers={
            "Authorization": authorization,
            "Accept": accept,
            "User-Agent": "jira-agent-mcp/1.0",
        },
    )

    try:
        with urlopen(request) as response:
            return response.read()
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise JiraHttpError(error.code, error.reason, body) from error
    except URLError as error:
        raise JiraAgentError(f"Network error: {error.reason}") from error


def site_origin(site: str) -> str:
    parsed = urlparse(site)
    if not parsed.scheme or not parsed.netloc:
        raise JiraAgentError(f"Invalid Jira site URL: {site}")
    return f"{parsed.scheme}://{parsed.netloc}"


def discover_cloud_id(site: str, authorization: str) -> str:
    origin = site_origin(site)
    url = f"{origin}/_edge/tenant_info"
    data = json.loads(jira_request(url, authorization).decode("utf-8"))
    cloud_id = data.get("cloudId")
    if not cloud_id:
        raise JiraAgentError(f"Could not discover cloudId from {url}")
    return cloud_id


def issue_api_base(site: str, authorization: str, scoped: bool = False) -> str:
    if not scoped:
        return site_origin(site)

    cloud_id = os.environ.get("JIRA_CLOUD_ID") or discover_cloud_id(site, authorization)
    return f"https://api.atlassian.com/ex/jira/{cloud_id}"


def read_issue_from_base(api_base: str, issue_key: str, authorization: str) -> dict[str, Any]:
    encoded_key = quote(issue_key, safe="")
    url = f"{api_base.rstrip('/')}/rest/api/3/issue/{encoded_key}?fields=attachment,project,summary"
    return json.loads(jira_request(url, authorization).decode("utf-8"))


def read_issue(site: str, issue_key: str, authorization: str) -> tuple[dict[str, Any], str]:
    try:
        return (
            read_issue_from_base(issue_api_base(site, authorization), issue_key, authorization),
            authorization,
        )
    except JiraHttpError as error:
        if error.status not in {401, 403, 404}:
            raise

        scoped_base = issue_api_base(site, authorization, scoped=True)
        try:
            return read_issue_from_base(scoped_base, issue_key, authorization), authorization
        except JiraAgentError as scoped_basic_error:
            bearer = bearer_auth_header()
            try:
                return read_issue_from_base(scoped_base, issue_key, bearer), bearer
            except JiraAgentError as scoped_bearer_error:
                scoped_error = (
                    f"Basic auth scoped API error: {scoped_basic_error}. "
                    f"Bearer auth scoped API error: {scoped_bearer_error}"
                )

                raise JiraAgentError(
                    "Could not read Jira issue using either site REST API or scoped-token "
                    f"Atlassian API route. Site REST error: {error}. "
                    f"Scoped API error: {scoped_error}. "
                    f"{issue_permission_hint(issue_key)}"
                ) from scoped_bearer_error


def safe_filename(filename: str) -> str:
    cleaned = filename.replace("/", "_").replace("\\", "_").strip()
    return cleaned or "attachment"


def unique_path(directory: Path, filename: str, overwrite: bool = False) -> Path:
    target = directory / safe_filename(filename)
    if overwrite or not target.exists():
        return target

    stem = target.stem
    suffix = target.suffix
    counter = 2

    while True:
        candidate = directory / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def issue_output_dir(
    issue_key: str,
    project_key: str | None = None,
    output_root: str | None = None,
) -> Path:
    root = output_root or os.environ.get("JIRA_ATTACHMENT_OUTPUT_ROOT") or DEFAULT_OUTPUT_ROOT
    project = project_key or issue_key.split("-", 1)[0]
    return Path(root).expanduser() / project / issue_key


def list_attachments(ticket: str, site: str | None = None) -> dict[str, Any]:
    load_env_file()
    resolved_site, issue_key = parse_ticket(ticket, site)
    authorization = auth_header()
    issue, attachment_authorization = read_issue(resolved_site, issue_key, authorization)
    fields = issue.get("fields", {})
    project_key = fields.get("project", {}).get("key") or issue_key.split("-", 1)[0]
    attachments = fields.get("attachment") or []

    return {
        "site": resolved_site,
        "issueKey": issue_key,
        "projectKey": project_key,
        "summary": fields.get("summary"),
        "attachments": [
            {
                "id": item.get("id"),
                "filename": item.get("filename"),
                "mimeType": item.get("mimeType"),
                "size": item.get("size"),
                "created": item.get("created"),
                "author": (item.get("author") or {}).get("displayName"),
            }
            for item in attachments
        ],
    }


def download_attachment(
    attachment: dict[str, Any],
    directory: Path,
    authorization: str,
    overwrite: bool = False,
) -> Path:
    filename = attachment.get("filename") or f"attachment-{attachment.get('id', 'unknown')}"
    content_url = attachment.get("content")
    if not content_url:
        raise JiraAgentError(f"Attachment {filename} does not include a content URL.")

    target = unique_path(directory, filename, overwrite=overwrite)
    if overwrite and target.exists():
        target.unlink()

    request = Request(
        content_url,
        headers={
            "Authorization": authorization,
            "Accept": "*/*",
            "User-Agent": "jira-agent-mcp/1.0",
        },
    )

    try:
        with urlopen(request) as response, target.open("wb") as file:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                file.write(chunk)
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        if target.exists():
            target.unlink()
        raise JiraHttpError(error.code, error.reason, body) from error
    except URLError as error:
        if target.exists():
            target.unlink()
        raise JiraAgentError(f"Network error: {error.reason}") from error

    return target


def download_attachments(
    ticket: str,
    site: str | None = None,
    output_root: str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    load_env_file()
    resolved_site, issue_key = parse_ticket(ticket, site)
    authorization = auth_header()
    issue, attachment_authorization = read_issue(resolved_site, issue_key, authorization)
    fields = issue.get("fields", {})
    project_key = fields.get("project", {}).get("key") or issue_key.split("-", 1)[0]
    attachments = fields.get("attachment") or []
    directory = issue_output_dir(issue_key, project_key, output_root)
    directory.mkdir(parents=True, exist_ok=True)

    downloaded = []
    for attachment in attachments:
        path = download_attachment(
            attachment,
            directory,
            attachment_authorization,
            overwrite=overwrite,
        )
        downloaded.append(
            {
                "id": attachment.get("id"),
                "filename": attachment.get("filename") or path.name,
                "mimeType": attachment.get("mimeType"),
                "size": path.stat().st_size,
                "path": str(path),
            }
        )

    return {
        "site": resolved_site,
        "issueKey": issue_key,
        "projectKey": project_key,
        "summary": fields.get("summary"),
        "outputDirectory": str(directory),
        "downloaded": downloaded,
        "count": len(downloaded),
    }
