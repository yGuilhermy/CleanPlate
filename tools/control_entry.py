"""Source launcher and PyInstaller console entry point."""
from pathlib import Path
import sys
if not getattr(sys,'frozen',False):
    root=Path(__file__).resolve().parents[1]
    sys.path[:0]=[str(root/'.deps'),str(root)]
if __name__=='__main__':
    from cleanplate.cli import main
    sys.exit(main())
