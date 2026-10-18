"""Capture a child process's stdout and stderr together, preserving its exit code."""
import argparse
import subprocess
import sys
from pathlib import Path


def run(command, log):
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open('w', encoding='utf-8', newline='\n') as target:
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as process:
            for line in iter(process.stdout.readline, b''):
                text = line.decode('utf-8', errors='replace').replace('\r\n', '\n')
                target.write(text)
                target.flush()
                sys.stdout.write(text)
                sys.stdout.flush()
            return process.wait()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--log', required=True, type=Path)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not args.command:
        parser.error('Child command required')
    raise SystemExit(run(args.command, args.log))
