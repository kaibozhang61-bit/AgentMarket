"""
scripts/create_cognito.py

Create the Cognito User Pool and App Client for Agent Marketplace.

Usage:
    poetry run python scripts/create_cognito.py [--region us-east-1]

Output:
    Prints the env vars to add to your .env file.
"""

import argparse
import json
import sys

import boto3
from botocore.exceptions import ClientError


def create(region: str) -> None:
    client = boto3.client("cognito-idp", region_name=region)

    # ── 1. User Pool ──────────────────────────────────────────────────────────
    print("Creating User Pool …")
    try:
        pool_resp = client.create_user_pool(
            PoolName="AgentMarketplaceUserPool",
            Policies={
                "PasswordPolicy": {
                    "MinimumLength": 8,
                    "RequireUppercase": True,
                    "RequireLowercase": True,
                    "RequireNumbers": True,
                    "RequireSymbols": False,
                }
            },
            # Allow sign-in with email address
            UsernameAttributes=["email"],
            AutoVerifiedAttributes=["email"],
            Schema=[
                {
                    "Name": "email",
                    "AttributeDataType": "String",
                    "Required": True,
                    "Mutable": True,
                },
                {
                    "Name": "preferred_username",
                    "AttributeDataType": "String",
                    "Required": False,
                    "Mutable": True,
                },
            ],
            EmailConfiguration={"EmailSendingAccount": "COGNITO_DEFAULT"},
            # Keep tokens short for MVP; extend as needed
            AdminCreateUserConfig={"AllowAdminCreateUserOnly": False},
        )
        pool_id: str = pool_resp["UserPool"]["Id"]
        print(f"  ✓ User Pool created: {pool_id}")
    except ClientError as exc:
        print(f"  ✗ Failed to create User Pool: {exc}", file=sys.stderr)
        sys.exit(1)

    # ── 2. App Client (no secret — safe for SPAs and mobile apps) ─────────────
    print("Creating App Client …")
    try:
        client_resp = client.create_user_pool_client(
            UserPoolId=pool_id,
            ClientName="AgentMarketplaceClient",
            GenerateSecret=False,
            ExplicitAuthFlows=[
                "ALLOW_USER_SRP_AUTH",          # standard SRP (browser / SDK)
                "ALLOW_USER_PASSWORD_AUTH",     # direct password (testing / CLI)
                "ALLOW_REFRESH_TOKEN_AUTH",
            ],
            # Token validity
            AccessTokenValidity=1,
            IdTokenValidity=1,
            RefreshTokenValidity=30,
            TokenValidityUnits={
                "AccessToken": "hours",
                "IdToken": "hours",
                "RefreshToken": "days",
            },
            # Return email in ID token
            ReadAttributes=["email", "preferred_username", "sub"],
            WriteAttributes=["email", "preferred_username"],
        )
        client_id: str = client_resp["UserPoolClient"]["ClientId"]
        print(f"  ✓ App Client created: {client_id}")
    except ClientError as exc:
        print(f"  ✗ Failed to create App Client: {exc}", file=sys.stderr)
        sys.exit(1)

    # ── Output ────────────────────────────────────────────────────────────────
    print("\n─── Add these to your .env file ───────────────────────────────────")
    print(f"COGNITO_REGION={region}")
    print(f"COGNITO_USER_POOL_ID={pool_id}")
    print(f"COGNITO_CLIENT_ID={client_id}")
    print("───────────────────────────────────────────────────────────────────")

    # Also write to a local file for convenience
    env_snippet = (
        f"COGNITO_REGION={region}\n"
        f"COGNITO_USER_POOL_ID={pool_id}\n"
        f"COGNITO_CLIENT_ID={client_id}\n"
    )
    out_path = "cognito_env.txt"
    with open(out_path, "w") as f:
        f.write(env_snippet)
    print(f"\nAlso saved to: {out_path}")

    # Print JWKS URL for reference
    jwks_url = (
        f"https://cognito-idp.{region}.amazonaws.com/{pool_id}"
        "/.well-known/jwks.json"
    )
    print(f"\nJWKS URL (for debugging): {jwks_url}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create Cognito User Pool")
    parser.add_argument("--region", default="us-east-1", help="AWS region")
    args = parser.parse_args()
    create(args.region)
