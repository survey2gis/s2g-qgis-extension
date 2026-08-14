import os
import platform
import logging
from qgis.PyQt import QtWidgets, uic, QtCore, QtGui
from dataclasses import dataclass, field
from osgeo import ogr
from qgis.gui import QgsMessageBar
from qgis.core import Qgis
from datetime import datetime

FORM_CLASS, _ = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), "s2g_data_processor_dockwidget_base.ui")
)

logger = logging.getLogger("s2g_plugin")
logger.setLevel(logging.DEBUG)

from .components.DataNormalizer import DataNormalizer
from .components.DataProcessor import DataProcessor
from .components.LogTab import LogTab
from .components import binary_utils

@dataclass
class CommandOptions:
    parser_path: str = ""
    label_mode: str = ""
    output_directory: str = ""
    output_base_name: str = ""
    additional_options: dict = field(default_factory=dict)
    flag_options: dict = field(default_factory=dict)

    def to_command_list(self) -> list:
        command = []
        if self.parser_path:
            command.extend(["-p", os.path.normpath(self.parser_path)])
        if self.label_mode:
            command.append(f"--label-mode-line={self.label_mode}")
        if self.output_directory:
            command.extend(["-o", os.path.normpath(self.output_directory)])
        if self.output_base_name:
            command.extend(["-n", self.output_base_name])

        for key, value in self.additional_options.items():
            if value:
                command.append(f"{key}={value}")

        for flag, is_set in self.flag_options.items():
            if is_set:
                command.append(flag)

        return command

class S2gDataProcessorDockWidget(QtWidgets.QDockWidget, FORM_CLASS):
    closingPlugin = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super(S2gDataProcessorDockWidget, self).__init__(parent)
        self.setupUi(self)
        
        self.output_base_name = None
        self.output_directory = None
        self.command_history_file = os.path.join(os.path.dirname(__file__), "command_history.txt")

        self.data_normalizer = DataNormalizer()
        self.data_normalizer.setup(self)
        
        self.data_processor = DataProcessor(self)
        self.log_tab = LogTab(self)
    
        self.user_manual.clicked.connect(
            lambda: QtGui.QDesktopServices.openUrl(QtCore.QUrl("https://github.com/user-attachments/files/16010974/english.pdf"))
        )

        self.online_help.clicked.connect(
            lambda: QtGui.QDesktopServices.openUrl(QtCore.QUrl("https://s2qgis-docs.survey-tools.org"))
        )

        self.command_options = CommandOptions()

    def closeEvent(self, event):
        self.closingPlugin.emit()
        event.accept()

    def get_binary_path(self):
        """Resolve the survey2gis binary path.

        Honors the QGIS global override variable ``s2g_path`` if it is set and
        points to an existing file, otherwise falls back to the bundled binary
        for the current platform. Uses the shared resolver so the path can
        never drift from what the diagnostics report.
        """
        override = None
        try:
            from qgis.core import QgsExpressionContextUtils
            candidate = QgsExpressionContextUtils.globalScope().variable("s2g_path")
            if candidate and os.path.exists(candidate):
                override = candidate
        except Exception:
            override = None

        return binary_utils.resolve_binary_path(
            os.path.dirname(__file__), global_override=override
        )

    def ensure_binary_executable(self):
        """Make sure the binary can be executed before we launch it.

        Returns True if the binary is (now) runnable, False otherwise. Any
        problem is logged to the Logs tab so the user gets a real error
        instead of a silent 60-second timeout.
        """
        binary_path = self.get_binary_path()
        info = binary_utils.inspect_binary(binary_path)

        if not info["is_file"]:
            self.data_processor.logger.log_message(
                f"survey2gis binary not found: {binary_path}",
                level="error", to_tab=True, to_gui=True, to_notification=True,
            )
            return False

        if not info["executable"]:
            success, message = binary_utils.make_binary_executable(binary_path)
            self.data_processor.logger.log_message(
                message,
                level="success" if success else "error",
                to_tab=True, to_gui=True, to_notification=not success,
            )
            if not success:
                return False

        # Report missing runtime dependencies (mostly Windows DLLs).
        missing = [name for name, present in info["dependencies"] if not present]
        if missing:
            self.data_processor.logger.log_message(
                "Missing survey2gis runtime dependencies: " + ", ".join(missing),
                level="warning", to_tab=True, to_gui=True, to_notification=True,
            )

        return True

class S2gDataProcessor:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.plugin_name = "S2G Data Processor"
        self.dockwidget = None
        self.actions = []
        self.menu = self.plugin_name
        self.toolbar = self.iface.addToolBar(self.plugin_name)
        self.toolbar.setObjectName(self.plugin_name)

    def initGui(self):
        icon = QtGui.QIcon(os.path.join(self.plugin_dir, 'icon.png'))
        action = QtWidgets.QAction(icon, self.plugin_name, self.iface.mainWindow())
        action.triggered.connect(self.run)
        action.setEnabled(True)
        
        self.toolbar.addAction(action)
        self.iface.addPluginToMenu(self.menu, action)
        self.actions.append(action)

    def unload(self):
        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)
        del self.toolbar

    def onClosePlugin(self):
        self.dockwidget.closingPlugin.disconnect(self.onClosePlugin)
        self.dockwidget = None

    def run(self):
        if not self.dockwidget:
            self.dockwidget = S2gDataProcessorDockWidget()
            self.dockwidget.closingPlugin.connect(self.onClosePlugin)
        self.dockwidget.show()

def classFactory(iface):
    return S2gDataProcessor(iface)