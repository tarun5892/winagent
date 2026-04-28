"""Top-level entry point used by PyInstaller.

PyInstaller runs the entry script as ``__main__`` rather than as part of a
package, which means relative imports inside the script break (the failure
you'd see is ``ImportError: attempted relative import with no known parent
package``). This file lives at the repository root, uses *absolute* imports
exclusively, and simply delegates to :func:`winagent.app.main`.
"""
from __future__ import annotations

import sys

from winagent.app import main

if __name__ == "__main__":
    sys.exit(main())
