"""
Create (or verify) the OpenSearch index for agent vector search.

Three vectors per agent (HNSW kNN):
  - desc_vector:   embedded from agent description
  - input_vector:  embedded from alphabetically sorted input field descriptions
  - output_vector: embedded from alphabetically sorted output field descriptions

Usage:
    python scripts/create_opensearch_index.py
    python scripts/create_opensearch_index.py --endpoint https://my-domain.us-east-1.es.amazonaws.com
"""

import argparse
import json
import sys

import boto3
from botocore.exceptions import ClientError
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

INDEX_NAME = "agent_vectors"
VECTOR_DIM = 1024  # Titan Embeddings V2 dimension

INDEX_BODY = {
    "settings": {
        "index": {
            "knn": True,
            "knn.algo_param.ef_search": 100,
        }
    },
    "mappings": {
        "properties": {
            "agent_id": {"type": "keyword"},
            "name": {"type": "text"},
            "description": {"type": "text"},
            "status": {"type": "keyword"},
            "visibility": {"type": "keyword"},
            "category": {"type": "keyword"},
            "desc_vector": {
                "type": "knn_vector",
                "dimension": VECTOR_DIM,
                "method": {
                    "name": "hnsw",
                    "space_type": "cosinesimil",
                    "engine": "nmslib",
                    "parameters": {"ef_construction": 256, "m": 48},
                },
            },
            "input_vector": {
                "type": "knn_vector",
                "dimension": VECTOR_DIM,
                "method": {
                    "name": "hnsw",
                    "space_type": "cosinesimil",
                    "engine": "nmslib",
                    "parameters": {"ef_construction": 256, "m": 48},
                },
            },
            "output_vector": {
                "type": "knn_vector",
                "dimension": VECTOR_DIM,
                "method": {
                    "name": "hnsw",
                    "space_type": "cosinesimil",
                    "engine": "nmslib",
                    "parameters": {"ef_construction": 256, "m": 48},
                },
            },
            "updated_at": {"type": "date"},
        }
    },
}


def get_client(endpoint: str, region: str) -> OpenSearch:
    credentials = boto3.Session().get_credentials()
    awsauth = AWS4Auth(
        credentials.access_key,
        credentials.secret_key,
        region,
        "es",
        session_token=credentials.token,
    )
    return OpenSearch(
        hosts=[{"host": endpoint.replace("https://", ""), "port": 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Create OpenSearch agent_vectors index.")
    parser.add_argument("--endpoint", required=True, help="OpenSearch domain endpoint URL")
    parser.add_argument("--region", default="us-east-1", help="AWS region (default: us-east-1)")
    parser.add_argument("--index", default=INDEX_NAME, help=f"Index name (default: {INDEX_NAME})")
    args = parser.parse_args()

    client = get_client(args.endpoint, args.region)

    if client.indices.exists(index=args.index):
        print(f"Index '{args.index}' already exists — skipping creation.")
        mapping = client.indices.get_mapping(index=args.index)
        print(json.dumps(mapping, indent=2))
        sys.exit(0)

    print(f"Creating index '{args.index}' …")
    try:
        client.indices.create(index=args.index, body=INDEX_BODY)
        print(f"Index '{args.index}' created successfully.")
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # Verify
    mapping = client.indices.get_mapping(index=args.index)
    print(json.dumps(mapping, indent=2))
    print("\nDone. Index is ready.")


if __name__ == "__main__":
    main()
