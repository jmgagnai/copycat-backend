"""T16's pure pieces: marker resolution (step 2) and, from step 3 on, the paragraph chunker.
No database."""

import uuid

from chat.citations import (
    CITATION_INSTRUCTIONS,
    MARKER_GROUP,
    resolve_citation_markers,
)
from chat.retrieval import RetrievedChunk
from chat.streaming import AnswerChunker


def chunk(text: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_version_id=uuid.uuid4(),
        filename="report.md",
        heading_path=["Report"],
        text=text,
        chat_snippet=None,
        similarity=0.5,
    )


# Step 2
def test_markers_resolve_only_against_retrieved_chunks() -> None:
    c1, c2 = chunk("one"), chunk("two")
    citations = resolve_citation_markers("A [2]. B [1, 2]. C [9][0].", [c1, c2])
    assert [c.marker for c in citations] == [1, 2]
    assert citations[0].chunk is c1 and citations[1].chunk is c2
    assert citations[0].char_start is None and citations[0].char_end is None


def test_markers_accept_both_bracket_styles_once_each() -> None:
    chunks = [chunk("one"), chunk("two"), chunk("three")]
    assert [m.group(1) for m in MARKER_GROUP.finditer("[1][ 2 ] [1, 3] [x]")] == [
        "1",
        "2",
        "1, 3",
    ]
    citations = resolve_citation_markers("[3] then [3][1] and [1,3]", chunks)
    assert [c.marker for c in citations] == [1, 3]
    assert resolve_citation_markers("No markers here.", chunks) == []
    assert resolve_citation_markers("[1]", []) == []


def test_citation_instructions_name_the_marker_shape() -> None:
    assert (
        "[2]" in CITATION_INSTRUCTIONS and "Never invent one" in CITATION_INSTRUCTIONS
    )


# Step 3
def test_chunker_releases_whole_paragraphs_only() -> None:
    chunker = AnswerChunker()
    assert chunker.push("First para\n\nSecond ") == ["First para"]
    assert chunker.push("para\n\nTail") == ["Second para"]
    assert chunker.flush() == ["Tail"]
    assert chunker.flush() == []


def test_chunker_normalises_line_endings_and_skips_blank_pieces() -> None:
    chunker = AnswerChunker()
    assert chunker.push("## Title\r\n\r\nfirst para\n\n\n\nsecond ") == [
        "## Title",
        "first para",
    ]
    assert chunker.push("para\n\n") == ["second para"]
    assert chunker.push("tail") == [] and chunker.flush() == ["tail"]
    assert AnswerChunker().push("   \n\n  ") == []
