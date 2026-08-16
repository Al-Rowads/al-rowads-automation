from __future__ import annotations

import pytest

from whatsapp_tracker.parsing import UploadValidationError, parse_numbers_file


def test_parser_normalizes_utf8_bom_and_reports_skipped_lines():
    parsed = parse_numbers_file(
        b"\xef\xbb\xbf+964 750 123 4567\n0751 234 5678\n\n"
        b"00964 750 123 4567\n09-12\n"
    )

    assert parsed.numbers == ("+9647501234567", "+9647512345678")
    assert parsed.blank_count == 1
    assert parsed.duplicate_count == 1
    assert parsed.invalid_count == 1
    assert [(issue.line, issue.reason) for issue in parsed.issues] == [
        (4, "duplicate"),
        (5, "invalid"),
    ]


@pytest.mark.parametrize(
    "value",
    [
        "0750 123 4567",
        "7501234567",
        "9647501234567",
        "+964 750 123 4567",
        "00964\t750 123 4567",
        "+964\u00a0750\u00a0123\u00a04567",
    ],
)
def test_parser_accepts_common_iraqi_mobile_formats(value):
    parsed = parse_numbers_file(f"{value}\n".encode())

    assert parsed.numbers == ("+9647501234567",)


@pytest.mark.parametrize(
    "value",
    [
        "+971501234567",
        "+96407501234567",
        "0750123456",
        "075012345678",
        "0750-123-4567",
    ],
)
def test_parser_rejects_foreign_or_malformed_numbers(value):
    with pytest.raises(UploadValidationError) as error:
        parse_numbers_file(f"{value}\n".encode())

    assert error.value.code == "no_valid_contacts"


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
    content = b"07501234567\n07512345678\n"

    with pytest.raises(UploadValidationError) as error:
        parse_numbers_file(content, max_contacts=1)

    assert error.value.code == "too_many_contacts"


def test_parser_rejects_non_ascii_phone_digits():
    with pytest.raises(UploadValidationError) as error:
        parse_numbers_file("+٩٦٤٧٥٠١٢٣٤٥٦٧\n".encode())

    assert error.value.code == "no_valid_contacts"
