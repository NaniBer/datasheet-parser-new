"""Enable `python -m src.conformance ...` (delegates to the runner CLI)."""
import sys

from .runner import main

if __name__ == "__main__":
    sys.exit(main())
