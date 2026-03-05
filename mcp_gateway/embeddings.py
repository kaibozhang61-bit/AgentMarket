"""
Shared embedding utility for the MCP Gateway.
"""

from __future__ import annotations

import json

import boto3

from mcp_gateway.config import AWS_REGION, EMBEDDING_MODEL_ID

_bedrock = boto3.client("bedrock-runtime", region_name=AWS_REGION)


def embed(text: str) -> list[float]:
    """Call Bedrock Titan Embeddings V2."""
    if not text.strip():
        return []
    resp = _bedrock.invoke_model(
        modelId=EMBEDDING_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({"inputText": text[:8000]}),
    )
    body = json.loads(resp["body"].read())
    return body["embedding"]
