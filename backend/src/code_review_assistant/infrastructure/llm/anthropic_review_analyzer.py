from collections.abc import Sequence
from typing import Protocol

from code_review_assistant.application.models.review_analysis import ReviewAnalysis
from code_review_assistant.application.ports.review_analyzer import ReviewAnalyzer
from code_review_assistant.domain.models.changed_file import ChangedFile
from code_review_assistant.domain.models.review_finding import Severity
from code_review_assistant.domain.models.review_run import ReviewRun
from code_review_assistant.domain.models.standard import Standard
from code_review_assistant.infrastructure.llm.review_request import (
    SYSTEM_PROMPT,
    prepare_review_request,
)
from code_review_assistant.infrastructure.llm.review_response import (
    parse_review_payload,
)


_TOOL_NAME = "submit_review"


class _ToolUseBlock(Protocol):
    type: str
    name: str
    input: object


class _MessageResponse(Protocol):
    content: Sequence[_ToolUseBlock]


class _MessagesResource(Protocol):
    async def create(self, **kwargs: object) -> _MessageResponse: ...


class _AnthropicClient(Protocol):
    messages: _MessagesResource


class AnthropicReviewAnalyzer(ReviewAnalyzer):
    def __init__(
        self,
        client: _AnthropicClient,
        model: str,
        max_tokens: int = 4096,
    ) -> None:
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must not be empty")
        if (
            isinstance(max_tokens, bool)
            or not isinstance(max_tokens, int)
            or max_tokens < 1
        ):
            raise ValueError("max_tokens must be a positive integer")

        self._client = client
        self._model = model
        self._max_tokens = max_tokens

    async def analyze(
        self,
        run: ReviewRun,
        changed_files: tuple[ChangedFile, ...],
        standards: tuple[Standard, ...],
    ) -> ReviewAnalysis:
        if not isinstance(run, ReviewRun):
            raise ValueError("run must be a ReviewRun")
        if not isinstance(changed_files, tuple) or not all(
            isinstance(file, ChangedFile) for file in changed_files
        ):
            raise ValueError("changed_files must be a tuple of ChangedFile objects")
        if not isinstance(standards, tuple) or not all(
            isinstance(standard, Standard) for standard in standards
        ):
            raise ValueError("standards must be a tuple of Standard objects")

        prepared = prepare_review_request(changed_files, standards)
        if prepared.request_json is None:
            return ReviewAnalysis(prepared.analyzed_paths, (), ())

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prepared.request_json}],
            tools=[
                {
                    "name": _TOOL_NAME,
                    "description": "Submit evidence-backed code review findings.",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "findings": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "rule_id": {"type": "string"},
                                        "standard_id": {"type": "string"},
                                        "severity": {
                                            "type": "string",
                                            "enum": [
                                                severity.value
                                                for severity in Severity
                                            ],
                                        },
                                        "title": {"type": "string"},
                                        "rationale": {"type": "string"},
                                        "file_path": {"type": "string"},
                                        "start_line": {"type": "integer"},
                                        "end_line": {"type": "integer"},
                                        "evidence": {"type": "string"},
                                    },
                                    "required": [
                                        "rule_id",
                                        "standard_id",
                                        "severity",
                                        "title",
                                        "rationale",
                                        "file_path",
                                        "start_line",
                                        "end_line",
                                        "evidence",
                                    ],
                                    "additionalProperties": False,
                                },
                            }
                        },
                        "required": ["findings"],
                        "additionalProperties": False,
                    },
                }
            ],
            tool_choice={"type": "tool", "name": _TOOL_NAME},
        )

        tool_blocks = tuple(
            block for block in response.content if block.type == "tool_use"
        )
        if (
            len(tool_blocks) != 1
            or tool_blocks[0].name != _TOOL_NAME
            or not isinstance(tool_blocks[0].input, dict)
        ):
            raise RuntimeError("model did not return the required review tool response")

        return parse_review_payload(
            tool_blocks[0].input,
            prepared.analyzed_paths,
            prepared.added_by_path,
            standards,
        )