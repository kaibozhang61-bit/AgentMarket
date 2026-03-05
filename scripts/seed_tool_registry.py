"""
Seed the tool registry with 20 built-in external tool definitions.

Usage:
    python scripts/seed_tool_registry.py
    python scripts/seed_tool_registry.py --local
"""

import argparse
import sys

import boto3

TABLE_NAME = "AgentMarketplace"

TOOLS = [
    {"toolId": "gmail", "name": "Gmail", "category": "Email",
     "description": "Send, read, search emails via Gmail API",
     "authType": "oauth2"},
    {"toolId": "slack", "name": "Slack", "category": "Messaging",
     "description": "Send messages, read channels, post to threads",
     "authType": "oauth2"},
    {"toolId": "google_sheets", "name": "Google Sheets", "category": "Spreadsheet",
     "description": "Read, write, append rows in Google Sheets",
     "authType": "oauth2"},
    {"toolId": "google_calendar", "name": "Google Calendar", "category": "Calendar",
     "description": "Create, read, update calendar events",
     "authType": "oauth2"},
    {"toolId": "google_drive", "name": "Google Drive", "category": "Storage",
     "description": "Upload, download, search files in Google Drive",
     "authType": "oauth2"},
    {"toolId": "notion", "name": "Notion", "category": "Productivity",
     "description": "Create/update pages, query databases in Notion",
     "authType": "api_key"},
    {"toolId": "airtable", "name": "Airtable", "category": "Database",
     "description": "Read, create, update records in Airtable",
     "authType": "api_key"},
    {"toolId": "zapier_webhooks", "name": "Zapier Webhooks", "category": "Automation",
     "description": "Trigger any Zapier workflow via webhook",
     "authType": "none"},
    {"toolId": "twilio", "name": "Twilio", "category": "SMS/Voice",
     "description": "Send SMS, make calls via Twilio",
     "authType": "credentials"},
    {"toolId": "stripe", "name": "Stripe", "category": "Payments",
     "description": "Create charges, check balances, list transactions",
     "authType": "api_key"},
    {"toolId": "salesforce", "name": "Salesforce", "category": "CRM",
     "description": "Query contacts, create leads, update opportunities",
     "authType": "oauth2"},
    {"toolId": "hubspot", "name": "HubSpot", "category": "CRM",
     "description": "Manage contacts, deals, tickets in HubSpot",
     "authType": "api_key"},
    {"toolId": "jira", "name": "Jira", "category": "Project Mgmt",
     "description": "Create issues, update status, search in Jira",
     "authType": "api_key"},
    {"toolId": "github", "name": "GitHub", "category": "Dev Tools",
     "description": "Create issues, PRs, read repos on GitHub",
     "authType": "api_key"},
    {"toolId": "postgresql", "name": "PostgreSQL", "category": "Database",
     "description": "Run SQL queries (read-only by default)",
     "authType": "credentials"},
    {"toolId": "http_rest", "name": "HTTP/REST", "category": "General",
     "description": "Call any REST API with configurable auth",
     "authType": "api_key"},
    {"toolId": "web_search", "name": "Web Search", "category": "Search",
     "description": "Search the web via Bing or Google",
     "authType": "api_key"},
    {"toolId": "web_scrape", "name": "Web Scrape", "category": "Data",
     "description": "Extract content from URLs",
     "authType": "none"},
    {"toolId": "s3", "name": "S3", "category": "Storage",
     "description": "Read/write files to S3 buckets",
     "authType": "credentials"},
    {"toolId": "shopify", "name": "Shopify", "category": "E-commerce",
     "description": "Manage products, orders, customers in Shopify",
     "authType": "api_key"},
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed tool registry.")
    parser.add_argument("--local", action="store_true")
    parser.add_argument("--table-name", default=TABLE_NAME)
    args = parser.parse_args()

    if args.local:
        ddb = boto3.resource("dynamodb", region_name="us-east-1",
                             endpoint_url="http://localhost:8000",
                             aws_access_key_id="local", aws_secret_access_key="local")
    else:
        ddb = boto3.resource("dynamodb")

    table = ddb.Table(args.table_name)

    for tool in TOOLS:
        item = {
            "PK": f"TOOL#{tool['toolId']}",
            "SK": "META",
            "entityType": "TOOL",
            "toolId": tool["toolId"],
            "name": tool["name"],
            "category": tool["category"],
            "description": tool["description"],
            "authType": tool["authType"],
            "inputSchema": [],
            "outputSchema": [],
            "config": {},
        }
        table.put_item(Item=item)
        print(f"  ✓ {tool['name']}")

    print(f"\nSeeded {len(TOOLS)} tools into {args.table_name}.")


if __name__ == "__main__":
    main()
