"""
application/contracts/base.py
-----------------------------
Generic capability result envelope.
Provides typed execution status, payload, and error encapsulation for agent tool calls.
"""

from typing import TypeVar, Generic, Optional, Dict, Any
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class CapabilityResult(BaseModel, Generic[T]):
    """
    Standardized result envelope for all capability tool executions.
    """
    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)

    success: bool = Field(..., description="Whether the capability executed without fatal errors")
    capability_name: str = Field(..., description="Stable name of the executed capability")
    data: Optional[T] = Field(default=None, description="Typed output payload upon success")
    error: Optional[str] = Field(default=None, description="Descriptive error message upon failure")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Execution metadata (duration, policy class, etc.)")
