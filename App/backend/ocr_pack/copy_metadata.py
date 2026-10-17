"""Keep dependency version/license metadata required by PaddleX's offline checks."""
import importlib.metadata
from pathlib import Path
import shutil
import sys

target=Path(sys.argv[1]).resolve(strict=True)
for distribution in importlib.metadata.distributions():
    directory=Path(distribution._path)
    if directory.is_dir() and directory.name.endswith('.dist-info'):
        shutil.copytree(directory,target/directory.name,dirs_exist_ok=True)
