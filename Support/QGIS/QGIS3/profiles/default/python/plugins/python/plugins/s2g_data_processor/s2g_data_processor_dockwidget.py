import os
import platform
import logging
from PyQt5 import QtWidgets, uic, QtCore, QtGui
from qgis.core import QgsProject, QgsVectorLayer, Qgis, QgsMessageLog
from qgis.utils import iface
from dataclasses import dataclass, field

FORM_CLASS, _ = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), "s2g_data_processor_dockwidget_base.ui")
)

logger = logging.getLogger("s2g_plugin")
logger.setLevel(logging.DEBUG)


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
        # if self.output_base_name:
        #     command.extend(["-n", self.output_base_name])


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
        """Constructor."""
        super(S2gDataProcessorDockWidget, self).__init__(parent)
        self.setupUi(self)

        self.ensure_binary_executable()

        self.output_base_name = None
        self.output_directory = None

        self.input_select_button.clicked.connect(self.select_input_files)
        self.select_parser_input.clicked.connect(self.select_parser_file)
        self.output_select_button.clicked.connect(self.select_output_directory)
        self.manual_link.clicked.connect(lambda: QtGui.QDesktopServices.openUrl(QtCore.QUrl("https://github.com/user-attachments/files/16010974/english.pdf")))


        self.select_parsed_inputfile_button.clicked.connect(self.select_parsed_inputfile)

        # self.process_button.clicked.connect(self.process_files)
        self.reset_parsed_inputfile_button.clicked.connect(
            lambda: self.reset_text_field(self.process_input_file_input)
        )
        self.reset_parser_input_button.clicked.connect(
            lambda: self.reset_text_field(self.select_parser_input)
        )
        # self.output_folder_reset.clicked.connect(
        #     lambda: self.reset_text_field(self.output_folder_select)
        # )

        self.command_options = CommandOptions()
        
        # Define field mapping for options
        self.option_fields = {
            'parser_path': self.parser_select,
            # 'output_base_name': self.output_basename_input,
            'output_directory': self.output_directory_input
        }
        
        # Define additional options and flags if needed
        self.additional_options_fields = {
            '--topology': self.topology_select,
            '--label-mode-poly': self.label_mode_poly_select,
            '--label': self.label_input,
            '--selection': self.selection_input,
            '--z-offset': self.z_offset_input,
            '--tolerance': self.tolerance_input,
            '--decimal-places': self.decimal_places_input,
            '--snapping': self.snapping_input,
            '--decimal-point': self.decimal_point_input,
            '--decimal-group': self.decimal_group_input,
            '--dangling': self.dangling_input,
            '--x-offset': self.x_offset_input,
            '--y-offset': self.y_offset_input,
            '--proj-in': self.proj_in_input,
            '--proj-out': self.proj_out_input
        }

        self.flag_options_fields = {
            '-c': self.strict_checkbox,
            '-e': self.english_checkbox,
            '-v': self.validate_checkbox,
            '-2': self.force_2d_checkbox,
        }


    def closeEvent(self, event):
        self.closingPlugin.emit()
        event.accept()

    def ensure_binary_executable(self):
        """Ensure the binary has executable permissions."""
        system = platform.system().lower()
        binary_path = self.get_binary_path()

        if os.path.exists(binary_path):
            if system == "linux" or system == "darwin":
                st = os.stat(binary_path)
                if not (st.st_mode & 0o111):
                    os.chmod(binary_path, st.st_mode | 0o111)
                    logger.info(f"Set executable permissions for {binary_path}")
                    self.log_plugin_message(f"Set executable permissions for {binary_path}")
                else:
                    logger.info(f"{binary_path} is already executable")
                    self.log_plugin_message(f"{binary_path} is already executable")
            elif system == "windows":
                # On Windows, do nothing as it doesn't use chmod for executable permissions
                pass
            else:
                logger.warning(f"Unsupported operating system: {system}")
                self.log_plugin_message(f"Unsupported operating system: {system}")
        else:
            logger.warning(f"Binary {binary_path} not found")
            self.log_plugin_message(f"Binary {binary_path} not found")

    def log_plugin_message(self, message):
        """Log a message to the plugin-specific log tab."""
        QgsMessageLog.logMessage(message, "Survey2GIS", Qgis.Info)

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
        
        return os.path.normpath(path)

    def select_input_files(self):
        """Open file dialog to select multiple input files."""
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Select Input File(s)", "", "All Files (*)"
        )
        if files:
            self.input_select.setText("; ".join(files))

    def select_parser_file(self):
        """Open file dialog to select one parser file."""
        file, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select Parser File", "", "All Files (*)"
        )
        if file:
            self.parser_select.setText(file)

    def select_output_directory(self):
        """Open file dialog to select an output directory."""
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select Output Directory", ""
        )
        if directory:
            self.output_select_input.setText(directory)  # Update text field with directory path
            self.command_options.output_directory = directory  # Update command options


    def select_parsed_inputfile(self):
        """Open file dialog to select one parser file."""
        file, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select Parser File", "", "All Files (*)"
        )
        if file:
            self.process_input_file_input.setText(file)


    def reset_text_field(self, field):
        field.setText("")

    def get_selected_label_mode_poly(self):
        """Get the selected label mode from the QComboBox."""
        return self.label_mode_poly.currentText()

    def show_message(self, message, level=Qgis.Info):
        """Display a message using QgsMessageBar."""
        message_bar = iface.messageBar()
        message_bar.pushMessage("Plugin Message", message, level=level, duration=5)

    def process_files(self):
        """Process the files using the survey2gis command line tool."""
        try:
            # Check if any of the required fields are empty
        # Check if the required fields are filled
            if (not self.input_select.text().strip() or
                not self.output_basename_input.text().strip() or
                not self.output_directory_input.text().strip()):
                self.show_error_message("Please fill all required fields in Tab 'files'")
                return

            # Check if either parser_profiles_select or parser_select is filled
            # if (self.parser_profiles_select.currentText() == "Choose profile from list" and 
            #     not self.parser_select.text().strip()):
            #     self.show_error_message("Please select a parser profile or a parser file.")
            #     return

            self.command_options = self.read_options()
            input_files = self.input_select.text().split("; ")
            input_files = [os.path.normpath(file) for file in input_files]

            command = self.build_command(input_files)

            self.output_log.clear()
            self.output_log.append(" ".join(command))

            self.run_process(command)

        except FileNotFoundError as e:
            self.handle_error(f"File not found: {e}")
        except PermissionError as e:
            self.handle_error(f"Permission denied: {e}")
        except Exception as e:
            self.handle_error(f"An unexpected error occurred: {e}")


    def read_options(self):
        """Read options from UI fields and update command_options."""
        command_options = CommandOptions()

        # Read main options
        for option, widget in self.option_fields.items():
            value = widget.currentText() if isinstance(widget, QtWidgets.QComboBox) else widget.text()
            setattr(command_options, option, value)

        # Read additional options
        for key, widget in self.additional_options_fields.items():
            value = widget.currentText() if isinstance(widget, QtWidgets.QComboBox) else widget.text()
            command_options.additional_options[key] = value

        # Read flag options
        for flag, widget in self.flag_options_fields.items():
            is_set = widget.isChecked()
            command_options.flag_options[flag] = is_set

        # Check the value of parser_profiles_select and set parser_path accordingly
        # profile_text = self.parser_profiles_select.currentText()
        # if profile_text != "Choose profile from list":
        #     command_options.parser_path = os.path.join(os.path.dirname(__file__), 'parser_profiles', profile_text)
        # else:
        #     command_options.parser_path = self.parser_select.text()

        return command_options

    def build_command(self, input_files):
        """Build the command to execute survey2gis."""
        binary_path = self.get_binary_path()

        command = [binary_path]

        # Include options and flags with the equal sign for options
        command.extend(self.command_options.to_command_list())

        # Add input files to the command
        command.extend(input_files)

        return command

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

        if "ERROR" in output_log:
            self.show_error_message(
                "Error occurred during processing. See Plugin log window."
            )
            return

        self.load_shapefiles(output_log)

    def load_shapefiles(self, output_log):
        """Load produced shapefiles into QGIS."""
        shapefile_suffixes = ["_line.shp", "_point.shp", "_poly.shp"]
        shapefiles = [
            os.path.join(
                self.command_options.output_directory,
                self.command_options.output_base_name + suffix,
            )
            for suffix in shapefile_suffixes
        ]

        logger.success("loading shapefiles")
        logger.success(shapefiles)

        if not shapefiles:
            logger.error("No shapefiles found in output log.")
            return

        root = QgsProject.instance().layerTreeRoot()
        # group = root.addGroup(self.command_options.output_base_name)

        for shapefile in shapefiles:
            if os.path.exists(shapefile):
                layer_name = os.path.splitext(os.path.basename(shapefile))[0]
                layer = QgsVectorLayer(shapefile, layer_name, "ogr")

                if layer and layer.isValid():
                    QgsProject.instance().addMapLayer(layer, False)
                    group.addLayer(layer)
                    logger.info(f"Added {os.path.basename(shapefile)} to project")
                else:
                    logger.error(
                        f"Failed to create layer for: {os.path.basename(shapefile)}"
                    )
            else:
                logger.warning(f"Shapefile not found: {shapefile}")

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
    return S2gDataProcessorDockWidget(iface)

