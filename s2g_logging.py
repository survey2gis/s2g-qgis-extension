import logging
from qgis.core import QgsMessageLog, Qgis
from qgis.utils import iface  # Directly import iface

class Survey2GISLogger:
    def __init__(self, main_widget=None):
        """
        Initialize the logger with optional access to the main widget.
        :param main_widget: Reference to main widget for appending to GUI text field
        """
        self.logger = logging.getLogger("s2g_plugin")
        self.logger.setLevel(logging.DEBUG)
        self.main_widget = main_widget  # Reference to the GUI widget containing the log text field

    def log_message(self, message, level="info", to_tab=True, to_gui=True, to_notification=False):
        """
        Log a message with options for different outputs.
        :param message: The message to log
        :param level: The log level as string (info, warning, error)
        :param to_tab: If True, log to the QGIS plugin tab
        :param to_gui: If True, append the log to a GUI text field
        :param to_notification: If True, display the message in QGIS as a notification bar
        """
        # Convert message to string to ensure compatibility
        message = self.convert_to_string(message)

        # Convert the level to QGIS compatible level and logging level
        if level == "info":
            qgis_level = Qgis.Info
            log_level = logging.INFO
        if level == "success":
            qgis_level = Qgis.Success
            log_level = logging.SUCCESS
        elif level == "warning":
            qgis_level = Qgis.Warning
            log_level = logging.WARNING
        elif level == "error":
            qgis_level = Qgis.Critical
            log_level = logging.ERROR
        else:
            qgis_level = Qgis.Info
            log_level = logging.INFO

        # Log to QGIS plugin tab
        if to_tab:
            QgsMessageLog.logMessage(message, "Survey2GIS", qgis_level)
            self.logger.log(log_level, message)  # Log to Python logger

        # Append to GUI text field
        if to_gui and self.main_widget and hasattr(self.main_widget, 'output_log'):
            current_text = self.main_widget.output_log.toPlainText()
            new_text = f"{current_text}\n{message}"
            self.main_widget.output_log.setPlainText(new_text)

        # Show QGIS notification bar
        if to_notification:
            self.show_notification_bar(message, level=qgis_level)

    def show_notification_bar(self, message, level=Qgis.Info):
        """Display a transient notification bar message in QGIS."""
        if iface:  # Check if iface is available
            messageBar = iface.messageBar()  # QGIS interface
            messageBar.pushMessage("Survey2GIS", message, level, duration=5)

        else:
            print("iface is not available")  # Debugging line to check iface availability

    def convert_to_string(self, obj):
        """Convert various objects to string."""
        if isinstance(obj, (list, tuple)):
            return ', '.join(map(str, obj))  # Join list/tuple items into a string
        return str(obj)  # Fallback to str conversion for other types
