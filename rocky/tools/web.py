import httpx
import logging

logger = logging.getLogger("rocky.tools.web")

async def web_fetch(url: str) -> str:
    """Fetches the content of a web page (GET request)."""
    try:
        logger.info(f"Fetching URL: {url}")
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text[:2000] # return first 2000 chars of HTML/text
    except Exception as e:
        logger.error(f"Failed to fetch url '{url}': {e}")
        return f"Error: Web request failed: {e}"
