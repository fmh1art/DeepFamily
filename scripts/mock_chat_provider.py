from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, cast

HOST = "127.0.0.1"
PORT = 9000
EXPECTED_PATH = "/v1/chat/completions?api-version=smoke"
EXPECTED_MODEL = "askdu-model-smoke"
EXPECTED_API_KEY = "smoke-key"  # Fixed non-secret test sentinel.
MAX_REQUEST_BYTES = 2 * 1024 * 1024
TARGET_ASSET_NAME = "D5 SHSAT Registrations and Testers.csv"
CATALOG_FIELDS = {"asset_id", "name", "relative_path", "columns", "byte_size"}


class SmokeProviderHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        if self.path == "/readyz":
            self._send(HTTPStatus.OK, {"status": "ready"})
            return
        self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:
        try:
            plan = self._validate_and_plan()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            self._send(HTTPStatus.BAD_REQUEST, {"error": "invalid smoke request"})
            return

        completion = {
            "id": "chatcmpl-local-model-smoke",
            "object": "chat.completion",
            "created": 0,
            "model": EXPECTED_MODEL,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(plan, separators=(",", ":")),
                    },
                    "finish_reason": "stop",
                }
            ],
        }
        self._send(HTTPStatus.OK, completion)

    def _validate_and_plan(self) -> dict[str, Any]:
        if self.path != EXPECTED_PATH:
            raise ValueError("unexpected path")
        if self.headers.get("api-key") != EXPECTED_API_KEY:
            raise ValueError("unexpected authentication")
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise ValueError("missing content length")
        length = int(raw_length)
        if not 0 < length <= MAX_REQUEST_BYTES:
            raise ValueError("invalid content length")
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(payload, dict) or payload.get("model") != EXPECTED_MODEL:
            raise ValueError("unexpected model payload")
        if payload.get("max_completion_tokens") != 8_000:
            raise ValueError("unexpected token bound")
        messages = payload.get("messages")
        if not isinstance(messages, list) or len(messages) != 2:
            raise ValueError("unexpected messages")
        roles = [
            message.get("role") for message in messages if isinstance(message, dict)
        ]
        if roles != ["system", "user"]:
            raise ValueError("unexpected message roles")
        user_message = cast(dict[str, Any], messages[1]).get("content")
        if not isinstance(user_message, str):
            raise TypeError("missing user message")
        request = json.loads(user_message)
        if not isinstance(request, dict):
            raise TypeError("planner request is not an object")
        base_fields = {"question", "catalog", "plan_schema"}
        request_fields = set(request)
        if request_fields == base_fields:
            is_correction = False
        elif request_fields == base_fields | {"validation_feedback", "instruction"}:
            is_correction = True
            feedback = request.get("validation_feedback")
            if (
                not isinstance(feedback, str)
                or not feedback.strip()
                or len(feedback) > 1_000
                or EXPECTED_API_KEY in feedback
            ):
                raise ValueError("expected bounded credential-free validation feedback")
            if request.get("instruction") != (
                "Return a corrected complete object. Do not repeat the invalid response."
            ):
                raise ValueError("unexpected correction instruction")
        else:
            raise ValueError("planner request contains an unexpected field")
        question = request.get("question")
        if question != "How many Grade 8 SHSAT registration rows are present in 2016?":
            raise ValueError("unexpected question")
        catalog = request.get("catalog")
        if not isinstance(catalog, list) or not catalog:
            raise TypeError("catalog is missing")
        if any(
            not isinstance(asset, dict) or set(asset) != CATALOG_FIELDS
            for asset in catalog
        ):
            raise ValueError(
                "catalog contains rows, credentials, or an unexpected field"
            )
        registration = next(
            asset for asset in catalog if asset.get("name") == TARGET_ASSET_NAME
        )
        columns = registration.get("columns")
        if not isinstance(columns, list) or not {
            "Year of SHST",
            "Grade level",
        }.issubset(columns):
            raise ValueError("required metadata is absent")
        asset_id = registration.get("asset_id")
        if not isinstance(asset_id, str) or not asset_id:
            raise ValueError("asset id is absent")
        plan = build_plan(asset_id)
        if not is_correction:
            plan["sources"][0]["asset_id"] = "asset_not_authorized"
        return plan

    def _send(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:
        return


def build_plan(asset_id: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "summary": "Count Grade 8 SHSAT registration rows in 2016.",
        "search_terms": ["SHSAT", "Grade level", "2016"],
        "sources": [
            {
                "alias": "registrations",
                "asset_id": asset_id,
                "required_columns": ["Year of SHST", "Grade level"],
                "purpose": "Grade-level SHSAT registration records",
            }
        ],
        "preparation": [
            {
                "type": "filter",
                "input_table": "registrations",
                "output_table": "grade8_2016",
                "predicates": [
                    {"column": "Year of SHST", "operator": "eq", "value": 2016},
                    {"column": "Grade level", "operator": "eq", "value": 8},
                ],
                "combine": "all",
            }
        ],
        "analyses": [
            {
                "type": "aggregate",
                "name": "grade8_2016_rows",
                "table": "grade8_2016",
                "function": "count_rows",
                "unit": "rows",
                "display_precision": 0,
            }
        ],
        "primary_table": "grade8_2016",
        "report_title": "Grade 8 SHSAT registrations in 2016",
    }


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), SmokeProviderHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
