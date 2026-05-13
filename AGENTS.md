# Basic
1. All the python program should use `uv run --python 3.10` to run except the `pyright` tool.
2. Commands that rely on test or verification dependencies must use `uv run --group dev --python 3.10`.
3. Run pytest via the current Python interpreter, for example `uv run --group dev --python 3.10 python -m pytest`, not bare `pytest`.

# Lint

1. Always use `pyright` in python projects to fetch lint results and fix them when needed, the `pyright` tool was installed by `npm`, just use global command to use it.
2. `pyright` MYST limit the scan files, do not scan all the repository except the user require you to do this.
