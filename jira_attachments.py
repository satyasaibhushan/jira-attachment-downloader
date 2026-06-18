#!/usr/bin/env python3
import argparse
import sys

from jira_agent import DEFAULT_OUTPUT_ROOT, DEFAULT_SITE, download_attachments


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download all attachments from a Jira ticket."
    )
    parser.add_argument("ticket", help="Jira issue key or URL, e.g. PROJ-123")
    parser.add_argument(
        "--site",
        default=DEFAULT_SITE,
        help="Jira site URL when passing an issue key. Not needed for full Jira URLs.",
    )
    parser.add_argument(
        "--output-root",
        default=DEFAULT_OUTPUT_ROOT,
        help=f"Root directory for downloads. Default: {DEFAULT_OUTPUT_ROOT}",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing files with the same attachment filenames.",
    )
    args = parser.parse_args()

    try:
        result = download_attachments(
            ticket=args.ticket,
            site=args.site,
            output_root=args.output_root,
            overwrite=args.overwrite,
        )

        if result["count"] == 0:
            print(f"No attachments found for {result['issueKey']}.")
            print(f"Checked: {result['site']}/browse/{result['issueKey']}")
            return 0

        print(f"Downloaded {result['count']} attachment(s) from {result['issueKey']}")
        print(f"Destination: {result['outputDirectory']}")
        for item in result["downloaded"]:
            print(f"- {item['filename']} ({item['size']} bytes)")

        return 0
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
