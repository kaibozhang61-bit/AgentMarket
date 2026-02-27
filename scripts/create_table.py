"""
Create (or verify) the AgentMarketplace DynamoDB single table.

Usage:
    # Against real AWS (reads credentials from env / ~/.aws)
    python scripts/create_table.py

    # Against DynamoDB Local (docker run -p 8000:8000 amazon/dynamodb-local)
    python scripts/create_table.py --local
"""

import argparse
import sys

import boto3
from botocore.exceptions import ClientError

# ── Table definition ──────────────────────────────────────────────────────────

TABLE_NAME = "AgentMarketplace"

# Only attributes used as table/GSI keys need to be declared here.
ATTRIBUTE_DEFINITIONS = [
    {"AttributeName": "PK", "AttributeType": "S"},
    {"AttributeName": "SK", "AttributeType": "S"},
    # GSI-1/3 (shared): query all entities by author, sorted by creation time
    {"AttributeName": "authorId", "AttributeType": "S"},
    {"AttributeName": "createdAt", "AttributeType": "S"},
    # GSI-2: marketplace hot-sort (status#visibility → callCount)
    # statusVisibility stores a composite like "PUBLISHED#public"
    {"AttributeName": "statusVisibility", "AttributeType": "S"},
    {"AttributeName": "callCount", "AttributeType": "N"},
]

KEY_SCHEMA = [
    {"AttributeName": "PK", "KeyType": "HASH"},
    {"AttributeName": "SK", "KeyType": "RANGE"},
]

GLOBAL_SECONDARY_INDEXES = [
    {
        # GSI-1 + GSI-3 merged: "give me all agents / workflows by this author"
        # Callers add FilterExpression on entityType ("AGENT" | "WORKFLOW")
        "IndexName": "GSI1_AuthorByDate",
        "KeySchema": [
            {"AttributeName": "authorId", "KeyType": "HASH"},
            {"AttributeName": "createdAt", "KeyType": "RANGE"},
        ],
        "Projection": {"ProjectionType": "ALL"},
    },
    {
        # GSI-2: marketplace hot page  → query(statusVisibility="PUBLISHED#public", sort by callCount)
        "IndexName": "GSI2_MarketplaceHotness",
        "KeySchema": [
            {"AttributeName": "statusVisibility", "KeyType": "HASH"},
            {"AttributeName": "callCount", "KeyType": "RANGE"},
        ],
        "Projection": {"ProjectionType": "ALL"},
    },
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_client(local: bool) -> "boto3.client":
    if local:
        return boto3.client(
            "dynamodb",
            region_name="us-east-1",
            endpoint_url="http://localhost:8000",
            aws_access_key_id="local",
            aws_secret_access_key="local",
        )
    return boto3.client("dynamodb")


def table_exists(client, table_name: str) -> bool:
    try:
        client.describe_table(TableName=table_name)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            return False
        raise


def create_table(client, table_name: str) -> dict:
    return client.create_table(
        TableName=table_name,
        AttributeDefinitions=ATTRIBUTE_DEFINITIONS,
        KeySchema=KEY_SCHEMA,
        GlobalSecondaryIndexes=GLOBAL_SECONDARY_INDEXES,
        BillingMode="PAY_PER_REQUEST",  # On-demand — no capacity planning for MVP
        Tags=[
            {"Key": "Project", "Value": "AgentMarketplace"},
            {"Key": "Stage", "Value": "mvp"},
        ],
    )


def wait_for_active(client, table_name: str) -> None:
    print(f"  Waiting for table '{table_name}' to become ACTIVE …", end="", flush=True)
    waiter = client.get_waiter("table_exists")
    waiter.wait(TableName=table_name, WaiterConfig={"Delay": 2, "MaxAttempts": 30})
    print(" done.")


def print_table_summary(client, table_name: str) -> None:
    desc = client.describe_table(TableName=table_name)["Table"]
    print(f"\nTable:  {desc['TableName']}")
    print(f"Status: {desc['TableStatus']}")
    print(f"ARN:    {desc['TableArn']}")
    print("\nGSIs:")
    for gsi in desc.get("GlobalSecondaryIndexes", []):
        pk = next(k["AttributeName"] for k in gsi["KeySchema"] if k["KeyType"] == "HASH")
        sk = next(k["AttributeName"] for k in gsi["KeySchema"] if k["KeyType"] == "RANGE")
        print(f"  {gsi['IndexName']}: PK={pk}, SK={sk}  [{gsi['IndexStatus']}]")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Create AgentMarketplace DynamoDB table.")
    parser.add_argument(
        "--local",
        action="store_true",
        help="Target DynamoDB Local at http://localhost:8000",
    )
    parser.add_argument(
        "--table-name",
        default=TABLE_NAME,
        help=f"Override table name (default: {TABLE_NAME})",
    )
    args = parser.parse_args()

    client = get_client(local=args.local)
    target = "DynamoDB Local" if args.local else "AWS DynamoDB"
    print(f"Target: {target}")
    print(f"Table:  {args.table_name}\n")

    if table_exists(client, args.table_name):
        print(f"Table '{args.table_name}' already exists — skipping creation.")
        print_table_summary(client, args.table_name)
        sys.exit(0)

    print(f"Creating table '{args.table_name}' …")
    try:
        create_table(client, args.table_name)
    except ClientError as e:
        print(f"ERROR: {e.response['Error']['Message']}", file=sys.stderr)
        sys.exit(1)

    wait_for_active(client, args.table_name)
    print_table_summary(client, args.table_name)
    print("\nDone. Table is ready.")


if __name__ == "__main__":
    main()
