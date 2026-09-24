#!/usr/bin/env python3
"""Entry point wrapper that applies patches before invoking ilamb-run."""

import sys

from dvmdostem_ilamb.ilamb_patch import apply_patches

apply_patches()

from ILAMB.run import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
