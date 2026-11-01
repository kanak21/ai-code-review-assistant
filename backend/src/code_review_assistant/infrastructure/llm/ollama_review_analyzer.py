import json

import httpx

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


_FINDING_FIELDS = (
    "rule_id",
    "standard_id",
    "severity",
    "title",
    "rationale",
    "file_path",
    "start_line",
    "end_line",
    "evidence",
)

_RESPONSE_SCHEMA = {
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
                        "enum": [severity.value for severity in Severity],
                    },
                    "title": {"type": "string"},
                    "rationale": {"type": "string"},
                    "file_path": {"type": "string"},
                    "start_line": {"type": "integer"},
                    "end_line": {"type": "integer"},
                    "evidence": {
                        "type": "string",
                        "description": (
                            "Exact source content from the added line, without diff "
                            "markers, quotes, or paraphrasing."
                        ),
                    },
                },
                "required": list(_FINDING_FIELDS),
                "additionalProperties": False,
            },
        }
    },
    "required": ["findings"],
    "additionalProperties": False,
}


def _response_schema(
    added_by_path: dict[str, dict[int, str]],
) -> dict[str, object]:
    paths = sorted(path for path, lines in added_by_path.items() if lines)
    line_numbers = sorted(
        {line for lines in added_by_path.values() for line in lines}
    )
    evidence_values = sorted(
        {content for lines in added_by_path.values() for content in lines.values()}
    )

    properties: dict[str, object] = {
        "rule_id": {"type": "string"},
        "standard_id": {"type": "string"},
        "severity": {
            "type": "string",
            "enum": [severity.value for severity in Severity],
        },
        "title": {"type": "string"},
        "rationale": {"type": "string"},
        "file_path": {"type": "string", "enum": paths},
        "start_line": {"type": "integer", "enum": line_numbers},
        "end_line": {"type": "integer", "enum": line_numbers},
        "evidence": {"type": "string", "enum": evidence_values},
    }

    return {
        "type": "object",
        "properties": {
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": properties,
                    "required": list(_FINDING_FIELDS),
                    "additionalProperties": False,
                },
            }
        },
        "required": ["findings"],
        "additionalProperties": False,
    }


class OllamaReviewAnalyzer(ReviewAnalyzer):
    def __init__(
        self,
        http_client: httpx.AsyncClient,
        base_url: str,
        model: str,
    ) -> None:
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError("base_url must not be empty")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must not be empty")

        self._http_client = http_client
        self._url = f"{base_url.rstrip('/')}/api/chat"
        self._model = model

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

        response = await self._http_client.post(
            self._url,
            json={
                "model": self._model,
                "stream": False,
                "format": _response_schema(prepared.added_by_path),
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prepared.request_json},
                ],
            },
        )
        response.raise_for_status()

        response_data = response.json()
        if not isinstance(response_data, dict):
            raise RuntimeError("Ollama returned an invalid chat response")

        message = response_data.get("message")
        if not isinstance(message, dict):
            raise RuntimeError("Ollama chat response has no message")

        content = message.get("content")
        if not isinstance(content, str):
            raise RuntimeError("Ollama chat response has no text content")

        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Ollama returned malformed review JSON") from exc

        return parse_review_payload(
            payload,
            prepared.analyzed_paths,
            prepared.added_by_path,
            standards,
        )