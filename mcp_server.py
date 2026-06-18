#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import traceback
from typing import Any

from jira_agent import DEFAULT_SITE, download_attachments, list_attachments


SERVER_NAME = "jira-attachment-downloader"
SERVER_VERSION = "1.0.0"


def text_result(text: str, structured: dict[str, Any] | None = None) -> dict[str, Any]:
    result = {"content": [{"type": "text", "text": text}]}
    if structured is not None:
        result["structuredContent"] = structured
    return result


def tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "jira_list_attachments",
            "description": "List attachments on a Jira issue without downloading them.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "ticket": {
                        "type": "string",
                        "description": "Jira issue key or URL, e.g. PROJ-123 or https://your-domain.atlassian.net/browse/PROJ-123.",
                    },
                    "site": {
                        "type": "string",
                        "description": "Jira site URL when ticket is an issue key. Not needed for full Jira URLs.",
                    },
                },
                "required": ["ticket"],
            },
        },
        {
            "name": "jira_download_attachments",
            "description": "Download all attachments from a Jira issue to ~/Agents/Jira/<PROJECT>/<ISSUE>/ by default.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "ticket": {
                        "type": "string",
                        "description": "Jira issue key or URL, e.g. PROJ-123 or https://your-domain.atlassian.net/browse/PROJ-123.",
                    },
                    "site": {
                        "type": "string",
                        "description": "Jira site URL when ticket is an issue key. Not needed for full Jira URLs.",
                    },
                    "outputRoot": {
                        "type": "string",
                        "description": "Optional destination root. Defaults to ~/Agents/Jira.",
                    },
                    "overwrite": {
                        "type": "boolean",
                        "description": "Replace existing files with the same filename.",
                        "default": False,
                    },
                },
                "required": ["ticket"],
            },
        },
    ]


def handle_request(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}

    if method == "notifications/initialized":
        return None

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        }

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": tools()}}

    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}

        if name == "jira_list_attachments":
            data = list_attachments(
                ticket=arguments["ticket"],
                site=arguments.get("site") or DEFAULT_SITE,
            )
            count = len(data["attachments"])
            summary = f"{data['issueKey']} has {count} attachment(s)."
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": text_result(summary, data),
            }

        if name == "jira_download_attachments":
            data = download_attachments(
                ticket=arguments["ticket"],
                site=arguments.get("site") or DEFAULT_SITE,
                output_root=arguments.get("outputRoot"),
                overwrite=bool(arguments.get("overwrite", False)),
            )
            summary = (
                f"Downloaded {data['count']} attachment(s) from {data['issueKey']} "
                f"to {data['outputDirectory']}."
            )
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": text_result(summary, data),
            }

        raise ValueError(f"Unknown tool: {name}")

    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main() -> int:
    for line in sys.stdin:
        if not line.strip():
            continue

        try:
            message = json.loads(line)
            response = handle_request(message)
        except Exception as error:
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32000,
                    "message": str(error),
                    "data": traceback.format_exc(),
                },
            }

        if response is not None:
            sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
            sys.stdout.flush()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
