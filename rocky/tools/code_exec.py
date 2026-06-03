import sys
import io
import logging
import traceback

logger = logging.getLogger("rocky.tools.code_exec")

async def execute_python(code: str) -> str:
    """Executes a block of Python code in-memory and returns the stdout."""
    logger.info("Executing Python block...")
    old_stdout = sys.stdout
    redirected_output = io.StringIO()
    sys.stdout = redirected_output
    
    try:
        # Define local scope
        local_vars = {}
        exec(code, globals(), local_vars)
        sys.stdout = old_stdout
        return redirected_output.getvalue() or "Python code completed successfully with no stdout."
    except Exception:
        sys.stdout = old_stdout
        return f"Error: Python execution crashed:\n{traceback.format_exc()}"
