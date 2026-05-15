from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .merged_forward_reader import ForwardLayerNote, ForwardTranscriptEntry


def format_transcript_entry(entry: ForwardTranscriptEntry) -> str:
    sender = entry.sender_name
    if entry.sender_id:
        sender = f"{sender}({entry.sender_id})"
    return f"{'  ' * entry.depth}{sender}: {entry.text}"


def format_transcript_text(
    entries: tuple[ForwardTranscriptEntry, ...],
    notes: tuple[ForwardLayerNote, ...],
) -> str:
    lines = [format_transcript_entry(entry) for entry in entries]
    lines.extend(note.text for note in notes)
    return "\n".join(line for line in lines if line).strip()
