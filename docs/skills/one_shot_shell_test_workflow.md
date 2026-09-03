# One‑Shot Shell Test Workflow

This skill documents the steps to add a safe shell utility, a script that echoes a test string, and a pytest that validates the output in the SHS‑Code project.

## Steps
1. **Verify project builds**: `python -m compileall -q .`
2. **Run existing test suite**: `python -m pytest -x -q`
3. **Add utility module** `src/utils/shell_runner.py` with a `run_cmd` function that safely executes shell commands using `subprocess.check_output` and `shlex.split`.
4. **Create script** `scripts/echo_test.py` that imports `run_cmd`, executes `echo hello-one-shot-test`, and prints the result. Adjust `sys.path` to include the project root.
5. **Write pytest** `tests/test_echo_test.py` that runs the script via `subprocess.run` and asserts the output equals `hello-one-shot-test`.
6. **Run the new test**: `python -m pytest tests/test_echo_test.py` – should pass.
7. **Capture script output** to `workspace/echo_test_output.txt` using `python scripts/echo_test.py > workspace/echo_test_output.txt`.
8. **Verify captured output** – the file should contain the line `hello-one-shot-test`.

## Outcome
All verification steps pass, and the workflow can be reused for similar one‑shot shell command tests.
