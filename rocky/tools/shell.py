import asyncio
import logging

logger = logging.getLogger("rocky.tools.shell")

async def run_command(command: str) -> str:
    """Executes a command inside the WSL terminal environment (non-blocking)."""
    try:
        logger.info(f"Running shell command: {command}")
        # Run under shell
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        
        output = stdout.decode(errors="replace")
        error = stderr.decode(errors="replace")
        
        result = ""
        if output:
            result += f"Output:\n{output}\n"
        if error:
            result += f"Stderr:\n{error}\n"
        if not result:
            result = "Command completed with no output."
            
        return result
    except Exception as e:
        logger.error(f"Failed to run shell command '{command}': {e}")
        return f"Error: Command failed to execute: {e}"
