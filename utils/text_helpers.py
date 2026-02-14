def create_snippet(
    text: str, max_length: int = 250, indicator: str = "..."
) -> tuple[str, bool]:
    """Truncates text intelligently at sentence or word boundaries."""
    if not text or len(text) <= max_length:
        return text, False

    # Try to cut at the last sentence
    end_sentence = text.rfind(".", 0, max_length + 1)
    if end_sentence > max_length * 0.7:
        return text[: end_sentence + 1], True

    # Fallback: cut at the last space
    end_space = text.rfind(" ", 0, max_length + 1)
    if end_space > max_length * 0.7:
        return text[:end_space] + indicator, True

    return text[:max_length] + indicator, True


def split_csv_text(text_content: str) -> list[str]:
    """Splits a comma-separated string (or lines) into a clean list."""
    if not text_content:
        return []
    items = []
    lines = text_content.splitlines()
    for line in lines:
        parts = [part.strip() for part in line.split(",")]
        items.extend(part for part in parts if part)
    return items


def make_url_safe_name(name: str) -> str:
    """Converts a string to a URL-safe slug."""
    if not name:
        return ""
    s = name.lower().replace("&", "and").replace(" ", "-")
    return "".join(c for c in s if c.isalnum() or c == "-")
