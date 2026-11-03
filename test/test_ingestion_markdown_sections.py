"""T12 step 1. No database."""

from ingestion.markdown_sections import split_markdown_sections


def test_heading_paths_skip_fences_and_empty_preamble() -> None:
    sections = split_markdown_sections(
        "Preamble\n\n# Report\n\n## Risks\n\ntext\n\n```\n# not a heading\n```\n"
    )
    assert [s.heading_path for s in sections] == [[], ["Report"], ["Report", "Risks"]]
    assert [s.heading for s in sections] == [None, "Report", "Risks"]
    assert [s.level for s in sections] == [0, 1, 2]
    assert sections[0].content == "Preamble"
    assert sections[1].content == ""
    assert sections[2].content == "text\n\n```\n# not a heading\n```"


def test_path_length_follows_nesting() -> None:
    sections = split_markdown_sections("# A\n## B\n### C\n## D\n")
    assert [len(s.heading_path) for s in sections] == [1, 2, 3, 2]
    assert sections[-1].heading_path == ["A", "D"]


def test_no_empty_preamble_section() -> None:
    assert [s.heading for s in split_markdown_sections("# Only\n\nbody")] == ["Only"]
    assert split_markdown_sections("") == []


def test_closing_hashes_and_skipped_levels() -> None:
    sections = split_markdown_sections("# Title ##\n### Deep\n")
    assert sections[0].heading == "Title"
    assert sections[1].heading_path == ["Title", "Deep"]
