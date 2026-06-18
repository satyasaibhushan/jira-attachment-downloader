# Jira Attachment Downloader + MCP

Download every attachment from a Jira issue into a predictable local folder, and expose the same capability to agent apps through MCP.

Default output layout:

```text
~/Agents/Jira/<PROJECT>/<ISSUE>/
```

For example, `PROJ-123` downloads into:

```text
~/Agents/Jira/PROJ/PROJ-123/
```

## What This Installs

This repository contains:

- `init.py`: interactive setup and MCP installer
- `mcp_server.py`: local stdio MCP server for agent apps
- `jira_attachments.py`: direct CLI downloader
- `jira_agent.py`: shared Jira API and download logic

The MCP server exposes two tools:

- `jira_list_attachments`: list issue attachments without downloading them
- `jira_download_attachments`: download all issue attachments to disk

Supported app config targets:

- Codex
- Cursor
- Claude Desktop
- Claude Code

## Prerequisites

- Python 3.9 or newer
- A Jira Cloud site, such as `https://your-domain.atlassian.net`
- An Atlassian account that can open the target Jira issues in the browser
- An Atlassian API token with the Jira read scopes listed below

No Python package install is required.

## Step 1: Create An Atlassian API Token

1. Open [Atlassian API tokens](https://id.atlassian.com/manage-profile/security/api-tokens).
2. Click **Create API token**.
3. Select **Jira** as the API token app.
4. Add these read scopes:

```text
read:account
read:jira-user
read:jira-work
read:me
read:issue:jira
read:project:jira
read:attachment:jira
```

Minimum scopes for this tool are:

```text
read:issue:jira
read:project:jira
read:attachment:jira
```

The broader classic scopes such as `read:jira-work` are useful for compatibility with older Jira REST behavior. Do not add write scopes unless you plan to extend this tool to modify Jira.

5. Create the token and copy it once.

Do not commit the token or paste it into chats.

## Step 2: Run Init

From the repository root:

```bash
python3 ./init.py
```

The setup flow asks for:

- Atlassian email
- Atlassian API token
- default Jira site, for example `https://your-domain.atlassian.net`
- attachment output root, defaulting to `~/Agents/Jira`
- which agent apps should receive the MCP config

Credentials are written to:

```text
~/.jira-agent-mcp.env
```

That file is created with mode `600`. Agent app configs receive only the path to this env file, not the raw token.

After init completes, restart any selected app so it reloads MCP configuration.

## Step 3: Verify With The CLI

Use a full Jira issue URL:

```bash
python3 ./jira_attachments.py "https://your-domain.atlassian.net/browse/PROJ-123"
```

Or use an issue key with a site:

```bash
python3 ./jira_attachments.py PROJ-123 --site https://your-domain.atlassian.net
```

If setup worked, the command prints the destination directory and downloaded files.

## CLI Options

Use a custom destination root:

```bash
python3 ./jira_attachments.py PROJ-123 \
  --site https://your-domain.atlassian.net \
  --output-root ~/Downloads/Jira
```

Replace existing files with matching attachment filenames:

```bash
python3 ./jira_attachments.py PROJ-123 \
  --site https://your-domain.atlassian.net \
  --overwrite
```

Without `--overwrite`, duplicate filenames are saved as `name (2).ext`, `name (3).ext`, and so on.

## Using From Agents

After init and app restart, ask the agent to use the MCP tool. Example prompts:

```text
List attachments for https://your-domain.atlassian.net/browse/PROJ-123.
```

```text
Download all attachments for PROJ-123.
```

For bare issue keys like `PROJ-123`, the app uses the default Jira site stored during init.

## Manual Environment Setup

You can skip `init.py` and set environment variables yourself:

```bash
export ATLASSIAN_EMAIL="user@example.com"
export ATLASSIAN_API_TOKEN="your-token"
export JIRA_DEFAULT_SITE="https://your-domain.atlassian.net"
export JIRA_ATTACHMENT_OUTPUT_ROOT="~/Agents/Jira"
```

Then run:

```bash
python3 ./jira_attachments.py PROJ-123
```

Optional:

```bash
export JIRA_CLOUD_ID="your-cloud-id"
```

`JIRA_CLOUD_ID` avoids cloud-id discovery when using scoped Atlassian API token routes.

## Troubleshooting

### `Missing auth. Set ATLASSIAN_EMAIL and ATLASSIAN_API_TOKEN, or run init.py.`

Run:

```bash
python3 ./init.py
```

Or set `ATLASSIAN_EMAIL` and `ATLASSIAN_API_TOKEN` manually.

### `A Jira site is required when passing an issue key`

Pass a full Jira URL:

```bash
python3 ./jira_attachments.py "https://your-domain.atlassian.net/browse/PROJ-123"
```

Or configure `JIRA_DEFAULT_SITE` through `init.py`.

### `404 Not Found` But The Issue Opens In The Browser

Jira often returns `404` when the authenticated API token cannot browse the issue.

Check:

- the token belongs to the same Atlassian account that can open the issue
- the token was created for the Jira app, not another Atlassian app
- the token includes `read:issue:jira`, `read:project:jira`, and `read:attachment:jira`
- the issue key and Jira site URL are correct
- your Jira permissions allow API access to the project

### `401 Unauthorized`

Check:

- the token was copied correctly
- the token has not expired or been revoked
- `~/.jira-agent-mcp.env` has the right email and token
- you restarted the agent app after running init

### MCP Tool Does Not Show Up

Run init again and select the target app:

```bash
python3 ./init.py
```

Then restart the app. For Claude Code, the installer uses:

```bash
claude mcp add-json
```

So the `claude` CLI must be available on `PATH`.

## Security Notes

- The token is stored locally in `~/.jira-agent-mcp.env` with mode `600`.
- The token is not written into Codex, Cursor, Claude Desktop, or Claude Code config files.
- App configs only receive `JIRA_AGENT_MCP_ENV`, pointing to the env file.
- `.env` files are ignored by git.
- Prefer read-only scopes. Do not add write scopes for this downloader.

## Development Checks

Syntax check:

```bash
python3 -c "import ast, pathlib; [ast.parse(p.read_text()) for p in pathlib.Path('.').glob('*.py')]; print('syntax ok')"
```

MCP smoke test:

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' \
  | python3 ./mcp_server.py
```
