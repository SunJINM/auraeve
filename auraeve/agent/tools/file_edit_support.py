from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


LEFT_SINGLE_CURLY_QUOTE = "‘"
RIGHT_SINGLE_CURLY_QUOTE = "’"
LEFT_DOUBLE_CURLY_QUOTE = "“"
RIGHT_DOUBLE_CURLY_QUOTE = "”"

DESANITIZATIONS: dict[str, str] = {
    "<fnr>": "<function_results>",
    "<n>": "<name>",
    "</n>": "</name>",
    "<o>": "<output>",
    "</o>": "</output>",
    "<e>": "<error>",
    "</e>": "</error>",
    "<s>": "<system>",
    "</s>": "</system>",
    "<r>": "<result>",
    "</r>": "</result>",
    "< META_START >": "<META_START>",
    "< META_END >": "<META_END>",
    "< EOT >": "<EOT>",
    "< META >": "<META>",
    "< SOS >": "<SOS>",
    "\n\nH:": "\n\nHuman:",
    "\n\nA:": "\n\nAssistant:",
}


@dataclass(slots=True)
class TextFileMetadata:
    content: str
    file_exists: bool
    encoding: str
    line_endings: str


def read_text_file_with_metadata(file_path: str) -> TextFileMetadata:
    path = Path(file_path)
    if not path.exists():
        return TextFileMetadata(content="", file_exists=False, encoding="utf-8", line_endings="LF")

    raw_bytes = path.read_bytes()
    encoding = detect_text_encoding(raw_bytes)
    if encoding == "utf-8-sig":
        raw_text = raw_bytes.decode("utf-8-sig")
    else:
        raw_text = raw_bytes.decode(encoding)

    return TextFileMetadata(
        content=raw_text.replace("\r\n", "\n"),
        file_exists=True,
        encoding=encoding,
        line_endings=detect_line_endings(raw_text),
    )


def write_text_with_metadata(
    file_path: str,
    content: str,
    *,
    encoding: str,
    line_endings: str,
) -> None:
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    to_write = content
    if line_endings == "CRLF":
        to_write = content.replace("\r\n", "\n").replace("\n", "\r\n")
    encoded = to_write.encode("utf-8-sig" if encoding == "utf-8-sig" else encoding)
    path.write_bytes(encoded)


def detect_text_encoding(raw_bytes: bytes) -> str:
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if raw_bytes.startswith(b"\xff\xfe"):
        return "utf-16le"
    return "utf-8"


def detect_line_endings(raw_text: str) -> str:
    crlf_count = raw_text.count("\r\n")
    lf_count = raw_text.count("\n") - crlf_count
    return "CRLF" if crlf_count > lf_count else "LF"


def strip_trailing_whitespace(text: str) -> str:
    parts = re.split(r"(\r\n|\n|\r)", text)
    result: list[str] = []
    for index, part in enumerate(parts):
        if index % 2 == 0:
            result.append(re.sub(r"\s+$", "", part))
        else:
            result.append(part)
    return "".join(result)


def normalize_quotes(text: str) -> str:
    return (
        text.replace(LEFT_SINGLE_CURLY_QUOTE, "'")
        .replace(RIGHT_SINGLE_CURLY_QUOTE, "'")
        .replace(LEFT_DOUBLE_CURLY_QUOTE, '"')
        .replace(RIGHT_DOUBLE_CURLY_QUOTE, '"')
    )


def find_actual_string(file_content: str, search_string: str) -> str | None:
    if file_content.find(search_string) != -1:
        return search_string

    normalized_search = normalize_quotes(search_string)
    normalized_file = normalize_quotes(file_content)
    search_index = normalized_file.find(normalized_search)
    if search_index == -1:
        return None
    return file_content[search_index : search_index + len(search_string)]


def preserve_quote_style(old_string: str, actual_old_string: str, new_string: str) -> str:
    if old_string == actual_old_string:
        return new_string

    has_double_quotes = (
        LEFT_DOUBLE_CURLY_QUOTE in actual_old_string or RIGHT_DOUBLE_CURLY_QUOTE in actual_old_string
    )
    has_single_quotes = (
        LEFT_SINGLE_CURLY_QUOTE in actual_old_string or RIGHT_SINGLE_CURLY_QUOTE in actual_old_string
    )

    result = new_string
    if has_double_quotes:
        result = _apply_curly_double_quotes(result)
    if has_single_quotes:
        result = _apply_curly_single_quotes(result)
    return result


def apply_edit_to_file(
    original_content: str,
    old_string: str,
    new_string: str,
    *,
    replace_all: bool = False,
) -> str:
    if replace_all:
        replacer = lambda source, old, new: source.replace(old, new)
    else:
        replacer = lambda source, old, new: source.replace(old, new, 1)

    if new_string != "":
        return replacer(original_content, old_string, new_string)

    strip_trailing_newline = (
        not old_string.endswith("\n") and f"{old_string}\n" in original_content
    )
    if strip_trailing_newline:
        return replacer(original_content, f"{old_string}\n", new_string)
    return replacer(original_content, old_string, new_string)


def normalize_edit_strings(
    *,
    file_path: str,
    file_content: str | None,
    old_string: str,
    new_string: str,
) -> tuple[str, str]:
    normalized_new = new_string if _is_markdown_path(file_path) else strip_trailing_whitespace(new_string)
    if file_content is None or old_string in file_content:
        return old_string, normalized_new

    desanitized_old, replacements = _desanitize_match_string(old_string)
    if desanitized_old in file_content:
        desanitized_new = normalized_new
        for old_value, new_value in replacements:
            desanitized_new = desanitized_new.replace(old_value, new_value)
        return desanitized_old, desanitized_new

    return old_string, normalized_new


def _desanitize_match_string(match_string: str) -> tuple[str, list[tuple[str, str]]]:
    result = match_string
    applied: list[tuple[str, str]] = []
    for old_value, new_value in DESANITIZATIONS.items():
        updated = result.replace(old_value, new_value)
        if updated != result:
            applied.append((old_value, new_value))
            result = updated
    return result, applied


def _is_markdown_path(file_path: str) -> bool:
    lowered = file_path.lower()
    return lowered.endswith(".md") or lowered.endswith(".mdx")


def _apply_curly_double_quotes(text: str) -> str:
    chars = list(text)
    result: list[str] = []
    for index, char in enumerate(chars):
        if char == '"':
            result.append(LEFT_DOUBLE_CURLY_QUOTE if _is_opening_context(chars, index) else RIGHT_DOUBLE_CURLY_QUOTE)
        else:
            result.append(char)
    return "".join(result)


def _apply_curly_single_quotes(text: str) -> str:
    chars = list(text)
    result: list[str] = []
    for index, char in enumerate(chars):
        if char != "'":
            result.append(char)
            continue

        prev_char = chars[index - 1] if index > 0 else ""
        next_char = chars[index + 1] if index < len(chars) - 1 else ""
        if prev_char.isalpha() and next_char.isalpha():
            result.append(RIGHT_SINGLE_CURLY_QUOTE)
            continue

        result.append(LEFT_SINGLE_CURLY_QUOTE if _is_opening_context(chars, index) else RIGHT_SINGLE_CURLY_QUOTE)
    return "".join(result)


def _is_opening_context(chars: list[str], index: int) -> bool:
    if index == 0:
        return True
    prev_char = chars[index - 1]
    return prev_char in {" ", "\t", "\n", "\r", "(", "[", "{", "—", "–"}
