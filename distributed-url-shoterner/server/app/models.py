from pydantic import BaseModel , HttpUrl
from typing import Optional

class ShortenRequest(BaseModel):
    url: HttpUrl

class ShortenResponse(BaseModel):
    short_id :str
    short_url : str
    url : HttpUrl
    created_at : Optional[int]