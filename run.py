#!/usr/bin/env python
import sys
from pathlib import Path

# Add the directory containing 'rocky' package to python path
sys.path.insert(0, str(Path(__file__).parent))

from rocky.main import cli

if __name__ == "__main__":
    cli()
