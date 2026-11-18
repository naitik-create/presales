"""Split extracted segments into retrieval chunks that keep their section path and page (§6.3)."""
from dataclasses import dataclass

from app.parsing.extract import Segment


@dataclass
class Chunk:
    text: str
    section_path: str
    page: str


def _pieces(text: str, size: int) -> list[str]:
    out = []
    while len(text) > size:  # very long paragraph: split on whitespace
        cut = text.rfind(" ", 0, size)
        cut = cut if cut > size // 2 else size
        out.append(text[:cut])
        text = text[cut:].lstrip()
    if text:
        out.append(text)
    return out


def chunk_segments(segments: list[Segment], size: int = 1800, overlap: int = 200) -> list[Chunk]:
    """Chunks never cross a section boundary. Consecutive chunks in one section share `overlap` characters."""
    chunks: list[Chunk] = []
    groups: list[tuple[str, list[tuple[str, str]]]] = []
    for seg in segments:
        if not groups or groups[-1][0] != seg.section:
            groups.append((seg.section, []))
        groups[-1][1].extend((p, seg.ref) for p in _pieces(seg.text, size))

    for section, pieces in groups:
        buf: list[str] = []
        length = 0
        ref = ""
        for text, piece_ref in pieces:
            if buf and length + len(text) > size:
                body = "\n".join(buf)
                chunks.append(Chunk(body, section, ref))
                tail = body[-overlap:] if overlap else ""
                buf, length, ref = ([tail] if tail else []), len(tail), ""
            if not ref:
                ref = piece_ref
            buf.append(text)
            length += len(text) + 1
        if buf:
            body = "\n".join(buf)
            if not chunks or chunks[-1].section_path != section or len(body) > overlap:
                chunks.append(Chunk(body, section, ref))
    return chunks
