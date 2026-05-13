# Basic
1. All the python program should use `uv run --python 3.10` to run except the `pyright` tool.
2. Commands that rely on test or verification dependencies must use `uv run --group dev --python 3.10`.
3. Run pytest via the current Python interpreter, for example `uv run --group dev --python 3.10 python -m pytest`, not bare `pytest`.

# Lint

1. Always use `pyright` in python projects to fetch lint results and fix them when needed, the `pyright` tool was installed by `npm`, just use global command to use it.
2. `pyright` MYST limit the scan files, do not scan all the repository except the user require you to do this.

# Plugin Imports

1. In plugin runtime code, all imports of this plugin's own modules MUST use explicit relative imports.
2. Apply `from .xxx import ...` for sibling modules and `from ..xxx import ...` for cross-package imports inside the plugin package tree.
3. Do not use `from chat_work_balance ...` inside `main.py` or any runtime module under `chat_work_balance/`.
4. Tests are the exception: test modules may continue using absolute imports such as `from chat_work_balance ...` because they are external callers, not runtime modules inside the plugin package tree.
