"""
MCP Gateway configuration — loaded from environment variables.
"""

import os


OPENSEARCH_ENDPOINT = os.environ.get("OPENSEARCH_ENDPOINT", "")
OPENSEARCH_INDEX = os.environ.get("OPENSEARCH_INDEX", "agent_vectors")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
DYNAMODB_TABLE_NAME = os.environ.get("DYNAMODB_TABLE_NAME", "AgentMarketplace")
EMBEDDING_MODEL_ID = os.environ.get("EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0")

# Score thresholds for 3-path routing
THRESHOLD_DIRECT = 0.85
THRESHOLD_INDIRECT = 0.50

# Search limits
MAX_SEARCH_RESULTS = 20
MAX_COMPARISON_AGENTS = 5
