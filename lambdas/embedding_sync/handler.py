"""
Embedding Sync Lambda — triggered by DDB Streams on agent publish.

On INSERT/MODIFY of an AGENT item with status=published:
  1. Embed description → desc_vector
  2. Alphabetically sort input fields, concat descriptions → input_vector
  3. Alphabetically sort output fields, concat descriptions → output_vector
  4. Upsert all 3 vectors into OpenSearch (agent_vectors index)

On REMOVE or status != published:
  Delete the document from OpenSearch.

Environment variables:
  OPENSEARCH_ENDPOINT  — e.g. https://my-domain.us-east-1.es.amazonaws.com
  OPENSEARCH_INDEX     — default: agent_vectors
  AWS_REGION           — default: us-east-1
  EMBEDDING_MODEL_ID   — default: amazon.titan-embed-text-v2:0
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

logger = logging.getLogger()
logger.setLevel(logging.INFO)

OPENSEARCH_ENDPOINT = os.environ["OPENSEARCH_ENDPOINT"]
OPENSEARCH_INDEX = os.environ.get("OPENSEARCH_INDEX", "agent_vectors")
REGION = os.environ.get("AWS_REGION", "us-east-1")
EMBEDDING_MODEL_ID = os.environ.get("EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0")

_bedrock = boto3.client("bedrock-runtime", region_name=REGION)


def _get_os_client() -> OpenSearch:
    credentials = boto3.Session().get_credentials()
    awsauth = AWS4Auth(
        credentials.access_key,
        credentials.secret_key,
        REGION,
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


def _embed(text: str) -> list[float]:
    """Call Bedrock Titan Embeddings V2 to get a vector."""
    if not text.strip():
        return []
    resp = _bedrock.invoke_model(
        modelId=EMBEDDING_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({"inputText": text[:8000]}),  # Titan limit
    )
    body = json.loads(resp["body"].read())
    return body["embedding"]


def _fields_to_text(fields: list[dict[str, Any]]) -> str:
    """
    Alphabetically sort fields by fieldName, concat name + description.
    Only include public fields.
    """
    public = [f for f in fields if f.get("visibility", "public") == "public"]
    public.sort(key=lambda f: f.get("fieldName", ""))
    parts = []
    for f in public:
        name = f.get("fieldName", "")
        desc = f.get("description", "")
        ftype = f.get("type", "")
        parts.append(f"{name} ({ftype}): {desc}" if desc else f"{name} ({ftype})")
    return "; ".join(parts)


def _unmarshal_ddb(record: dict) -> dict[str, Any]:
    """Simple DDB Streams image unmarshalling."""
    deserializer = boto3.dynamodb.types.TypeDeserializer()
    return {k: deserializer.deserialize(v) for k, v in record.items()}


def handler(event: dict, context: Any) -> dict:
    os_client = _get_os_client()

    for record in event.get("Records", []):
        event_name = record["eventName"]  # INSERT | MODIFY | REMOVE
        keys = _unmarshal_ddb(record["dynamodb"]["Keys"])
        pk = keys.get("PK", "")
        sk = keys.get("SK", "")

        # Only process AGENT items with SK=LATEST
        if not pk.startswith("AGENT#") or sk != "LATEST":
            continue

        agent_id = pk.replace("AGENT#", "")

        if event_name == "REMOVE":
            _delete_from_index(os_client, agent_id)
            continue

        new_image = _unmarshal_ddb(record["dynamodb"].get("NewImage", {}))
        status = new_image.get("status", "")
        visibility = new_image.get("visibility", "")

        # Only index published + public agents
        if status != "published" or visibility != "public":
            _delete_from_index(os_client, agent_id)
            continue

        # Skip re-embedding if the fields that affect vectors haven't changed
        if event_name == "MODIFY":
            old_image = _unmarshal_ddb(record["dynamodb"].get("OldImage", {}))
            if not _embedding_fields_changed(old_image, new_image):
                logger.info(f"Agent {agent_id}: embedding fields unchanged, skipping")
                continue

        _index_agent(os_client, agent_id, new_image)

    return {"statusCode": 200}


def _embedding_fields_changed(old: dict[str, Any], new: dict[str, Any]) -> bool:
    """
    Check if any fields that affect embeddings have changed.
    Only these three fields matter for vector generation:
      - description
      - inputSchema (public fields' names, types, descriptions)
      - outputSchema (public fields' names, types, descriptions)
    """
    if old.get("description", "") != new.get("description", ""):
        return True
    if _fields_to_text(old.get("inputSchema", [])) != _fields_to_text(new.get("inputSchema", [])):
        return True
    if _fields_to_text(old.get("outputSchema", [])) != _fields_to_text(new.get("outputSchema", [])):
        return True
    return False


def _index_agent(os_client: OpenSearch, agent_id: str, item: dict[str, Any]) -> None:
    description = item.get("description", "")
    input_fields = item.get("inputSchema", [])
    output_fields = item.get("outputSchema", [])

    desc_text = description
    input_text = _fields_to_text(input_fields)
    output_text = _fields_to_text(output_fields)

    desc_vector = _embed(desc_text) if desc_text else []
    input_vector = _embed(input_text) if input_text else []
    output_vector = _embed(output_text) if output_text else []

    # Skip if no vectors could be generated (at minimum desc should exist)
    if not desc_vector:
        logger.warning(f"No description for agent {agent_id}, skipping indexing")
        return

    doc: dict[str, Any] = {
        "agent_id": agent_id,
        "name": item.get("name", ""),
        "description": description,
        "status": item.get("status", ""),
        "visibility": item.get("visibility", ""),
        "category": item.get("category", ""),
        "desc_vector": desc_vector,
        "updated_at": item.get("updatedAt", ""),
    }

    # Only include vectors if fields exist (dynamic degradation per ADR)
    if input_vector:
        doc["input_vector"] = input_vector
    if output_vector:
        doc["output_vector"] = output_vector

    os_client.index(index=OPENSEARCH_INDEX, id=agent_id, body=doc)
    logger.info(f"Indexed agent {agent_id}")


def _delete_from_index(os_client: OpenSearch, agent_id: str) -> None:
    try:
        os_client.delete(index=OPENSEARCH_INDEX, id=agent_id)
        logger.info(f"Deleted agent {agent_id} from index")
    except Exception:
        logger.info(f"Agent {agent_id} not in index, nothing to delete")
