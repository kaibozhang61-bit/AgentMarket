"""
OpenSearch client for the MCP Gateway.
"""

from __future__ import annotations

from typing import Any

import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

from mcp_gateway.config import (
    AWS_REGION,
    MAX_SEARCH_RESULTS,
    OPENSEARCH_ENDPOINT,
    OPENSEARCH_INDEX,
)


def _get_client() -> OpenSearch:
    credentials = boto3.Session().get_credentials()
    awsauth = AWS4Auth(
        credentials.access_key,
        credentials.secret_key,
        AWS_REGION,
        "es",
        session_token=credentials.token,
    )
    host = OPENSEARCH_ENDPOINT.replace("https://", "").rstrip("/")
    return OpenSearch(
        hosts=[{"host": host, "port": 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
    )


_client: OpenSearch | None = None


def get_os_client() -> OpenSearch:
    global _client
    if _client is None:
        _client = _get_client()
    return _client


def knn_search(
    desc_vector: list[float],
    input_vector: list[float] | None = None,
    output_vector: list[float] | None = None,
    k: int = MAX_SEARCH_RESULTS,
) -> list[dict[str, Any]]:
    """
    Weighted 3-vector kNN search.

    Weights: description=0.5, input=0.25, output=0.25
    If input or output vectors are missing, description gets full weight.
    """
    client = get_os_client()

    # Build weighted sub-queries
    should_clauses = []
    total_weight = 0.0

    if desc_vector:
        should_clauses.append({
            "knn": {"desc_vector": {"vector": desc_vector, "k": k}},
        })
        total_weight += 0.5

    if input_vector:
        should_clauses.append({
            "knn": {"input_vector": {"vector": input_vector, "k": k}},
        })
        total_weight += 0.25

    if output_vector:
        should_clauses.append({
            "knn": {"output_vector": {"vector": output_vector, "k": k}},
        })
        total_weight += 0.25

    if not should_clauses:
        return []

    # Use script_score to combine multiple kNN queries with weights
    query: dict[str, Any] = {
        "size": k,
        "query": {
            "bool": {
                "should": should_clauses,
                "minimum_should_match": 1,
            }
        },
        "_source": ["agent_id", "name", "description", "category"],
    }

    resp = client.search(index=OPENSEARCH_INDEX, body=query)

    results = []
    for hit in resp["hits"]["hits"]:
        # Normalize score to 0-1 range (OpenSearch kNN cosinesimil returns 1/(1+d))
        score = hit.get("_score", 0)
        source = hit["_source"]
        results.append({
            "agent_id": source.get("agent_id", ""),
            "name": source.get("name", ""),
            "description": source.get("description", ""),
            "category": source.get("category", ""),
            "score": round(score, 4),
        })

    return results
