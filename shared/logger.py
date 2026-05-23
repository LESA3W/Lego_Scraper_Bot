"""Colored, timestamped console logger with severity levels."""

from datetime import datetime
from pathlib import Path
from typing import Optional


class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"

    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    BRIGHT_BLACK = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"


class LogLevel:
    DEBUG = "DEBUG"
    INFO = "INFO"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


LEVEL_COLORS = {
    LogLevel.DEBUG: Colors.BRIGHT_BLACK,
    LogLevel.INFO: Colors.CYAN,
    LogLevel.SUCCESS: Colors.GREEN,
    LogLevel.WARNING: Colors.YELLOW,
    LogLevel.ERROR: Colors.RED,
    LogLevel.CRITICAL: Colors.BRIGHT_RED + Colors.BOLD,
}


def get_timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


def log(
    message: str,
    level: str = LogLevel.INFO,
    to_file: bool = False,
    log_file: Optional[Path] = None,
) -> None:
    """Log a message with color and timestamp."""
    timestamp = get_timestamp()
    color = LEVEL_COLORS.get(level, Colors.WHITE)
    prefix = f"[{timestamp}] [{level}]"

    full_message = f"{color}{prefix}{Colors.RESET} {message}"
    print(full_message, flush=True)

    if to_file and log_file:
        plain_message = f"[{timestamp}] [{level}] {message}\n"
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(plain_message)
        except Exception as e:
            print(f"{Colors.RED}[ERROR] Failed to write to log file: {e}{Colors.RESET}")


def debug(message: str, **kwargs) -> None:
    log(message, level=LogLevel.DEBUG, **kwargs)


def info(message: str, **kwargs) -> None:
    log(message, level=LogLevel.INFO, **kwargs)


def success(message: str, **kwargs) -> None:
    log(message, level=LogLevel.SUCCESS, **kwargs)


def warning(message: str, **kwargs) -> None:
    log(message, level=LogLevel.WARNING, **kwargs)


def error(message: str, **kwargs) -> None:
    log(message, level=LogLevel.ERROR, **kwargs)


def critical(message: str, **kwargs) -> None:
    log(message, level=LogLevel.CRITICAL, **kwargs)


def log_separator(char: str = "-", length: int = 60) -> None:
    print(f"{Colors.BRIGHT_BLACK}{char * length}{Colors.RESET}")


def log_banner(text: str, char: str = "=") -> None:
    length = len(text) + 4
    print(f"{Colors.CYAN}{Colors.BOLD}")
    print(char * length)
    print(f"  {text}  ")
    print(char * length)
    print(Colors.RESET)


__all__ = [
    "log",
    "debug",
    "info",
    "success",
    "warning",
    "error",
    "critical",
    "log_separator",
    "log_banner",
    "Colors",
    "LogLevel",
]
