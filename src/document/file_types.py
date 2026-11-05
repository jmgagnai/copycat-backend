ACCEPTED_EXTENSIONS: dict[str, str] = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv": "text/csv",
    ".pdf": "application/pdf",
}

ACCEPTED_TYPES_DESCRIPTION = "text, Markdown, DOCX, Excel (.xlsx), CSV, and PDF"

EXPLAINED_REJECTIONS: dict[str, str] = {
    ".xls": "Legacy Excel (.xls) is not supported; re-save it as .xlsx and upload that.",
}

MAX_UPLOAD_FILE_BYTES = 50 * 1024 * 1024
MAX_UPLOAD_FILE_DESCRIPTION = "50 MiB"


def extension_of(filename: str) -> str:
    dot = filename.rfind(".")
    return "" if dot == -1 else filename[dot:].lower()


def resolve_accepted_mime_type(filename: str) -> str | None:
    return ACCEPTED_EXTENSIONS.get(extension_of(filename))


def describe_rejected_file_type(filename: str) -> str:
    explained = EXPLAINED_REJECTIONS.get(extension_of(filename))
    if explained:
        return f'Unsupported file type for "{filename}". {explained}'
    return f'Unsupported file type for "{filename}". Accepted types: {ACCEPTED_TYPES_DESCRIPTION}.'
