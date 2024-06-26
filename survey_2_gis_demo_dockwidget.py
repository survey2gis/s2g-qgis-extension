import os
import platform
import re
import logging
from PyQt5 import QtWidgets, uic, QtCore, QtGui
from qgis.core import QgsProject, QgsVectorLayer, Qgis
from qgis.utils import iface

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'survey_2_gis_demo_dockwidget_base.ui'))

logger = logging.getLogger('s2g_plugin')
logger.setLevel(logging.DEBUG)

class Survey2GisDemoDockWidget(QtWidgets.QDockWidget, FORM_CLASS):

    closingPlugin = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        """Constructor."""
        super(Survey2GisDemoDockWidget, self).__init__(parent)
        self.setupUi(self)

        # Ensure the Linux binary is executable
        self.ensure_linux_binary_executable()

        # Initialize output base name and Directory
        self.output_base_name = None
        self.output_directory = None

        # Connect select buttons to their slots
        self.input_select_button.clicked.connect(self.select_input_files)
        self.parser_select_button.clicked.connect(self.select_parser_file)
        self.output_folder_select.clicked.connect(self.select_output_directory)

        # Connect reset buttons to their slots
        self.process_button.clicked.connect(self.process_files)
        self.input_data_reset.clicked.connect(lambda: self.reset_text_field(self.input_select))
        self.parser_reset.clicked.connect(lambda: self.reset_text_field(self.parser_select))
        self.output_folder_reset.clicked.connect(lambda: self.reset_text_field(self.output_folder_select))

        # Create a button group for the radio buttons
        self.label_mode_group = QtWidgets.QButtonGroup(self)
        self.label_mode_group.addButton(self.label_mode_center)
        self.label_mode_group.addButton(self.label_mode_first)
        self.label_mode_group.addButton(self.label_mode_last)

    def closeEvent(self, event):
        self.closingPlugin.emit()
        event.accept()

    def ensure_linux_binary_executable(self):
        """Ensure the Linux binary has executable permissions."""
        if platform.system().lower() == 'linux':
            binary_path = os.path.join(os.path.dirname(__file__), 'bin', 'linux64', 'cli-only', 'survey2gis')
            if os.path.exists(binary_path):
                st = os.stat(binary_path)
                os.chmod(binary_path, st.st_mode | 0o111)

    def select_input_files(self):
        """Open file dialog to select multiple input files."""
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Select Input File(s)", "", "All Files (*)")
        if files:
            self.input_select.setText("; ".join(files))

    def select_parser_file(self):
        """Open file dialog to select one parser file."""
        file, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select Parser File", "", "All Files (*)")
        if file:
            self.parser_select.setText(file)

    def select_output_directory(self):
        """Open file dialog to select an output directory."""
        directory = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Output Directory", "")
        if directory:
            self.output_folder_select.setText(directory)
            self.output_directory = directory

    def reset_text_field(self, field):
        field.setText("")

    def get_selected_label_mode(self):
        """Get the selected label mode from the radio button group."""
        selected_button = self.label_mode_group.checkedButton()
        return selected_button.text() if selected_button else None

    def show_message(self, message, level=Qgis.Info):
        """Display a message using QgsMessageBar."""
        message_bar = iface.messageBar()
        message_bar.pushMessage("Plugin Message", message, level=level, duration=5)

    def process_files(self):
        """Process the files using the survey2gis command line tool."""
        try:
            # Get the user inputs
            parser_path = self.parser_select.text()
            input_files = self.input_select.text().split("; ")
            self.output_base_name = self.output_base_input.text()
            label_mode = self.get_selected_label_mode()

            # Build the command
            command = self.build_command(parser_path, input_files, label_mode)

            # Clear the log and show command
            self.output_log.clear()
            self.output_log.append(' '.join(command))

            # Run the command using QProcess
            self.run_process(command)

        except FileNotFoundError as e:
            self.handle_error(f"File not found: {e}")
        except PermissionError as e:
            self.handle_error(f"Permission denied: {e}")
        except Exception as e:
            self.handle_error(f"An unexpected error occurred: {e}")

    def build_command(self, parser_path, input_files, label_mode):
        """Build the command to execute survey2gis."""
        system = platform.system().lower()
        if system == 'windows':
            binary_path = os.path.join(os.path.dirname(__file__), 'bin', 'win32', 'cli-only', 'survey2gis.exe')
        elif system == 'linux':
            binary_path = os.path.join(os.path.dirname(__file__), 'bin', 'linux64', 'cli-only', 'survey2gis')
        else:
            raise NotImplementedError("Your operating system is not supported.")

        return [
            binary_path,
            '-p', parser_path,
            '--label-mode-line=' + label_mode,
            '-o', self.output_directory,
            '-n', self.output_base_name
        ] + input_files

    def run_process(self, command):
        """Run an external process using QProcess."""
        self.process = QtCore.QProcess(self)
        self.process.readyReadStandardOutput.connect(self.handle_stdout)
        self.process.readyReadStandardError.connect(self.handle_stderr)
        self.process.finished.connect(self.process_finished)

        self.process.start(command[0], command[1:])

    def handle_stdout(self):
        """Handle standard output from the process."""
        data = self.process.readAllStandardOutput().data().decode()
        self.output_log.append(data)

    def handle_stderr(self):
        """Handle standard error from the process."""
        data = self.process.readAllStandardError().data().decode()
        self.output_log.append(data)

    def process_finished(self, exit_code, exit_status):
        """Handle process finished event."""
        if exit_code == 0:
            self.handle_process_output("Process finished successfully.")
        else:
            self.handle_process_output(f"Process finished with exit code {exit_code}.")

    def handle_process_output(self, output_log):
        """Handle the output of the external process."""
        self.output_log.append(output_log)

        if 'ERROR' in output_log:
            self.show_error_message("Error occurred during processing. See Plugin log window.")
            return


        self.load_shapefiles(output_log)

    def load_shapefiles(self, output_log):
        """Load produced shapefiles into QGIS."""


        shapefile_suffixes = ['_line.shp', '_point.shp','_poly.shp']
        shapefiles = [os.path.join(self.output_directory, self.output_base_name + suffix) for suffix in shapefile_suffixes]

        self.output_log.append("shapefiles are")
        self.output_log.append(str(shapefiles))
        self.output_log.append("loading shapefiles")

        if not shapefiles:
            logger.error("No shapefiles found in output log.")
            return

        root = QgsProject.instance().layerTreeRoot()
        group = root.addGroup(self.output_base_name)

        for shapefile in shapefiles:
            if os.path.exists(shapefile):
                layer_name = os.path.splitext(os.path.basename(shapefile))[0]
                layer = QgsVectorLayer(shapefile, layer_name, 'ogr')
                
                if layer and layer.isValid():
                    # Add the layer to the project
                    QgsProject.instance().addMapLayer(layer, False)
                    # Add the layer to the group in the layer tree
                    group.addLayer(layer)
                    self.output_log.append(f"Added {os.path.basename(shapefile)} to project")
                    logger.info(f"Added {os.path.basename(shapefile)} to project")
                else:
                    logger.error(f"Failed to create layer for: {os.path.basename(shapefile)}")
            else:
                logger.warning(f"Shapefile not found: {shapefile}")

        # Expand the group to show the layers
        group.setExpanded(True)



    def handle_error(self, error):
        """Handle and log errors."""
        self.output_log.append(f"An error occurred: {error}")
        logger.error(f"An error occurred: {error}")
        self.show_error_message(f"An error occurred: {error}")

    def show_error_message(self, message):
        """Display an error message."""
        self.show_message(message, level=Qgis.Critical)

    def show_success_message(self, message):
        """Display a success message."""
        self.show_message(message, level=Qgis.Success)

def classFactory(iface):
    return Survey2GisDemoDockWidget(iface)
