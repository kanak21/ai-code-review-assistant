from typing import Protocol

from code_review_assistant.domain.models.standard import Standard


class StandardsWriter(Protocol):
    async def add_many(
        self,
        organization_id: str,
        standards: tuple[Standard, ...],
    ) -> None:
        """Atomically add standards for one organization."""
        ...