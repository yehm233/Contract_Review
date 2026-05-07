import os

MYSQL_DSN = os.getenv("DATABASE_URL", "mysql+aiomysql://root:password@172.27.3.6:3306/contract_review")
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "172.27.3.6:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "contracts")
MCP_HTTP_BASE = os.getenv("MCP_HTTP_BASE", "http://127.0.0.1:8000")
