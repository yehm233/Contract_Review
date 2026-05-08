from pydantic import BaseModel


class ReviewStartRequest(BaseModel):
    contract_id: str
    contract_text: str | None = None
