# Changelog

All entries below are from session 1 on 31 October 2026.

| File | Change | Why |
|---|---|---|
| `mcp_config.json` | Added | Source of truth for the upstream server command |
| `client.py` | Added | Lists and calls tools on the upstream server or the bridge |
| `server.py` | Added | Registers bridge tools at runtime and asks for missing inputs |
| `test_client.py` | Added | Live tests for the client |
| `test_server.py` | Added | Live tests for the bridge, and schema tests for the question builder |
| `requirements.txt` | Added | Names fastmcp with the apps extra, Deno, and the dev tools |
| `README.md` | Added | Install steps, run steps, tool list, and a question capture |
| `question.jpg` | Added | Screenshot of a rendered question |
| `CLAUDE.md` | Added | Records open issues for the next session |
| `.gitignore` | Added | Keeps the environment, caches, and secrets out of the repo |
| `server.py` | Added result card, null removal, nested enum search, one held session, state values, disabled empty Send | Code review findings |
| `client.py` | Added session reuse and validation of the args option and the tool list | Code review findings |
| `test_client.py` | Skip now needs a direct redirect check | Code review finding: the old skip hid real upstream failures |
| `test_server.py` | Forwarding test compares with upstream. Fixture is no longer autouse. Added tests for new functions | Code review findings |
| `README.md` | Updated test counts, flow, and limits | Matches the fixed code |
| `question.jpg` | Replaced | Shows Send disabled on an empty answer |
| `CLAUDE.md` | Updated open issues | Matches the fixed code |
