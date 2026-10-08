"""
agent/policies.py
-----------------
Policy enforcement for Agent capability execution.
Enforces safety invariants across READ, WRITE, and EXTERNAL_ACTION classes.
Prevents execution of unregistered capabilities or unauthorized side-effects.
"""

import logging
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

from application.policies.classification import PolicyClass
from application.capabilities.registry import CapabilityDescriptor

logger = logging.getLogger(__name__)


class PolicyViolationError(Exception):
    """Raised when an operation violates configured safety policies."""
    pass


class ExecutionPolicyConfig(BaseModel):
    """
    Configuration parameters governing capability execution safety.
    """
    model_config = ConfigDict(extra="ignore")

    allow_staged_writes: bool = Field(
        default=True,
        description="Whether staged internal writes (e.g. staging drafts) are permitted automatically"
    )
    require_approval_for_write: bool = Field(
        default=False,
        description="If True, even staged writes require human approval before execution"
    )
    require_approval_for_external: bool = Field(
        default=True,
        description="If True, external real-world actions strictly require human approval"
    )


class PolicyEvaluationResult(BaseModel):
    """Result of policy evaluation for a capability."""
    is_allowed: bool
    requires_approval: bool
    policy_class: Optional[PolicyClass] = None
    reason: str


class PolicyEnforcer:
    """
    Evaluates capabilities against safety rules prior to execution.
    """

    def __init__(self, config: Optional[ExecutionPolicyConfig] = None):
        self.config = config or ExecutionPolicyConfig()

    def evaluate(self, descriptor: Optional[CapabilityDescriptor]) -> PolicyEvaluationResult:
        """
        Evaluates whether a capability may execute, requires approval, or is forbidden.
        """
        if descriptor is None:
            return PolicyEvaluationResult(
                is_allowed=False,
                requires_approval=False,
                policy_class=None,
                reason="Capability is not registered in the CapabilityRegistry."
            )

        policy_class = descriptor.policy_class

        if policy_class == PolicyClass.READ:
            return PolicyEvaluationResult(
                is_allowed=True,
                requires_approval=False,
                policy_class=policy_class,
                reason="READ capabilities execute automatically with zero side-effects."
            )

        if policy_class == PolicyClass.WRITE:
            if self.config.allow_staged_writes and not self.config.require_approval_for_write:
                return PolicyEvaluationResult(
                    is_allowed=True,
                    requires_approval=False,
                    policy_class=policy_class,
                    reason="WRITE capability allowed under configured staged-write policy."
                )
            else:
                return PolicyEvaluationResult(
                    is_allowed=False,
                    requires_approval=True,
                    policy_class=policy_class,
                    reason="WRITE capability requires explicit approval under current configuration."
                )

        if policy_class == PolicyClass.EXTERNAL_ACTION:
            if self.config.require_approval_for_external:
                return PolicyEvaluationResult(
                    is_allowed=False,
                    requires_approval=True,
                    policy_class=policy_class,
                    reason="EXTERNAL_ACTION capabilities strictly require human approval."
                )
            return PolicyEvaluationResult(
                is_allowed=True,
                requires_approval=False,
                policy_class=policy_class,
                reason="EXTERNAL_ACTION approved by configuration override."
            )

        return PolicyEvaluationResult(
            is_allowed=False,
            requires_approval=False,
            policy_class=policy_class,
            reason=f"Unknown policy classification: {policy_class}"
        )
