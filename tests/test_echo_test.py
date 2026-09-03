import subprocess
import sys
import os

def test_echo_output():
    # Ensure the script can be executed
    script_path = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'echo_test.py')
    result = subprocess.run([sys.executable, script_path], capture_output=True, text=True, check=True)
    output = result.stdout.strip()
    assert output == 'hello-one-shot-test'
