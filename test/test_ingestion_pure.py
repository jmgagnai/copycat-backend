"""T13 steps 1 and 2. No database."""

from document.chunk_ranges import ChunkRange, locate_in_markdown
from ingestion.chunking import (
    SEPARATORS,
    chunk_markdown,
    merge_pieces,
    split_into_pieces,
    split_keeping_separator,
)


def test_split_keeping_separator_is_lossless() -> None:
    parts = split_keeping_separator("a. b. c", ". ")
    assert parts == ["a. ", "b. ", "c"]
    assert "".join(parts) == "a. b. c"
    assert split_keeping_separator("abc", "") == ["abc"]


def test_split_into_pieces_recurses_only_into_long_parts() -> None:
    text = "one two three\n\nfour five"
    pieces = split_into_pieces(text, 8, SEPARATORS)
    assert pieces == ["one ", "two ", "three\n", "\n", "four ", "five"]
    assert "".join(pieces) == text
    assert split_into_pieces("abcdefgh", 3, [""]) == ["abc", "def", "gh"]


def test_merge_pieces_overlaps_by_whole_pieces() -> None:
    # "two " is carried whole; "three\n\n" and "four " exceed the overlap, so their tails are.
    chunks = merge_pieces(["one ", "two ", "three\n\n", "four ", "five"], 12, 4)
    assert chunks == ["one two ", "two three\n\n", "ee\n\nfour ", "our five"]
    assert all(len(c) <= 12 for c in chunks)
    assert merge_pieces(["ab", "cd"], 10, 0) == ["abcd"]


def test_merge_pieces_takes_a_tail_when_one_piece_exceeds_the_overlap() -> None:
    # A single 8-character piece with a 3-character overlap: the next chunk starts with its tail.
    assert merge_pieces(["abcdefgh", "ij"], 8, 3) == ["abcdefgh", "fghij"]


def test_merge_pieces_gives_up_overlap_before_size() -> None:
    # The carried overlap ("cd" + "ef") plus the 7-character piece would exceed 8: pieces are
    # dropped from the front, then the last one is cut, so the size always holds.
    chunks = merge_pieces(["ab", "cd", "ef", "ghijklm"], 8, 4)
    assert chunks == ["abcdef", "fghijklm"]
    assert all(len(c) <= 8 for c in chunks)
    # No room at all: the overlap disappears entirely.
    assert merge_pieces(["ab", "cd", "efghijkl"], 8, 4) == ["abcd", "efghijkl"]


MARKDOWN = (
    "# A\n\n" + "para one. " * 30 + "\n\n" + "para two. " * 30 + "\n\n# B\n\nshort"
)


def test_chunk_markdown_yields_verbatim_bounded_chunks_with_paths() -> None:
    chunks = chunk_markdown(MARKDOWN, chunk_size=200, chunk_overlap=20)
    assert all(c.text in MARKDOWN for c in chunks)
    assert all(len(c.text) <= 200 for c in chunks)
    assert [c.index for c in chunks] == list(range(len(chunks)))
    assert chunks[-1].heading_path == ["B"] and chunks[-1].text == "short"
    assert all(c.heading_path == ["A"] for c in chunks[:-1])
    assert len(chunks) > 3


def test_consecutive_chunks_of_a_long_section_overlap() -> None:
    chunks = chunk_markdown(MARKDOWN, chunk_size=200, chunk_overlap=20)
    first, second = chunks[0].text, chunks[1].text
    assert first.endswith("para one.") and second.startswith("para one.")
    assert second[: len("para one. para one.")] in first


def test_an_embedded_picture_splits_a_paragraph_in_two() -> None:
    chunks = chunk_markdown("# A\n\nbefore ![Image](data:image/png;base64,AAAA) after")
    assert [c.text for c in chunks] == ["before", "after"]
    # A picture alone in a list item leaves only its bullet behind: not a chunk.
    chunks = chunk_markdown("# A\n\n- ![Image](data:image/png;base64,AAAA)\n- words")
    assert [c.text for c in chunks] == ["- words"]


def test_chunk_markdown_skips_empty_sections_and_clamps_the_overlap() -> None:
    assert chunk_markdown("# Only a heading\n\n## And another") == []
    markdown = "# A\n\nab cd ef gh"
    chunks = chunk_markdown(markdown, chunk_size=5, chunk_overlap=50)
    assert all(len(c.text) <= 5 and c.text in markdown for c in chunks)
    assert chunks[0].text == "ab" and chunks[-1].text.endswith("gh")


# Step 2
def test_locate_in_markdown_moves_a_forward_cursor() -> None:
    assert locate_in_markdown(
        "alpha beta gamma", ["alpha beta", "beta gamma", "zzz"]
    ) == [ChunkRange(0, 10), ChunkRange(6, 16), None]


def test_located_chunks_are_slices_of_the_markdown() -> None:
    markdown = "# A\n\n" + "para one. " * 30 + "\n\n" + "para two. " * 30
    chunks = chunk_markdown(markdown, chunk_size=200, chunk_overlap=20)
    ranges = locate_in_markdown(markdown, [c.text for c in chunks])
    assert all(r is not None for r in ranges)
    for chunk, located in zip(chunks, ranges, strict=True):
        assert located is not None
        assert markdown[located.char_start : located.char_end] == chunk.text
    # Identical texts resolve to successive positions, never the same one twice.
    assert locate_in_markdown("x x x", ["x", "x", "x", "x"]) == [
        ChunkRange(0, 1),
        ChunkRange(2, 3),
        ChunkRange(4, 5),
        None,
    ]
