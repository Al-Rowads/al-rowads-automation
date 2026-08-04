from __future__ import annotations

import pytest

from whatsapp_tracker.parsing import UploadValidationError, parse_numbers_file


def test_parser_normalizes_utf8_bom_and_reports_skipped_lines():
    parsed = parse_numbers_file(
        b"\xef\xbb\xbf+989121234567\n971501234567\n\n+989121234567\n09-12\n"
    )

    assert parsed.numbers == ("+989121234567", "+971501234567")
    assert parsed.blank_count == 1
    assert parsed.duplicate_count == 1
    assert parsed.invalid_count == 1
    assert [(issue.line, issue.reason) for issue in parsed.issues] == [
        (4, "duplicate"),
        (5, "invalid"),
    ]


@pytest.mark.parametrize(
    "content, code",
    [
        (b"not-a-phone\n", "no_valid_contacts"),
        (b"\xff\xfe\x00\x00", "invalid_encoding"),
    ],
)
def test_parser_rejects_files_without_valid_utf8_numbers(content, code):
    with pytest.raises(UploadValidationError) as error:
        parse_numbers_file(content)

    assert error.value.code == code


def test_parser_enforces_contact_limit():
    content = b"+12025550101\n+12025550102\n"

    with pytest.raises(UploadValidationError) as error:
        parse_numbers_file(content, max_contacts=1)

    assert error.value.code == "too_many_contacts"


def test_parser_rejects_non_ascii_phone_digits():
    with pytest.raises(UploadValidationError) as error:
        parse_numbers_file("+٩٨٩١٢١٢٣٤٥٦٧\n".encode())

    assert error.value.code == "no_valid_contacts"
