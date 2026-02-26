"""Bedrock — A desktop Markdown note editor inspired by Obsidian."""

import sys

from pathlib import Path

from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow

APP_DIR = Path(__file__).parent.resolve()


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Bedrock")

    # Load dark theme
    theme_path = APP_DIR / "resources" / "dark_theme.qss"
    try:
        app.setStyleSheet(theme_path.read_text())
    except FileNotFoundError:
        pass

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
