# Jira Attachment Downloader + MCP

Small dependency-free local tool to download every attachment from a Jira ticket into a predictable local folder. It also includes an MCP server so agents like Codex, Claude Desktop, Claude Code, and Cursor can use the same capability.

Default output layout:

```text
~/Agents/Jira/<PROJECT>/<ISSUE>/
```

## Init

Run the setup flow:

```bash
python3 ./init.py
```

It will ask for:

- Atlassian email
- Atlassian API token
- default Jira site
- attachment output root
- which agent apps should get the MCP config

Credentials are written to:

```text
~/.jira-agent-mcp.env
```

The file is created with mode `600`. MCP app configs receive only the env-file path, not the raw token.

## Agent Tools

The MCP exposes:

- `jira_list_attachments`
- `jira_download_attachments`

After setup, restart the selected apps so they reload MCP configuration.

## CLI

```bash
python3 jira_attachments.py "https://your-domain.atlassian.net/browse/PROJ-123"
```

This downloads files to:

```text
~/Agents/Jira/PROJ/PROJ-123/
```

You can also pass an issue key:

```bash
python3 jira_attachments.py PROJ-123 --site https://your-domain.atlassian.net
```

Use a custom destination root:

```bash
python3 jira_attachments.py PROJ-123 \
  --site https://your-domain.atlassian.net \
  --output-root ~/Downloads/Jira
```

## Auth

Create a Jira API token with read scopes. You can either run `init.py`, or set these manually:

```bash
export ATLASSIAN_EMAIL="user@example.com"
export ATLASSIAN_API_TOKEN="your-token"
```

Required for attachment downloads:

- `read:attachment:jira`
- `read:issue:jira`
- `read:project:jira`

The token is only read from environment variables. Do not commit it.
