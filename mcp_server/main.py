from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app.server import mcp


if __name__ == "__main__":
    mcp.run(transport="sse")
