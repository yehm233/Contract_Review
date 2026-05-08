import os

MYSQL_DSN = os.getenv("DATABASE_URL", "mysql+aiomysql://root:password@172.27.3.6:3306/contract_review")
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "172.27.3.6:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "contracts")
MCP_HTTP_BASE = os.getenv("MCP_HTTP_BASE", "http://127.0.0.1:8000")
MCP_SSE_URL = os.getenv("MCP_SSE_URL", f"{MCP_HTTP_BASE}/sse")
REVIEW_WORKFLOW_MODE = os.getenv("REVIEW_WORKFLOW_MODE", "langchain")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
