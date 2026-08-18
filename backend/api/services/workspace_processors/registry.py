"""Extension → processor dispatch.

An unrecognized extension is not an error: the file is still recorded in the
workspace manifest with ``parse_status="unsupported"`` (via the caller), and
the batch continues — "a failure in one file must not terminate the complete
job."
"""
from __future__ import annotations

from .base import make_result
from .code_processor import process_code
from .csv_processor import process_csv
from .excel_processor import process_excel
from .image_processor import process_image
from .pdf_processor import process_pdf
from .pptx_processor import process_pptx
from .text_processor import process_text
from .word_processor import process_word

_TEXT_EXTS = {"txt", "md", "rtf", "log"}
_CODE_EXTS = {
    "py", "js", "jsx", "ts", "tsx", "html", "css", "sql",
    "json", "xml", "yaml", "yml", "ini", "toml", "env",
}
_IMAGE_EXTS = {"png", "jpg", "jpeg", "webp", "tiff", "tif"}
_EXCEL_EXTS = {"xlsx", "xls"}

SUPPORTED_EXTENSIONS = (
    {"pdf", "docx", "pptx", "csv"} | _TEXT_EXTS | _CODE_EXTS | _IMAGE_EXTS | _EXCEL_EXTS
)


def is_supported(extension: str) -> bool:
    return extension.lower().lstrip(".") in SUPPORTED_EXTENSIONS


def process_file(file_path: str, data: bytes, extension: str, *, filename: str = "") -> dict:
    """Dispatch to the matching processor. Never raises — errors are returned
    inside the standardized result dict instead."""
    ext = extension.lower().lstrip(".")
    try:
        if ext == "pdf":
            return process_pdf(file_path, data)
        if ext == "docx":
            return process_word(file_path, data)
        if ext == "pptx":
            return process_pptx(file_path, data)
        if ext in _EXCEL_EXTS:
            return process_excel(file_path, data)
        if ext == "csv":
            return process_csv(file_path, data)
        if ext in _IMAGE_EXTS:
            return process_image(file_path, data)
        if ext in _CODE_EXTS:
            return process_code(file_path, data, extension=ext, filename=filename)
        if ext in _TEXT_EXTS:
            return process_text(file_path, data, filename=filename)
        if ext == "doc" or ext == "ppt":
            return make_result(
                file_path, ext,
                errors=[f"Legacy .{ext} format is not supported — please re-save as .{ext}x."],
            )
        return make_result(
            file_path, ext or "unknown",
            warnings=[f"Unsupported file type '.{ext}' — file was stored but not parsed."],
        )
    except Exception as exc:  # last-resort guard so one bad file never aborts a batch
        return make_result(file_path, ext or "unknown", errors=[f"Unexpected processing error: {exc}"])
