from typing import List, Optional,Union
from pydantic import BaseModel, Field

class GraphApiResponse(BaseModel):
    """A generic response model for Graph API data."""
    status_code: int = Field(..., description="The HTTP status code from the Graph API call.")
    data: Optional[Union[List[dict], dict]] = Field(
        None, description="The JSON data returned from the Graph API as a list or a single object."
    )
    error: Optional[str] = Field(None, description="An error message if the call failed.")
