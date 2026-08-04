from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass


PHONE_PATTERN = re.compile(r"^\+?[1-9][0-9]{6,14}$")


class UploadValidationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ParseIssue:
    line: int
    value: str
    reason: str


@dataclass(frozen=True)
class ParseResult:
    numbers: tuple[str, ...]
    issues: tuple[ParseIssue, ...]
    blank_count: int
    digest: str

    @property
    def invalid_count(self) -> int:
        return sum(issue.reason == "invalid" for issue in self.issues)

    @property
    def duplicate_count(self) -> int:
        return sum(issue.reason == "duplicate" for issue in self.issues)


def parse_numbers_file(raw: bytes, max_contacts: int = 20_000) -> ParseResult:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise UploadValidationError(
            "invalid_encoding",
            "يجب أن يكون الملف بترميز UTF-8.",
        ) from error

    numbers: list[str] = []
    seen: set[str] = set()
    issues: list[ParseIssue] = []
    blank_count = 0

    for line_number, original_value in enumerate(text.splitlines(), start=1):
        value = original_value.strip()
        if not value:
            blank_count += 1
            continue

        if PHONE_PATTERN.fullmatch(value) is None:
            issues.append(ParseIssue(line_number, value, "invalid"))
            continue

        normalized = f"+{value.removeprefix('+')}"
        if normalized in seen:
            issues.append(ParseIssue(line_number, value, "duplicate"))
            continue

        seen.add(normalized)
        numbers.append(normalized)
        if len(numbers) > max_contacts:
            raise UploadValidationError(
                "too_many_contacts",
                f"يحتوي الملف على أكثر من {max_contacts:,} رقم صالح.",
            )

    if not numbers:
        raise UploadValidationError(
            "no_valid_contacts",
            "لا يحتوي الملف على أي رقم دولي صالح.",
        )

    return ParseResult(
        numbers=tuple(numbers),
        issues=tuple(issues),
        blank_count=blank_count,
        digest=hashlib.sha256(raw).hexdigest(),
    )
