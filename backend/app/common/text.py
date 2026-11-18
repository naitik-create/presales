import re


def normalise(text: str) -> str:
    """Lower-case, strip punctuation and collapse whitespace, for comparing requirement texts."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", text.lower())).strip()
