import os
import subprocess
import platform

from qgis.PyQt import QtWidgets, uic, QtCore
from qgis.core import QgsProject, QgsVectorLayer, QgsMessageLog, Qgis
from qgis.utils import iface

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'survey_2_gis_demo_dockwidget_base.ui'))


class Survey2GisDemoDockWidget(QtWidgets.QDockWidget, FORM_CLASS):

    closingPlugin = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        """Constructor."""
        super(Survey2GisDemoDockWidget, self).__init__(parent)
        # Set up the user interface from Designer.
        self.setupUi(self)
        
        # Connect buttons to their slots
        self.input_select_button.clicked.connect(self.select_input_files)
        self.parser_select_button.clicked.connect(self.select_parser_file)
        self.process_button.clicked.connect(self.process_files)
        self.input_data_reset.clicked.connect(lambda: self.reset_text_field(self.input_select))
        self.parser_reset.clicked.connect(lambda: self.reset_text_field(self.parser_select))

        # Create a button group for the radio buttons
        self.label_mode_group = QtWidgets.QButtonGroup(self)
        self.label_mode_group.addButton(self.label_mode_center)
        self.label_mode_group.addButton(self.label_mode_first)
        self.label_mode_group.addButton(self.label_mode_last)
        
        # Ensure the Linux binary is executable
        self.ensure_linux_binary_executable()

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
        """Open file dialog to select a parser file."""
        file, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select Parser File", "", "All Files (*)")
        if file:
            self.parser_select.setText(file)
    
    def reset_text_field(self, field):
        field.setText("")

    def get_selected_label_mode(self):
        """Get the selected label mode from the radio button group."""
        selected_button = self.label_mode_group.checkedButton()
        if selected_button:
            return selected_button.text()
        return None
    
    def show_success_message(self, message):
        """Display a success message using QgsMessageBar."""
        message_bar = iface.messageBar()
        message_bar.pushMessage("Success", message, level=Qgis.Info, duration=5)
    

    def process_files(self):
        """Process the files using the survey2gis command line tool."""
        # Get the user inputs
        parser_path = self.parser_select.text()
        input_files = self.input_select.text().split("; ")
        output_base_name = self.ouput_base_input.text()
        label_mode = self.get_selected_label_mode()
        
        # Determine the binary path based on the OS
        system = platform.system().lower()
        if system == 'windows':
            binary_path = os.path.join(os.path.dirname(__file__), 'bin', 'win32', 'cli-only', 'survey2gis.exe')
        elif system == 'linux':
            binary_path = os.path.join(os.path.dirname(__file__), 'bin', 'linux64', 'cli-only', 'survey2gis')
        elif system == 'darwin':
            QtWidgets.QMessageBox.warning(self, "Not Implemented", "This feature is not implemented on OSX.")
            return
        else:
            QtWidgets.QMessageBox.critical(self, "Unsupported OS", "Your operating system is not supported.")
            return
        
        # Build the output directory path
        output_dir = os.path.join(os.path.dirname(__file__), 'output')

        # Create the output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Build the command
        command = [
            binary_path,
            '-p', parser_path,
            '--label-mode-line=' + label_mode,
            '-o', output_dir,
            '-n', output_base_name
        ] + input_files
        
        try:
            # Execute the command and capture the output
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate()
            
            # Merge stdout and stderr
            output_log = (stdout + stderr).decode('utf-8')
            
            # Write the output to the log
            self.output_log.clear()
            self.output_log.append(output_log)
            
            # Check for errors in the output
            if 'ERROR' in output_log:
                QtWidgets.QMessageBox.critical(self, "Error", "Error occurred during processing.")
                return
            
            # Search for the string "Output files produced" in the output
            if "Output files produced" in output_log:
                self.show_success_message("Output files successfully produced.")
                
                # Search for the shapefiles based on the output_base_name
                shapefile_suffixes = ['_line.shp', '_point.shp', '_poly.shp']
                shapefiles = [os.path.join(output_dir, output_base_name + suffix) for suffix in shapefile_suffixes]
                
                # Load the shapefiles into the current QGIS map view as virtual layers
                for shapefile in shapefiles:
                    if os.path.exists(shapefile):
                        layer = QgsVectorLayer(shapefile, os.path.basename(shapefile), "ogr")
                        if layer.isValid():
                            QgsProject.instance().addMapLayer(layer)
                        else:
                            QgsMessageLog.logMessage(f"Failed to load layer: {os.path.basename(shapefile)}", 'Plugin')
                    else:
                        QgsMessageLog.logMessage(f"Shapefile not found: {shapefile}", 'Plugin')

                            
        except Exception as e:
            QgsMessageLog.logMessage(f"An error occurred: {e}", 'Plugin')
            QtWidgets.QMessageBox.critical(self, "Error", f"An error occurred: {e}")
