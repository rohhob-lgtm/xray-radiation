"""File processors for the AI Chat Workspace agent.

Each processor takes raw bytes and returns the standardized result shape:

    {
        "filePath": str, "fileType": str, "text": str, "metadata": dict,
        "tables": list, "images": list, "slides": list, "sheets": list,
        "warnings": list, "errors": list,
    }

A processor failure never raises past its own module — callers get an
``errors``-populated result instead, so one bad file cannot abort a batch.
"""
