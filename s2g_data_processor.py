import os
import platform
import urllib.request
import zipfile
import platform
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from .resources import *
from .s2g_data_processor_dockwidget import S2gDataProcessorDockWidget
import shutil
from .s2g_logging import log_plugin_message


class S2gDataProcessor:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.binaries_url = "https://github.com/survey2gis/survey-tools/releases/download/v1.5.2-bin-only/survey2gis-binaries-only.zip"
        self.download_dir = os.path.join(self.plugin_dir, "binaries")

        self._download_and_extract_binaries()

        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(self.plugin_dir, 'i18n', 'S2gDataProcessor_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        self.actions = []
        self.menu = self.tr(u'&Survey2Gis Data Processor')
        self.toolbar = self.iface.addToolBar(u'S2gDataProcessor')
        self.toolbar.setObjectName(u'S2gDataProcessor')

        self.pluginIsActive = False
        self.dockwidget = None

    def tr(self, message):
        return QCoreApplication.translate('S2gDataProcessor', message)

    def add_action(self, icon_path, text, callback, enabled_flag=True, add_to_menu=True, add_to_toolbar=True, status_tip=None, whats_this=None, parent=None):
        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.toolbar.addAction(action)

        if add_to_menu:
            self.iface.addPluginToMenu(self.menu, action)

        self.actions.append(action)

        return action

    def initGui(self):
        icon_path = ':/plugins/s2g_data_processor/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u'Survey2Gis Data Processor'),
            callback=self.run,
            parent=self.iface.mainWindow()
        )

    def onClosePlugin(self):
        self.dockwidget.closingPlugin.disconnect(self.onClosePlugin)
        self.pluginIsActive = False

    def unload(self):
        for action in self.actions:
            self.iface.removePluginMenu(self.tr(u'&Survey2Gis Data Processor'), action)
            self.iface.removeToolBarIcon(action)
        del self.toolbar

    def run(self):
        if not self.pluginIsActive:
            self.pluginIsActive = True
            if self.dockwidget is None:
                self.dockwidget = S2gDataProcessorDockWidget()
            self.dockwidget.closingPlugin.connect(self.onClosePlugin)
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dockwidget)
            self.dockwidget.show()


    def get_binary_path(self):
        """Return the path to the appropriate binary based on the current platform."""
        system = platform.system().lower()
        base_path = os.path.dirname(__file__)
        
        if system == "windows":
            path = os.path.join(base_path, "survey2gis", "win32", "cli-only", "survey2gis.exe")
        elif system == "linux":
            path = os.path.join(base_path, "survey2gis", "linux64", "cli-only", "survey2gis")
        elif system == "darwin":
            path = os.path.join(base_path, "survey2gis", "macosx", "cli-only", "survey2gis")
        else:
            raise NotImplementedError("Your operating system is not supported.")

        # return os.path.normpath('"'+path+'"')
        return os.path.normpath(path)

    def ensure_binary_executable(self):
        """Ensure the binary has executable permissions."""
        system = platform.system().lower()
        binary_path = self.get_binary_path()

        if os.path.exists(binary_path):
            if system == "linux" or system == "darwin":
                st = os.stat(binary_path)
                if not (st.st_mode & 0o111):
                    os.chmod(binary_path, st.st_mode | 0o111)
                    log_plugin_message(f"Set executable permissions for {binary_path}")
                else:
                    log_plugin_message(f"{binary_path} is already executable")

                    return True
            elif system == "windows":
                # On Windows, do nothing as it doesn't use chmod for executable permissions
                pass
            else:
                log_plugin_message(f"Unsupported operating system: {system}", "error")
        else:
            log_plugin_message(f"Binary {binary_path} not found", "error")
            return False

    def _download_and_extract_binaries(self):
        download_binary = self.ensure_binary_executable()
        if download_binary == False:
            log_plugin_message(f"Downloading binary again")

            if not os.path.exists(self.download_dir):
                os.makedirs(self.download_dir)

            # Define paths
            zip_path = os.path.join(self.download_dir, "binaries.zip")
            extract_path = os.path.join(self.plugin_dir, "survey2gis")

            # Download binaries
            with urllib.request.urlopen(self.binaries_url) as response:
                with open(zip_path, 'wb') as f:
                    f.write(response.read())

            # Extract binaries
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_path)

            # Cleanup
            os.remove(zip_path)

            try:
                shutil.rmtree(self.download_dir)
            except OSError as e:
                print("Error: %s - %s." % (e.filename, e.strerror))