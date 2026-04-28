"""Allow ``python -m winagent`` to launch the app."""
import sys

from winagent.app import main

if __name__ == "__main__":
    sys.exit(main())
