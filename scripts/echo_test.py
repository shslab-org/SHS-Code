import sys
import os, sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.utils.shell_runner import run_cmd

def main():
    output = run_cmd('echo hello-one-shot-test')
    print(output)

if __name__ == '__main__':
    main()
