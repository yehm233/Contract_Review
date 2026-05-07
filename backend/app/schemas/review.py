from pydantic import BaseModel


class ReviewStartRequest(BaseModel):
    contract_id: str
