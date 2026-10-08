"""
application/policies/classification.py
--------------------------------------
Safety policy classification for application capabilities.
Defines PolicyClass enum: READ, WRITE, EXTERNAL_ACTION.
"""

from enum import Enum


class PolicyClass(str, Enum):
    """
    Safety classification controlling agent execution permissions.

    - READ: Zero side-effects. Safe for autonomous execution in agent loops.
    - WRITE: Local state mutation (staging records, saving internal drafts).
             Restricted execution with schema validation and idempotency keys.
    - EXTERNAL_ACTION: Operations with external real-world impact (dispatching emails,
                       WhatsApp, external webhooks). STRICTLY requires human approval.
    """
    READ = "READ"
    WRITE = "WRITE"
    EXTERNAL_ACTION = "EXTERNAL_ACTION"
