# Project notes

## Overrides of the global file

The build prompt sets these rules for this repo.

1. Use `requirements.txt`, not `pyproject.toml`.
2. Keep every file at the repo root. Loguru writes to stderr only.
3. Use a FastMCP server and a client script. Do not add FastAPI endpoints.

## Open issues

1. Airbnb redirects this network to a local domain, and the upstream server does not follow the redirect. Both upstream tools return an error. Two data tests skip for this reason. Run them on another network.
2. The answer step has not run in a real MCP Apps host.
3. The bridge lists two provider tools beside the upstream tools.
4. A forwarded result with upstream structured content gets no card. The current upstream tools return text only.
5. If the held upstream session dies while it still reports connected, forwarded calls fail until the bridge restarts.
