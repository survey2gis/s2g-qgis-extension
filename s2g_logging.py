import logging
from qgis.core import QgsMessageLog, Qgis

logger = logging.getLogger("s2g_plugin")
logger.setLevel(logging.DEBUG)

def log_plugin_message(message, level="info"):
    """Log a message to the plugin-specific log tab in QGIS."""
    if level == "info" or level is False:
        msg_level = Qgis.Info
    elif level == "warning":
        msg_level = Qgis.Warning
    elif level == "error":
        msg_level = Qgis.Critical
    else:
        # Default to Qgis.Info if level is not recognized
        msg_level = Qgis.Info

    # Log message with the determined message level
    QgsMessageLog.logMessage(message, "Survey2GIS", msg_level)
    logger.log(msg_level, message)  # Log to QGIS message log and Python logger
