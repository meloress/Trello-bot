from aiohttp import web


def err(message: str, status: int = 400) -> web.Response:
    return web.json_response({"error": message}, status=status)
