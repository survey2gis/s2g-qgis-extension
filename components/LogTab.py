from qgis.PyQt import QtWidgets
import importlib

from .. s2g_logging import Survey2GISLogger
from . import binary_utils


def _fresh_binary_utils():
    """Return a freshly reloaded binary_utils module.

    The plugin folder name contains dashes ('s2g-qgis-extension'), which is
    not a valid Python package name. QGIS loads it anyway, but that can leave
    a stale copy of this submodule cached in sys.modules across plugin
    reinstalls, so a newly added function like test_run_binary appears to be
    missing. Reloading on access guarantees we use the file on disk.
    """
    try:
        return importlib.reload(binary_utils)
    except Exception:
        return binary_utils


class LogTab:
    def __init__(self, parent_widget):
        """Access main widget for shared variables and settings."""
        self.parent_widget = parent_widget
        self.logger = Survey2GISLogger(parent_widget)
        self._add_binary_buttons()
        self.connect_signals()

    def _add_binary_buttons(self):
        """Add 'diagnose binary' and 'make executable' buttons next to reset.

        Created in code so we don't have to touch the large .ui file. The
        buttons are placed in the same layout as the existing reset button.
        """
        reset_button = getattr(self.parent_widget, "reset_logs_button", None)
        if reset_button is None:
            return

        self.diagnose_binary_button = QtWidgets.QPushButton("diagnose binary")
        self.diagnose_binary_button.setToolTip(
            "Log which survey2gis binary is used and whether it is executable."
        )
        self.make_executable_button = QtWidgets.QPushButton("make executable")
        self.make_executable_button.setToolTip(
            "Make the survey2gis binary executable on this system "
            "(chmod on Linux/macOS, unblock on Windows)."
        )
        self.test_run_button = QtWidgets.QPushButton("test run")
        self.test_run_button.setToolTip(
            "Launch the binary once (survey2gis --help) to check it actually "
            "starts - catches macOS Gatekeeper blocks and missing DLLs."
        )

        parent_layout = reset_button.parentWidget().layout()
        if parent_layout is not None:
            index = parent_layout.indexOf(reset_button)
            if index >= 0:
                parent_layout.insertWidget(index + 1, self.diagnose_binary_button)
                parent_layout.insertWidget(index + 2, self.make_executable_button)
                parent_layout.insertWidget(index + 3, self.test_run_button)
            else:
                parent_layout.addWidget(self.diagnose_binary_button)
                parent_layout.addWidget(self.make_executable_button)
                parent_layout.addWidget(self.test_run_button)

    def connect_signals(self):
        # reset logs
        self.parent_widget.reset_logs_button.clicked.connect(self.reset_logs)

        if hasattr(self, "diagnose_binary_button"):
            self.diagnose_binary_button.clicked.connect(self.diagnose_binary)
        if hasattr(self, "make_executable_button"):
            self.make_executable_button.clicked.connect(self.make_binary_executable)
        if hasattr(self, "test_run_button"):
            self.test_run_button.clicked.connect(self.test_run_binary)

    def reset_logs(self):
        self.parent_widget.output_log.setText("")

    # -- binary diagnostics -------------------------------------------------

    def _resolve_binary_path(self):
        """Get the binary path exactly as the processor would use it."""
        # Prefer the widget's own resolver so diagnostics match execution.
        if hasattr(self.parent_widget, "get_binary_path"):
            return self.parent_widget.get_binary_path()
        import os
        return binary_utils.resolve_binary_path(
            os.path.dirname(os.path.dirname(__file__))
        )

    def diagnose_binary(self):
        """Log a full report on the binary that would be executed."""
        try:
            binary_path = self._resolve_binary_path()
            info = _fresh_binary_utils().inspect_binary(binary_path)

            lines = []
            lines.append(f"{'='*3}")
            lines.append("<b>survey2gis binary diagnostics</b>")
            lines.append(f"System:        {info['system']} ({info['architecture']})")
            lines.append(f"Binary path:   {info['path']}")
            lines.append(f"Exists:        {info['exists']}")
            lines.append(f"Is file:       {info['is_file']}")
            if info["size"] is not None:
                lines.append(f"Size:          {info['size']} bytes")
            if info["mode_octal"] is not None:
                lines.append(f"Permissions:   {info['mode_octal']}")
            lines.append(f"Readable:      {info['readable']}")
            lines.append(f"Executable:    {info['executable']}")

            if info["dependencies"]:
                lines.append("DLLs next to the exe (informational):")
                for name, _present in info["dependencies"]:
                    lines.append(f"    - {name}")

            if info["notes"]:
                lines.append("Notes:")
                for note in info["notes"]:
                    lines.append(f"    - {note}")

            if info["executable"]:
                verdict = "Binary looks ready to run."
                level = "success"
            else:
                verdict = (
                    "Binary is NOT ready. Try 'make executable', or set a "
                    "working binary via the global variable 's2g_path'."
                )
                level = "warning"
            lines.append(verdict)
            lines.append(f"{'='*3}")

            self.logger.log_message(
                "\n".join(lines),
                level=level,
                to_tab=True,
                to_gui=True,
                to_notification=False,
            )
        except Exception as error:  # noqa: BLE001
            self.logger.log_message(
                f"Binary diagnostics failed: {error}",
                level="error",
                to_tab=True,
                to_gui=True,
                to_notification=True,
            )

    def test_run_binary(self):
        """Launch the binary once and report whether it actually starts."""
        try:
            binary_path = self._resolve_binary_path()
            result = _fresh_binary_utils().test_run_binary(binary_path)

            lines = []
            lines.append(f"{'='*3}")
            lines.append("<b>survey2gis test run (--help)</b>")
            lines.append(f"Binary path:   {binary_path}")
            lines.append(f"Launched:      {result['launched']}")
            if result["returncode"] is not None:
                lines.append(f"Exit code:     {result['returncode']}")
            if result["signal"] is not None:
                lines.append(f"Killed by signal: {result['signal']}")

            output = (result["stdout"] or result["stderr"]).strip()
            if output:
                snippet = output.splitlines()[:5]
                lines.append("Output (first lines):")
                for line in snippet:
                    lines.append(f"    {line}")

            lines.append(result["message"])
            lines.append(f"{'='*3}")

            # "Launched" is the real signal: even a usage error means the
            # binary ran. A block or missing library means it never started.
            if result["launched"] and (result["signal"] is None):
                level = "success"
            else:
                level = "error"

            self.logger.log_message(
                "\n".join(lines),
                level=level,
                to_tab=True,
                to_gui=True,
                to_notification=(level == "error"),
            )
        except Exception as error:  # noqa: BLE001
            self.logger.log_message(
                f"Test run failed: {error}",
                level="error",
                to_tab=True,
                to_gui=True,
                to_notification=True,
            )

    def make_binary_executable(self):
        """Make the resolved binary executable and report the result."""
        try:
            binary_path = self._resolve_binary_path()
            success, message = _fresh_binary_utils().make_binary_executable(binary_path)
            self.logger.log_message(
                message,
                level="success" if success else "error",
                to_tab=True,
                to_gui=True,
                to_notification=True,
            )
            # Re-run diagnostics so the user sees the resulting state.
            self.diagnose_binary()
        except Exception as error:  # noqa: BLE001
            self.logger.log_message(
                f"Could not make binary executable: {error}",
                level="error",
                to_tab=True,
                to_gui=True,
                to_notification=True,
            )
