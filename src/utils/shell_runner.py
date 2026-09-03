import subprocess
import shlex

def run_cmd(cmd: str) -> str:
    """Run a shell command safely and return its stdout as a string.
    Raises subprocess.CalledProcessError on non-zero exit.
    """
    # Use shlex.split to avoid shell injection issues
    args = shlex.split(cmd)
    result = subprocess.check_output(args, text=True)
    return result.strip()
