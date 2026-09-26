"""repowiki-cli - query DeepWiki documentation from the terminal."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("pyrepowiki-cli")
except PackageNotFoundError:
    __version__ = "0.0.0"
