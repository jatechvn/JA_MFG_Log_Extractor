"""ANSI styles shared by CLI output and report messages."""


class Color:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    CYAN = "\033[96m"
    BRIGHT_CYAN = "\033[1;96m"
    GREEN = "\033[92m"
    BRIGHT_GREEN = "\033[1;92m"
    YELLOW = "\033[93m"
    BRIGHT_YELLOW = "\033[1;93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    RED = "\033[91m"
    BRIGHT_RED = "\033[1;91m"
    WHITE = "\033[97m"
    GRAY = "\033[90m"
