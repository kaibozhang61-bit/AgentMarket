"""
Deploy the embedding sync Lambda + DDB Stream trigger.

1. Enable DynamoDB Streams on AgentMarketplace table
2. Create IAM role for the Lambda
3. Package and deploy the Lambda function
4. Create event source mapping (DDB Stream → Lambda)

Usage:
    python scripts/deploy_embedding_sync.py
    python scripts/deploy_embedding_sync.py --table-name AgentMarketplace --region us-east-1

Prerequisites:
    - pip install opensearch-py requests-aws4auth (in Lambda package)
    - OPENSEARCH_ENDPOINT set in environment or passed via --opensearch-endpoint
"""

import argparse
import io
import json
import os
import sys
import time
import zipfile

import boto3
from botocore.exceptions import ClientError

TABLE_NAME = "AgentMarketplace"
REGION = "us-east-1"
FUNCTION_NAME = "agent-marketplace-embedding-sync"
ROLE_NAME = "agent-marketplace-embedding-sync-role"


def get_account_id() -> str:
    return boto3.client("sts").get_caller_identity()["Account"]


# ── Step 1: Enable DDB Streams ───────────────────────────────────────────────

def enable_streams(table_name: str, region: str) -> str:
    """Enable DDB Streams (NEW_IMAGE) on the table. Returns stream ARN."""
    ddb = boto3.client("dynamodb", region_name=region)

    desc = ddb.describe_table(TableName=table_name)["Table"]
    stream_spec = desc.get("StreamSpecification", {})

    if stream_spec.get("StreamEnabled"):
        arn = desc.get("LatestStreamArn", "")
        print(f"  Streams already enabled: {arn}")
        return arn

    print(f"  Enabling streams on {table_name}...")
    ddb.update_table(
        TableName=table_name,
        StreamSpecification={
            "StreamEnabled": True,
            "StreamViewType": "NEW_AND_OLD_IMAGES",
        },
    )

    # Wait for stream to be active
    for _ in range(30):
        time.sleep(2)
        desc = ddb.describe_table(TableName=table_name)["Table"]
        arn = desc.get("LatestStreamArn", "")
        if arn:
            print(f"  Stream ARN: {arn}")
            return arn

    print("ERROR: Timed out waiting for stream ARN", file=sys.stderr)
    sys.exit(1)


# ── Step 2: Create IAM Role ──────────────────────────────────────────────────

TRUST_POLICY = json.dumps({
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Principal": {"Service": "lambda.amazonaws.com"},
        "Action": "sts:AssumeRole",
    }],
})


def create_role(region: str, table_name: str, account_id: str) -> str:
    """Create IAM role for the Lambda. Returns role ARN."""
    iam = boto3.client("iam")

    try:
        resp = iam.get_role(RoleName=ROLE_NAME)
        arn = resp["Role"]["Arn"]
        print(f"  Role already exists: {arn}")
        return arn
    except ClientError as e:
        if e.response["Error"]["Code"] != "NoSuchEntity":
            raise

    print(f"  Creating role {ROLE_NAME}...")
    resp = iam.create_role(
        RoleName=ROLE_NAME,
        AssumeRolePolicyDocument=TRUST_POLICY,
        Description="Lambda role for agent marketplace embedding sync",
    )
    role_arn = resp["Role"]["Arn"]

    # Attach managed policies
    iam.attach_role_policy(
        RoleName=ROLE_NAME,
        PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
    )

    # Inline policy for DDB Streams + OpenSearch + Bedrock
    inline_policy = json.dumps({
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "dynamodb:GetRecords",
                    "dynamodb:GetShardIterator",
                    "dynamodb:DescribeStream",
                    "dynamodb:ListStreams",
                ],
                "Resource": f"arn:aws:dynamodb:{region}:{account_id}:table/{table_name}/stream/*",
            },
            {
                "Effect": "Allow",
                "Action": ["es:ESHttpPost", "es:ESHttpPut", "es:ESHttpDelete", "es:ESHttpGet"],
                "Resource": f"arn:aws:es:{region}:{account_id}:domain/agent-marketplace/*",
            },
            {
                "Effect": "Allow",
                "Action": ["bedrock:InvokeModel"],
                "Resource": "*",
            },
        ],
    })
    iam.put_role_policy(
        RoleName=ROLE_NAME,
        PolicyName="embedding-sync-permissions",
        PolicyDocument=inline_policy,
    )

    # IAM role propagation takes a few seconds
    print("  Waiting for role propagation...")
    time.sleep(10)

    return role_arn


# ── Step 3: Package Lambda ───────────────────────────────────────────────────

def package_lambda() -> bytes:
    """Create a zip of the Lambda handler code + dependencies."""
    import subprocess
    import tempfile
    import shutil

    with tempfile.TemporaryDirectory() as tmpdir:
        # Install dependencies into the temp dir
        print("  Installing dependencies (opensearch-py, requests-aws4auth)...")
        subprocess.check_call(
            [
                sys.executable, "-m", "pip", "install",
                "opensearch-py", "requests-aws4auth",
                "-t", tmpdir,
                "--quiet", "--no-cache-dir",
            ],
            stdout=subprocess.DEVNULL,
        )

        # Copy handler into the temp dir
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "lambdas", "embedding_sync", "handler.py"
        )
        shutil.copy2(handler_path, os.path.join(tmpdir, "handler.py"))

        # Zip everything
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(tmpdir):
                # Skip __pycache__ and .dist-info
                dirs[:] = [d for d in dirs if d != "__pycache__" and not d.endswith(".dist-info")]
                for f in files:
                    full = os.path.join(root, f)
                    arcname = os.path.relpath(full, tmpdir)
                    zf.write(full, arcname)

        zip_bytes = buf.getvalue()
        print(f"  Package size: {len(zip_bytes) / 1024 / 1024:.1f} MB")
        return zip_bytes


# ── Step 4: Deploy Lambda ────────────────────────────────────────────────────

def deploy_lambda(
    region: str,
    role_arn: str,
    opensearch_endpoint: str,
) -> str:
    """Create or update the Lambda function. Returns function ARN."""
    lam = boto3.client("lambda", region_name=region)
    code_zip = package_lambda()

    env_vars = {
        "OPENSEARCH_ENDPOINT": opensearch_endpoint,
        "OPENSEARCH_INDEX": "agent_vectors",
        "AWS_REGION_NAME": region,
        "EMBEDDING_MODEL_ID": "amazon.titan-embed-text-v2:0",
    }

    try:
        resp = lam.get_function(FunctionName=FUNCTION_NAME)
        print(f"  Updating existing function {FUNCTION_NAME}...")
        lam.update_function_code(
            FunctionName=FUNCTION_NAME,
            ZipFile=code_zip,
        )
        # Wait for update to complete
        time.sleep(5)
        lam.update_function_configuration(
            FunctionName=FUNCTION_NAME,
            Environment={"Variables": env_vars},
            Timeout=120,
            MemorySize=256,
        )
        return resp["Configuration"]["FunctionArn"]
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceNotFoundException":
            raise

    print(f"  Creating function {FUNCTION_NAME}...")

    # The handler uses opensearch-py and requests-aws4auth which need to be
    # in a Lambda layer. For MVP, we use a layer or inline install.
    # For now, deploy with just the handler — dependencies via layer.
    resp = lam.create_function(
        FunctionName=FUNCTION_NAME,
        Runtime="python3.11",
        Role=role_arn,
        Handler="handler.handler",
        Code={"ZipFile": code_zip},
        Timeout=120,
        MemorySize=256,
        Environment={"Variables": env_vars},
        Tags={"Project": "AgentMarketplace"},
    )
    print(f"  Function ARN: {resp['FunctionArn']}")

    # Wait for function to be active
    waiter = lam.get_waiter("function_active_v2")
    waiter.wait(FunctionName=FUNCTION_NAME)

    return resp["FunctionArn"]


# ── Step 5: Create Event Source Mapping ───────────────────────────────────────

def create_trigger(region: str, function_name: str, stream_arn: str) -> None:
    """Wire DDB Stream → Lambda trigger with event filter."""
    lam = boto3.client("lambda", region_name=region)

    # Filter: only invoke Lambda for AGENT# items with SK=LATEST
    # This prevents Lambda invocations for runs, sessions, users, tools, etc.
    filter_criteria = {
        "Filters": [
            {
                "Pattern": json.dumps({
                    "dynamodb": {
                        "Keys": {
                            "PK": {"S": [{"prefix": "AGENT#"}]},
                            "SK": {"S": ["LATEST"]},
                        }
                    }
                })
            }
        ]
    }

    # Check if mapping already exists
    resp = lam.list_event_source_mappings(
        EventSourceArn=stream_arn,
        FunctionName=function_name,
    )
    if resp.get("EventSourceMappings"):
        mapping = resp["EventSourceMappings"][0]
        uuid = mapping["UUID"]
        # Update existing mapping with filter
        print(f"  Trigger exists (UUID: {uuid}), updating with filter criteria...")
        lam.update_event_source_mapping(
            UUID=uuid,
            FilterCriteria=filter_criteria,
        )
        print(f"  Filter applied: only AGENT# + SK=LATEST events invoke Lambda")
        return

    print(f"  Creating event source mapping with filter...")
    resp = lam.create_event_source_mapping(
        EventSourceArn=stream_arn,
        FunctionName=function_name,
        StartingPosition="LATEST",
        BatchSize=10,
        MaximumBatchingWindowInSeconds=5,
        Enabled=True,
        FilterCriteria=filter_criteria,
    )
    print(f"  Trigger UUID: {resp['UUID']}")
    print(f"  Filter applied: only AGENT# + SK=LATEST events invoke Lambda")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy embedding sync Lambda + DDB Stream trigger.")
    parser.add_argument("--table-name", default=TABLE_NAME)
    parser.add_argument("--region", default=REGION)
    parser.add_argument("--opensearch-endpoint", default=os.environ.get("OPENSEARCH_ENDPOINT", ""))
    args = parser.parse_args()

    if not args.opensearch_endpoint:
        print("ERROR: --opensearch-endpoint is required (or set OPENSEARCH_ENDPOINT env var)")
        print("  Get it from: aws opensearch describe-domain --domain-name agent-marketplace --query 'DomainStatus.Endpoint'")
        sys.exit(1)

    endpoint = args.opensearch_endpoint
    if not endpoint.startswith("https://"):
        endpoint = f"https://{endpoint}"

    account_id = get_account_id()
    print(f"Account: {account_id}")
    print(f"Region:  {args.region}")
    print(f"Table:   {args.table_name}")
    print(f"OpenSearch: {endpoint}")
    print()

    print("[1/4] Enabling DynamoDB Streams...")
    stream_arn = enable_streams(args.table_name, args.region)

    print("[2/4] Creating IAM role...")
    role_arn = create_role(args.region, args.table_name, account_id)

    print("[3/4] Deploying Lambda function...")
    function_arn = deploy_lambda(args.region, role_arn, endpoint)

    print("[4/4] Creating DDB Stream → Lambda trigger...")
    create_trigger(args.region, FUNCTION_NAME, stream_arn)

    print()
    print("Done! The embedding sync pipeline is active.")
    print(f"  Table:    {args.table_name} (streams enabled)")
    print(f"  Lambda:   {FUNCTION_NAME}")
    print(f"  Trigger:  DDB Stream → Lambda on NEW_AND_OLD_IMAGES")


if __name__ == "__main__":
    main()
