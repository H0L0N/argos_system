import enum
from rich.console import Console
from rich.panel import Panel
from rich.theme import Theme
from rich.text import Text
from rich.table import Table


class LogLevel(enum.IntEnum):
    """Available log levels for the system."""

    DEBUG = 0
    INFO = 1
    SUCCESS = 2
    WARNING = 3
    ERROR = 4
    CRITICAL = 5
    NONE = 6


# Define a premium Kali Linux-style theme
KALI_THEME = Theme(
    {
        "debug": "dim cyan",
        "info": "bold cyan",
        "success": "bold green",
        "warning": "bold yellow",
        "error": "bold red",
        "critical": "bold red blink",
        "banner": "bold cyan",
        "accent": "bright_blue",
    }
)


class Logger:
    """Professional logger that handles verbosity internally using Rich."""

    def __init__(self, level: LogLevel = LogLevel.INFO):
        self.level = level
        self.console = Console(theme=KALI_THEME)

    def debug(self, message: str) -> None:
        """Prints a debug message with a magnifying glass icon."""
        if self.level <= LogLevel.DEBUG:
            self.console.print(f"[debug]🔍 [DEBUG] {message}[/debug]")

    def info(self, message: str) -> None:
        """Prints an informational message with a satellite dish icon."""
        if self.level <= LogLevel.INFO:
            self.console.print(f"[info]📡 {message}[/info]")

    def success(self, message: str) -> None:
        """Prints a success message with a shield icon."""
        if self.level <= LogLevel.SUCCESS:
            self.console.print(f"[success]🛡️  {message}[/success]")

    def warning(self, message: str) -> None:
        """Prints a warning message with an alert icon."""
        if self.level <= LogLevel.WARNING:
            self.console.print(f"[warning]⚠️  {message}[/warning]")

    def error(self, message: str, exc: Exception | None = None) -> None:
        """Prints an error message with a skull icon and traceback."""
        if self.level <= LogLevel.ERROR:
            self.console.print(f"[error]💀 ERROR: {message}[/error]")
            if exc is not None:
                import traceback

                self.console.print(f"[red]{traceback.format_exc()}[/red]")

    def banner(
        self,
        message: str,
        color: str = "cyan",  # Color name supported by Rich
        center: bool = True,
        level: LogLevel = LogLevel.INFO,
    ) -> None:
        """Prints a premium cybersecurity banner using Rich Panels."""
        if self.level > level:
            return

        panel = Panel(
            Text.from_markup(
                message, justify="center" if center else "left", style="bold white"
            ),
            border_style=color,
            title="[bold accent]ARGOS System[/bold accent]",
            subtitle="[bold accent]Security Operations Center[/bold accent]",
        )
        self.console.print("\n", panel, "\n")

    def display_table(
        self, title: str, columns: list[str], rows: list[list[str]]
    ) -> None:
        """Displays data in a premium Rich table."""
        if self.level > LogLevel.INFO:
            return

        table = Table(
            title=f"[bold accent]{title}[/bold accent]",
            border_style="bright_blue",
            header_style="bold cyan",
            show_header=True,
            show_lines=True,
        )

        for col in columns:
            table.add_column(col)

        for row in rows:
            table.add_row(*row)

        self.console.print(table)
