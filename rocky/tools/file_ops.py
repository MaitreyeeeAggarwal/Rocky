import os
import logging
from pathlib import Path

logger = logging.getLogger("rocky.tools.file_ops")

async def write_file(filename: str, content: str) -> str:
    """Writes content to a file in the active workspace directory."""
    try:
        path = Path(filename)
        # Block writing to system files outside workspace
        if path.is_absolute() and not str(path).startswith(os.getcwd()):
            return f"Error: Permission denied. Cannot write outside workspace: {filename}"
            
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        logger.info(f"File written successfully: {filename}")
        return f"File '{filename}' written successfully."
    except Exception as e:
        logger.error(f"Failed to write file '{filename}': {e}")
        return f"Error: Failed to write file: {e}"

async def read_file(filename: str) -> str:
    """Reads content from a file in the active workspace directory."""
    try:
        path = Path(filename)
        if not path.exists():
            return f"Error: File not found: {filename}"
        return path.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"Failed to read file '{filename}': {e}")
        return f"Error: Failed to read file: {e}"
