from io import BytesIO

import httpx
from minio import Minio

from app.core.config import MINIO_ACCESS_KEY, MINIO_BUCKET, MINIO_ENDPOINT, MINIO_SECRET_KEY

client = Minio(MINIO_ENDPOINT, access_key=MINIO_ACCESS_KEY, secret_key=MINIO_SECRET_KEY, secure=False)


async def save_onlyoffice_file(file_url: str, key: str) -> str:
    if not client.bucket_exists(MINIO_BUCKET):
        client.make_bucket(MINIO_BUCKET)
    async with httpx.AsyncClient(timeout=30) as hc:
        resp = await hc.get(file_url)
        resp.raise_for_status()
    obj = f"onlyoffice/{key}.docx"
    raw = resp.content
    client.put_object(MINIO_BUCKET, obj, BytesIO(raw), len(raw), content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    return f"minio://{MINIO_BUCKET}/{obj}"
