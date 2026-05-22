"""Entry point shim: ``python -m ping_luma.bot``."""

from ping_luma.presentation.bot import main

__all__ = ["main"]

if __name__ == "__main__":
    main()
