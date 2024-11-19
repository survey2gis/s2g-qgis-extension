import os
import platform
import logging
from PyQt5 import QtWidgets, uic, QtCore, QtGui
from qgis.core import QgsProject, QgsVectorLayer, Qgis
from qgis.utils import iface
from dataclasses import dataclass, field
import shutil
from qgis.core import QgsVectorFileWriter, QgsProject
from osgeo import ogr
import json
from .s2g_logging import log_plugin_message

import fnmatch
import re
import time
import configparser


FORM_CLASS, _ = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), "s2g_data_processor_dockwidget_base.ui")
)

logger = logging.getLogger("s2g_plugin")
logger.setLevel(logging.DEBUG)

# from .classes.DataNormalizer import DataNormalizer
# from.classes.DataProcessor import DataProcessor

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

    # General

    def __init__(self, parent=None):
        """Constructor."""
        super(S2gDataProcessorDockWidget, self).__init__(parent)
        self.setupUi(self)

        self.alias_mapping = self.load_alias_mapping("/Users/tonischonbuchner/Desktop/_s2g_test/alias.txt")

        self.output_base_name = None
        self.output_directory = None
        self.CONCAT_OUTPUT_NAME = "concatenated_output.txt"

        self.command_history_file = os.path.join(os.path.dirname(__file__), "command_history.txt")
        self.current_commands = []
        self.current_command_index = 0

        # Tab Normalize
        self.input_select_button.clicked.connect(self.select_input_files)
        self.input_data_reset_button.clicked.connect(
            lambda: self.reset_text_field(self.input_select)
        )

        self.output_select_button.clicked.connect(self.select_output_directory)
        self.output_reset_button.clicked.connect(
            lambda: self.reset_text_field(self.output_select_input)
        )

        self.styles_input_select_button.clicked.connect(self.styles_input_directory)
        self.styles_reset_button.clicked.connect(
            lambda: self.reset_text_field(self.styles_folder_path_input)
        )

        self.run_button.clicked.connect(self.run_normalize)

        # Tab Process

        self.select_parsed_inputfile_button.clicked.connect(self.select_parsed_inputfile)
        self.reset_parsed_inputfile_button.clicked.connect(
            lambda: self.reset_text_field(self.process_input_file_input)
        )

        self.select_parser_input_button.clicked.connect(self.select_parser_file)
        self.reset_parser_input_button.clicked.connect(
            lambda: self.reset_text_field(self.select_parser_input)
        )

        self.select_shapeoutput_button.clicked.connect(self.select_shapeoutput_directory)
        self.reset_shapeoutput_button.clicked.connect(
            lambda: self.reset_text_field(self.shape_output_path_input)
        )

        self.add_command_button.clicked.connect(self.add_command)
        self.save_commands_button.clicked.connect(self.save_command_history)
        self.run_commands_button.clicked.connect(self.run_commands)

        self.intermediate_file_dict = {}
        
        # Tab help
        self.manual_link.clicked.connect(lambda: QtGui.QDesktopServices.openUrl(QtCore.QUrl("https://github.com/user-attachments/files/16010974/english.pdf")))

        # End Tabs
        
        self.command_options = CommandOptions()

        # Define field mapping for options
        self.option_fields = {
            'parser_path': self.select_parser_input,
            'output_base_name': self.name_generated_file_input,
            'output_directory': self.shape_output_path_input
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

        self.load_command_history()

    # Todo: this also exists in s2g_data_processor.py solve redundance
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

    def closeEvent(self, event):
        self.closingPlugin.emit()
        event.accept()

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

    def get_selected_label_mode_poly(self):
        """Get the selected label mode from the QComboBox."""
        return self.label_mode_poly.currentText()


    # Normalize

    def select_input_files(self):
        """Open file dialog to select multiple input files."""
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Select Input File(s)", "", "All Files (*)"
        )
        if files:
            self.input_select.setText("; ".join(files))

    def select_parsed_inputfile(self):
        """Open file dialog to select one parser file."""
        file, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select Parser File", "", "All Files (*)"
        )
        if file:
            self.process_input_file_input.setText(file)

    def select_parser_file(self):
        """Open file dialog to select one parser file."""
        file, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select Parser File", "", "All Files (*)"
        )
        if file:
            self.select_parser_input.setText(file)

    def select_shapeoutput_directory(self):
        """Open file dialog to select an output directory."""
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select Output Directory", ""
        )
        if directory:
            self.shape_output_path_input.setText(directory)  # Update text field with directory path
            self.command_options.output_directory = directory  # Update command options

    def styles_input_directory(self):
        """Open file dialog to select an output directory."""
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select Output Directory", ""
        )
        if directory:
            self.styles_folder_path_input.setText(directory)  # Update text field with directory path
            self.command_options.styles_folder_path_input = directory  # Update command options

    def select_output_directory(self):
        """Open file dialog to select an output directory."""
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select Output Directory", ""
        )
        if directory:
            self.output_select_input.setText(directory)  # Update text field with directory path
            self.command_options.output_directory = directory  # Update command options

    def reset_text_field(self, field):
        field.setText("")

    def show_message(self, message, level=Qgis.Info):
        """Display a message using QgsMessageBar."""
        message_bar = iface.messageBar()
        message_bar.pushMessage("Plugin Message", message, level=level, duration=5)

    def concatenate_files(self):
        """Concatenate selected .txt or .dat files alphabetically and save the result."""
        input_files = self.input_select.text().split("; ")
        input_files = sorted([os.path.normpath(file) for file in input_files if file.endswith(('.txt', '.dat'))])
        
        if not input_files:
            raise FileNotFoundError("No valid .txt or .dat files selected")

        # Output file path based on the selected output directory and base name
        output_directory = self.output_select_input.text().strip()
        output_file_path = os.path.join(output_directory, self.CONCAT_OUTPUT_NAME)

        with open(output_file_path, 'w', encoding='utf-8') as output_file:
            for input_file in input_files:
                with open(input_file, 'r', encoding='utf-8') as f:
                    content = f.readlines()

                    # Filter out empty lines or lines with only whitespace
                    content = [line.strip() for line in content if line.strip()]

                    # Ensure there's a newline before appending content from the next file
                    if os.path.getsize(output_file_path) > 0:  # If output file is not empty
                        with open(output_file_path, 'rb+') as check_file:
                            check_file.seek(-1, os.SEEK_END)
                            last_char = check_file.read(1).decode()

                        if last_char != "\n":  # Append a newline if not present
                            output_file.write("\n")

                    # Write the non-empty lines to the output file
                    output_file.write("\n".join(content))

                    # Ensure the content written ends with a newline
                    if content:  # Only add a newline if content was written
                        output_file.write("\n")

    def add_columns_after_line_number(self, file_path):
        """
        Adds the split string (from the user input) after the line numbering in each line of the file.
        The input can contain an arbitrary number of parts separated by '-'.
        """
        # Check if the checkbox is checked and input is not empty
        if self.cols_after_id_checkbox.isChecked() and self.cols_after_ids_input.text().strip():
            try:
                # Get the input string and split it by '-'
                input_string = self.cols_after_ids_input.text().strip()
                split_string = input_string.split('-')

                # Read the content of the file
                with open(file_path, 'r', encoding='utf-8') as file:
                    lines = file.readlines()

                updated_lines = []
                for line in lines:
                    # Split the line into components
                    parts = line.strip().split()

                    if parts and parts[0].isdigit():  # Ensure the line starts with a number
                        # Prepare the new line with all split parts
                        updated_line = f"{parts[0]} {' '.join(split_string)} {' '.join(parts[1:])}"
                        updated_lines.append(updated_line)
                    else:
                        # In case the line doesn't start with a number, leave it unchanged
                        updated_lines.append(line.strip())

                # Write the updated content back to the file
                with open(file_path, 'w', encoding='utf-8') as file:
                    file.write("\n".join(updated_lines) + "\n")  # Ensure a newline at the end

                logger.info(f"Added columns after line numbers in {file_path}")
                self.show_success_message(f"Columns added to file: {file_path}")

            except Exception as e:
                self.show_error_message(f"Error adding columns after line numbers: {e}")
                logger.error(f"Error adding columns to file {file_path}: {e}")
        else:
            logger.info("Checkbox unchecked or input string is empty, skipping column addition.")

    def clean_file_content(self, file_path):
        """
        Cleans the content of a file by:
        - Removing empty lines.
        - Converting multiple spaces or tabs to a single space.
        """
        try:
            # Read the content of the file
            with open(file_path, 'r', encoding='utf-8') as file:
                lines = file.readlines()

            cleaned_lines = []
            for line in lines:
                # Strip leading/trailing whitespaces and reduce multiple spaces/tabs to a single space
                cleaned_line = ' '.join(line.split())
                
                # Only add non-empty lines after cleaning
                if cleaned_line:
                    cleaned_lines.append(cleaned_line)

            # Write the cleaned content back to the file
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write("\n".join(cleaned_lines) + "\n")  # Ensure a newline at the end of the file

            logger.info(f"Cleaned file content in {file_path}")
            self.show_success_message(f"File cleaned: {file_path}")

        except Exception as e:
            self.show_error_message(f"Error cleaning file content: {e}")
            logger.error(f"Error cleaning file content in {file_path}: {e}")

    def copy_qml_files(self):
        """Copy QML style files from the selected styles folder to the output directory."""
        # Ensure the checkbox is checked and a styles folder path is provided
        if not self.copy_styles_checkbox.isChecked():
            return  # Styles copying is not requested, so we return early

        styles_folder_path = self.styles_folder_path_input.text().strip()
        if not styles_folder_path or not os.path.isdir(styles_folder_path):
            self.show_error_message(f"Styles folder does not exist: {styles_folder_path}")
            return

        # Get the output folder path and create a 'qml' subfolder within it
        output_folder_path = self.output_select_input.text().strip()
        qml_output_folder = os.path.join(output_folder_path, "qml")

        try:
            os.makedirs(qml_output_folder, exist_ok=True)  # Create 'qml' folder if it doesn't exist
        except Exception as e:
            self.show_error_message(f"Error creating QML folder: {e}")
            return

        # Copy all .qml files from the styles folder to the 'qml' subfolder
        qml_files = [f for f in os.listdir(styles_folder_path) if f.endswith(".qml")]
        if not qml_files:
            self.show_error_message("No QML files found in the styles folder.")
            return

        try:
            for qml_file in qml_files:
                source = os.path.join(styles_folder_path, qml_file)
                destination = os.path.join(qml_output_folder, qml_file)
                shutil.copy(source, destination)
                logger.info(f"Copied {qml_file} to {qml_output_folder}")
            self.show_success_message(f"Successfully copied {len(qml_files)} QML file(s) to {qml_output_folder}")
            self.output_log.append(f"Successfully copied {len(qml_files)} QML file(s) to {qml_output_folder}")
        except Exception as e:
            self.show_error_message(f"Error copying QML files: {e}")

    def replace_geotag_symbols(self):
        """Replace & with $ in concatenated_output.txt if the standard_geotags_checkbox is checked."""
        # Check if the checkbox is checked
        if not self.standard_geotags_checkbox.isChecked():
            return  # If the checkbox isn't checked, we return early

        # Get the path of the concatenated output file
        output_directory = self.output_select_input.text().strip()
        concatenated_output_file = os.path.join(output_directory, self.CONCAT_OUTPUT_NAME)

        if not os.path.isfile(concatenated_output_file):
            self.show_error_message(f"Output file not found: {concatenated_output_file}")
            return

        try:
            # Read the contents of the file
            with open(concatenated_output_file, 'r', encoding='utf-8') as file:
                content = file.read()

            # Replace & with $
            updated_content = content.replace('&', '$')

            # Write the updated content back to the file
            with open(concatenated_output_file, 'w', encoding='utf-8') as file:
                file.write(updated_content)

            logger.info(f"Replaced '&' with '$' in {concatenated_output_file}")
            self.show_success_message(f"Geotag symbols replaced in {concatenated_output_file}")
            self.output_log.append(f"Geotag symbols replaced in {concatenated_output_file}")

        except Exception as e:
            self.show_error_message(f"Error updating geotag symbols: {e}")
            logger.error(f"Error updating geotag symbols in {concatenated_output_file}: {e}")

    def fix_line_numbering(self):
        """Fix line numbering in the concatenated_output.txt file if fix_lines_checkbox is checked."""
        # Check if the checkbox is checked
        if not self.fix_lines_checkbox.isChecked():
            return  # If the checkbox isn't checked, return early

        # Get the path of the concatenated output file
        output_directory = self.output_select_input.text().strip()
        concatenated_output_file = os.path.join(output_directory, self.CONCAT_OUTPUT_NAME)

        if not os.path.isfile(concatenated_output_file):
            self.show_error_message(f"Output file not found: {concatenated_output_file}")
            return

        try:
            # Read the content of the file
            with open(concatenated_output_file, 'r', encoding='utf-8') as file:
                lines = file.readlines()

            # Process each line: remove erroneous numbering and reassign correct numbering
            fixed_lines = []
            for idx, line in enumerate(lines, start=1):
                # Split each line by spaces and remove the first part (the erroneous numbering)
                parts = line.strip().split(" ", 1)  # Split into 2 parts, the first part (index) is discarded
                if len(parts) > 1:
                    new_line = f"{idx} {parts[1]}"  # Add correct numbering with a space
                    fixed_lines.append(new_line)
                else:
                    fixed_lines.append(line.strip())  # In case the line has no spaces or is invalid

            # Write the fixed content back to the file
            with open(concatenated_output_file, 'w', encoding='utf-8') as file:
                file.write("\n".join(fixed_lines))

            logger.info(f"Line numbering fixed in {concatenated_output_file}")
            self.show_success_message(f"Line numbering fixed in {concatenated_output_file}")
            self.output_log.append(f"Line numbering fixed in {concatenated_output_file}")

        except Exception as e:
            self.show_error_message(f"Error fixing line numbering: {e}")
            logger.error(f"Error fixing line numbering in {concatenated_output_file}: {e}")

    def run_normalize(self):
        if (not self.input_select.text().strip() or
            not self.output_select_input.text().strip()):
            self.show_error_message("Please fill all required fields in Tab 'Normalize'")
            return

        try:
            self.concatenate_files()
            output_directory = self.output_select_input.text().strip()
            output_file_path = os.path.join(output_directory, self.CONCAT_OUTPUT_NAME)

            # Clean the concatenated output file
            self.clean_file_content(output_file_path)

            self.copy_qml_files()
            self.replace_geotag_symbols()  # Call the function to replace & with $
            self.fix_line_numbering()  # Call the function to fix line numbering

            # Add columns after line numbering (if checkbox checked and input filled)
            self.add_columns_after_line_number(output_file_path)

            # update the process text field
            self.process_input_file_input.setText(output_file_path)

            self.show_success_message("Files successfully processed!")
        except Exception as e:
            self.handle_error(f"Error during file processing: {e}")


    # Process

    def load_command_history(self):
        """Load command history from file if it exists."""
        try:
            if os.path.exists(self.command_history_file):
                with open(self.command_history_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if content.strip():  # Check if file has non-whitespace content
                        self.command_code_field.setPlainText(content)
                        logger.info(f"Command history loaded from {self.command_history_file}")
        except Exception as e:
            self.show_error_message(f"Error loading command history: {e}")
            logger.error(f"Error loading command history: {e}")

    def save_command_history(self):
        """Save the current command history to a file."""
        try:
            with open(self.command_history_file, 'w', encoding='utf-8') as f:
                f.write(self.command_code_field.toPlainText())
            logger.info(f"Command history saved to {self.command_history_file}")
        except Exception as e:
            self.show_error_message(f"Error saving command history: {e}")
            logger.error(f"Error saving command history: {e}")

    def _split_command(self, command):
        """Helper function to split a command while preserving quoted strings."""
        parts = []
        current_part = ''
        in_quotes = False

        for char in command:
            if char == '"':
                in_quotes = not in_quotes
            elif char == ' ' and not in_quotes:
                if current_part:
                    parts.append(current_part)
                    current_part = ''
            else:
                current_part += char
        if current_part:
            parts.append(current_part)

        return parts

    def _extract_output_and_basename(self, parts):
        """Helper function to extract the output directory and basename from a command."""
        output_dir, basename = None, None

        for i, part in enumerate(parts):
            if part == '-o' and i + 1 < len(parts):
                output_dir = parts[i + 1].strip('"')
                self.show_success_message(f"Found output directory: {output_dir}")
            elif part == '-n' and i + 1 < len(parts):
                basename = parts[i + 1].strip('"')
                self.show_success_message(f"Found basename: {basename}")

        return output_dir, basename

    def add_command(self):
        """Process the files using the survey2gis command line tool."""
        try:
            # Check if any of the required fields are empty
            if (not self.process_input_file_input.text().strip() or
                not self.select_parser_input.text().strip() or
                not self.name_generated_file_input.text().strip()):
                self.show_error_message("Please fill all required fields in Tab 'Process'")
                return

            self.output_base_name = self.name_generated_file_input.text().strip()
            self.command_options = self.read_options()
            command = self.build_command(self.process_input_file_input.text().strip())

            self.output_log.clear()
            self.output_log.append(" ".join(command))
            self.command_code_field.append(" ".join(command))
            
            # Add this line to save the command history after appending the new command
            self.save_command_history()

        except FileNotFoundError as e:
            self.handle_error(f"File not found: {e}")

    # def process_files(self):
    #     """Process the files using the survey2gis command line tool."""
    #     try:
    #         # Check if any of the required fields are empty
    #     # Check if the required fields are filled
    #         if (not self.input_select.text().strip() or
    #             not self.output_basename_input.text().strip() or
    #             not self.output_directory_input.text().strip()):
    #             self.show_error_message("Please fill all required fields in Tab 'files'")
    #             return

    #         # Check if either parser_profiles_select or parser_select is filled
    #         # if (self.parser_profiles_select.currentText() == "Choose profile from list" and 
    #         #     not self.parser_select.text().strip()):
    #         #     self.show_error_message("Please select a parser profile or a parser file.")
    #         #     return

    #         self.command_options = self.read_options()
    #         input_files = self.input_select.text().split("; ")
    #         input_files = [os.path.normpath(file) for file in input_files]

    #         command = self.build_command(input_files)

    #         self.output_log.clear()
    #         self.output_log.append(" ".join(command))

    #         self.run_process(command)

    #     except FileNotFoundError as e:
    #         self.handle_error(f"File not found: {e}")
    #     except PermissionError as e:
    #         self.handle_error(f"Permission denied: {e}")
    #     except Exception as e:
    #         self.handle_error(f"An unexpected error occurred: {e}")

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

        command_options.parser_path = self.select_parser_input.text()
        return command_options

    def build_command(self, generated_input_file):
        """Build the command to execute survey2gis."""
        binary_path = self.get_binary_path()
        command = ['"'+binary_path+'"']
        
        # Include options and flags with the equal sign for options
        command.extend(self.command_options.to_command_list())
        
        # Add input file to the command (as a single argument)
        command.append(generated_input_file)
        
        return command

    def _parse_command(self, command):
        """Parse the command string into parts."""
        command_parts = []
        current_part = ''
        in_quotes = False

        for char in command:
            if char == '"':
                in_quotes = not in_quotes
                if not in_quotes and current_part:
                    command_parts.append(current_part)
                    current_part = ''
            elif char == ' ' and not in_quotes:
                if current_part:
                    command_parts.append(current_part)
                    current_part = ''
            else:
                current_part += char

        if current_part:
            command_parts.append(current_part)

        return [part for part in command_parts if part]  # Remove empty parts


    def handle_stdout_sequential(self):
        """Handle standard output from the current process."""
        data = self.process.readAllStandardOutput().data().decode()
        self.current_command_output.append(data)
        self.output_log.append(data)
        logger.debug(f"Process stdout: {data}")

    def handle_stderr_sequential(self):
        """Handle standard error from the current process."""
        data = self.process.readAllStandardError().data().decode()
        self.current_command_output.append(data)
        self.output_log.append(data)
        logger.debug(f"Process stderr: {data}")

    def run_process_sequential(self, command_parts):
        """Run a single process and handle its completion."""
        try:
            self.process = QtCore.QProcess(self)

            # Connect signals
            self.process.readyReadStandardOutput.connect(self.handle_stdout_sequential)
            self.process.readyReadStandardError.connect(self.handle_stderr_sequential)
            self.process.finished.connect(self.handle_process_finished_sequential)

            # Extract the program path and arguments
            program = command_parts[0]
            arguments = command_parts[1:]

            logger.debug(f"Executing program: {program}")
            logger.debug(f"With arguments: {arguments}")

            # Start the process
            self.process.start(program, arguments)

            # Wait for process to start
            if not self.process.waitForStarted(3000):  # 3 second timeout
                raise Exception("Process failed to start within timeout period")

            logger.debug("Process started successfully")

        except Exception as e:
            self.handle_error(f"Failed to start process: {e}")
            logger.error(f"Process start error: {str(e)}")

    def _handle_command_failure(self, exit_code, output_text):
        """Handle the failure of a command."""
        error_message = (f"Command {self.current_command_index + 1} failed "
                         f"with exit code {exit_code}")
        if "ERROR" in output_text:
            error_message += f"\nError in survey2gis output detected"

        self.output_log.append(f"\n{error_message}")
        self.show_error_message(error_message)
        logger.error(error_message)

    def run_commands(self):
        logger.info("Running commands")
        """Run all commands from the command code field sequentially."""
        try:
            # Get commands from the field and filter out empty lines
            commands = [cmd.strip() for cmd in self.command_code_field.toPlainText().split('\n') if cmd.strip()]
            
            if not commands:
                self.show_error_message("No commands found to execute")
                return
                
            self.current_commands = commands
            self.current_command_index = 0
            
            # Clear the output log before starting new command sequence
            self.output_log.clear()
            self.output_log.append("Starting command sequence execution...")
            
            # Start with the first command
            self.run_next_command()
            
        except Exception as e:
            self.handle_error(f"Error preparing commands: {e}")

    def run_next_command(self):
        """Run the next command in the sequence."""
        if self.current_command_index >= len(self.current_commands):
            self.show_success_message("All commands completed successfully!")

            # All s2g commands finished – Attempt to load files into geopackage
            self.load_survey_data()
            return

        command = self.current_commands[self.current_command_index]
        try:
            command_parts = self._parse_command(command)

            self.output_log.append(f"\n{'='*50}")
            self.output_log.append(f"Executing command {self.current_command_index + 1}/{len(self.current_commands)}:")
            self.output_log.append(command)
            self.output_log.append(f"Command parts: {command_parts}")  # Debug output
            self.output_log.append(f"{'='*50}\n")

            # Store current command output for interpretation
            self.current_command_output = []
            self.run_process_sequential(command_parts)

        except Exception as e:
            self.handle_error(f"Error processing command: {e}")

    def handle_process_finished_sequential(self, exit_code, exit_status):
        """Handle the completion of a single process in the sequence."""
        output_text = ''.join(self.current_command_output)

        self.output_log.append(f"\nProcess finished with exit code: {exit_code}")
        log_plugin_message(f"Process finished with exit code: {exit_code}")
        log_plugin_message(f"Process output: {output_text}")

        if exit_code == 0 and "ERROR" not in output_text:
            self.output_log.append(f"\nCommand {self.current_command_index + 1} completed successfully")
            log_plugin_message(f"Command {self.current_command_index + 1} completed successfully")

            # Move to next command
            self.current_command_index += 1
            self.run_next_command()
        else:
            self._handle_command_failure(exit_code, output_text)

    def scan_directory_for_spatialfiles(self, directory):

        # Initialize an empty dictionary with 'shp' and 'geojson' as top-level keys
        grouped_files = {
            'shp': {},
            'geojson': {}
        }

        # Compile regex to match the keywords polygon, point, or line (case-insensitive)
        keyword_pattern = re.compile(r'(poly|point|line)', re.IGNORECASE)

        # Define valid file extensions
        valid_extensions = ['*.shp', '*.geojson']

        # Walk through the directory and find matching files
        for root, dirs, files in os.walk(directory):
            for extension in valid_extensions:
                for file in fnmatch.filter(files, extension):
                    # Check if the file name contains any of the keywords
                    match = keyword_pattern.search(file)
                    if match:
                        file_lower = file.lower()
                        # Split the filename after the first underscore
                        prefix = file.split('_', 1)[0]
                        
                        # Determine the file type (either 'shp' or 'geojson')
                        file_type = 'shp' if file.endswith('.shp') else 'geojson'
                        
                        # Ensure the prefix exists under the correct file type
                        if prefix not in grouped_files[file_type]:
                            grouped_files[file_type][prefix] = {'polygon': [], 'line': [], 'point': []}

                        # Classify and add the file to the appropriate list under the file type and prefix
                        file_path = os.path.join(root, file)
                        if 'poly' in file_lower:
                            grouped_files[file_type][prefix]['polygon'].append(file_path)
                        elif 'line' in file_lower:
                            grouped_files[file_type][prefix]['line'].append(file_path)
                        elif 'point' in file_lower:
                            grouped_files[file_type][prefix]['point'].append(file_path)

        # Convert the dictionary to the desired format: type -> prefix -> list with [polygons, lines, points]
        result = {}
        for file_type, prefixes in grouped_files.items():
            result[file_type] = {}
            for prefix, file_dict in prefixes.items():
                # Combine the lists into the desired order: polygons first, lines second, points third
                result[file_type][prefix] = file_dict['polygon'] + file_dict['line'] + file_dict['point']

        self.intermediate_file_dict = result

        return result

    def handle_file_cleanup(self):
        # Step 1: Get base path
        base_path = os.path.dirname(__file__)
        
        
        # Step 3: Check for the presence of `keep_files`
        keep_files_path = os.path.join(base_path, 'keep_files')
        
        # Step 4: If `keep_files` does not exist, delete files listed in the dictionary
        if not os.path.exists(keep_files_path):
            for file_type, groups in self.intermediate_file_dict.items():
                for group, file_list in groups.items():
                    for file_path in file_list:
                        # Delete each file in the list if it exists
                        if os.path.exists(file_path):
                            os.remove(file_path)
                            log_plugin_message(f"Deleted: {file_path}")
                        else:
                            log_plugin_message(f"File not found, could not delete: {file_path}", "error")
        else:
            log_plugin_message("keep_files file found, skipping deletion.")

    def load_survey_data(self):
        """
        Load supported survey data formats (shapefiles, geojson) and save them to a single GeoPackage.
        """
        try:
            log_plugin_message("=== Starting load_survey_data function ===")

            # Get all commands from the command code field
            commands = [cmd.strip() for cmd in self.command_code_field.toPlainText().split('\n') if cmd.strip()]
            log_plugin_message(f"Found {len(commands)} commands to process")

            if not commands:
                logger.error("No commands found to process")
                return

            root = QgsProject.instance().layerTreeRoot()

            processed_basenames = set()
            log_plugin_message("Initializing processed_basenames set")

            # Initialize a list to hold all layers across multiple basenames
            all_shape_layers = []
            all_geojson_layers = []

            # Use a single GeoPackage file for all layers
            output_dir = None  # We'll update this as we extract it from commands
            gpkg_path = None   # GeoPackage path will be defined when we know output_dir

            for command_index, command in enumerate(commands):
                log_plugin_message(f"\nProcessing command {command_index + 1}/{len(commands)}")
                logger.debug(f"Command: {command}")

                # Split the command while preserving quoted strings
                parts = self._split_command(command)
                logger.debug(f"Parsed command parts: {parts}")

                # Extract output directory and basename from command
                current_output_dir, basename = self._extract_output_and_basename(parts)
                if not current_output_dir or not basename:
                    logger.warning(f"Missing output directory or basename in command: {command}")
                    continue

                # Set the output directory and GeoPackage path
                if output_dir is None:
                    output_dir = current_output_dir
                    gpkg_path = os.path.join(output_dir, "merged_data.gpkg")  # One GeoPackage for all

                # Skip if already processed
                if basename in processed_basenames:
                    logger.warning(f"Skipping already processed basename: {basename}")
                    continue

                log_plugin_message(f"Adding {basename} to processed basenames")
                processed_basenames.add(basename)
                logger.debug(f"Current processed basenames: {processed_basenames}")

                # Process Shapefiles
                all_shape_layer = self.load_shapefiles(current_output_dir, basename)
                if all_shape_layer:
                    all_shape_layers.append(all_shape_layer)
                
                # Process GeoJSON (if available)
                # all_geojson_layers = self.load_geojson(current_output_dir, basename) #read 
                geojson_layer = self.load_geojson_files(current_output_dir, basename) #read 
                if geojson_layer:
                    all_geojson_layers.append(geojson_layer)



            # # Save all layers (from all basenames) to a single GeoPackage if any were loaded
            # if all_shape_layers:
            #     group = root.addGroup("Merged Data")
            #     group.setExpanded(True)
            #     self.save_shapefile_layers_to_geopackage(all_shape_layers, gpkg_path, group) #write
            
            # # Save all layers (from all basenames) to a single GeoPackage if any were loaded
            if all_geojson_layers:
                splitted_geojson = self.split_geojson_files(all_geojson_layers)

            all = self.scan_directory_for_spatialfiles(current_output_dir)
            log_plugin_message("Created files are")
            log_plugin_message(str(all))
            log_plugin_message(f"gpg path ist {str(gpkg_path)}")


            self.iter_found_files_and_pass_to_geopackage(all, gpkg_path)

                # if splitted_geojson:
                #     geopackage_layer = self.geojsons_to_gpkg(splitted_geojson, gpkg_path)
                
                # if geopackage_layer:
                #     group = root.addGroup("Merged Data")
                #     group.setExpanded(True)
                #     self.add_layers_from_geopackage(gpkg_path, group)

                # self.show_success_message(str(all_geojson_layers))

            log_plugin_message("=== Completed load_survey_data function ===")
            
        except Exception as e:
            log_plugin_message(f"Error: {str(e)}", "error")

    def load_shapefiles(self, output_dir, basename):
        """
        Load shapefiles (point, line, polygon) and return a list of QgsVectorLayers.
        """
        log_plugin_message(f"Loading shapefiles for {basename}")
        suffixes = ["_line.shp", "_point.shp", "_poly.shp"]
        layers = self._load_layers_by_format(output_dir, basename, suffixes, 'shp')

        if len(layers) > 0:
            log_plugin_message(f"Successfully loaded shapefiles for {basename}")
            return layers
        else:
            log_plugin_message(f"No shapefiles found for {basename}")

        return False

    def load_geojson_files(self, output_dir, basename):
        """
        Load shapefiles (point, line, polygon) and return a list of QgsVectorLayers.
        """
        log_plugin_message(f"Loading geojson for {basename}")
        file_path = os.path.join(output_dir, basename + "_all.geojson")
        if os.path.exists(file_path):
            log_plugin_message(f"Loading geojson file: {file_path}")
            return file_path

        return False

    def _load_layers_by_format(self, output_dir, basename, suffixes, format_name):
        """Load files of a specific format and return a list of QgsVectorLayers."""
        layers = []
        for suffix in suffixes:
            file_path = os.path.join(output_dir, suffix if format_name != "shp" else basename + suffix)
            if os.path.exists(file_path):
                log_plugin_message(f"Loading {format_name} file: {file_path}")
                layer = QgsVectorLayer(file_path, os.path.splitext(os.path.basename(file_path))[0], "ogr")

                if layer.isValid():
                    layers.append(layer)
                    log_plugin_message(f"Successfully added {format_name} layer: {layer.name()}")
                else:
                    logger.error(f"Failed to create valid layer for: {file_path}")

        return layers

    def split_geojson_to_gpkg(self, input_geojson_path, output_gpkg):
        # Open and load the GeoJSON file
        with open(input_geojson_path, 'r') as geojson_file:
            geojson_data = json.load(geojson_file)

        # Prepare dictionary to collect geometries by type
        geometry_collections = {
            'Point': [],
            'PointZ': [],
            'LineString': [],
            'LineStringZ': [],
            'Polygon': [],
            'PolygonZ': []
        }

        # Classify features based on geometry type
        for feature in geojson_data.get('features', []):
            geometry = feature.get('geometry')
            geom_type = geometry.get('type')
            
            # Handle Z types, assuming they have extra coordinates
            if geom_type == 'Point' and len(geometry.get('coordinates', [])) == 3:
                geom_type = 'PointZ'
            elif geom_type == 'LineString' and any(len(coord) == 3 for coord in geometry.get('coordinates', [])):
                geom_type = 'LineStringZ'
            elif geom_type == 'Polygon' and any(len(coord) == 3 for ring in geometry.get('coordinates', []) for coord in ring):
                geom_type = 'PolygonZ'
            
            # Append feature to appropriate geometry collection
            if geom_type in geometry_collections:
                geometry_collections[geom_type].append(feature)

        # Get the directory of the input file
        input_directory = os.path.dirname(input_geojson_path)
        base_filename = os.path.splitext(os.path.basename(input_geojson_path))[0]

        # List to store names of created layers (for tracking)
        created_layers = []

        # Create the output GPKG file
        drv = ogr.GetDriverByName('GPKG')
        # if os.path.exists(output_gpkg):
        #     os.remove(output_gpkg)  # Remove existing file if present
        out_ds = drv.CreateDataSource(output_gpkg)

        # Function to write features to a GeoPackage layer
        def write_to_gpkg(geometry_type, features, base_filename, output_ds):
            if features:
                # Create temporary GeoJSON structure for features
                temp_geojson = {
                    "type": "FeatureCollection",
                    "features": features
                }
                # Create temporary file to store the filtered features
                temp_geojson_file = f"{base_filename}_{geometry_type}.geojson"
                temp_geojson_path = os.path.join(input_directory, temp_geojson_file)
                with open(temp_geojson_path, 'w') as temp_file:
                    json.dump(temp_geojson, temp_file, indent=2)

                # Open the temporary GeoJSON file with OGR
                ds = ogr.Open(temp_geojson_path)
                if ds is None:
                    print(f"Could not open {temp_geojson_path}")
                    return

                lyr = ds.GetLayer()

                # Layer name (based on filename without extension)
                layer_name = os.path.splitext(os.path.basename(temp_geojson_file))[0]

                # Copy the layer to the output GeoPackage
                output_ds.CopyLayer(lyr, layer_name)
                created_layers.append(layer_name)

                # Cleanup temporary GeoJSON file
                os.remove(temp_geojson_path)

                # Cleanup
                del ds

        # Write each geometry collection to a GPKG layer
        for geom_type, features in geometry_collections.items():
            write_to_gpkg(geom_type, features, base_filename, out_ds)

        # Cleanup
        del out_ds

        return created_layers


    def split_geojson_files(self, all_geojson_files):
        

        # List to store the paths of created GeoJSON files
        geojson_files = []

        for input_geojson_path in all_geojson_files:   
            # Open and load the GeoJSON file
            with open(input_geojson_path, 'r') as geojson_file:
                geojson_data = json.load(geojson_file)

            # Prepare dictionary to collect geometries by type
            geometry_collections = {
                'Point': [],
                'PointZ': [],
                'LineString': [],
                'LineStringZ': [],
                'Polygon': [],
                'PolygonZ': []
            }

            # Classify features based on geometry type
            for feature in geojson_data.get('features', []):
                geometry = feature.get('geometry')
                geom_type = geometry.get('type')
                
                # Handle Z types, assuming they have extra coordinates


                if geom_type == 'Polygon' and any(len(coord) == 3 for ring in geometry.get('coordinates', []) for coord in ring):
                    geom_type = 'PolygonZ'
                elif geom_type == 'LineString' and any(len(coord) == 3 for coord in geometry.get('coordinates', [])):
                    geom_type = 'LineStringZ'
                elif geom_type == 'Point' and len(geometry.get('coordinates', [])) == 3:
                    geom_type = 'PointZ'

                # Append feature to appropriate geometry collection
                if geom_type in geometry_collections:
                    geometry_collections[geom_type].append(feature)

            # Get the directory of the input file
            input_directory = os.path.dirname(input_geojson_path)
            base_filename = os.path.splitext(os.path.basename(input_geojson_path))[0]


            # Save each geometry collection to a separate GeoJSON file
            for geom_type, features in geometry_collections.items():
                if features:
                    temp_geojson = {
                        "type": "FeatureCollection",
                        "features": features
                    }
                    temp_geojson_file = f"{base_filename}_{geom_type}.geojson"
                    temp_geojson_path = os.path.join(input_directory, temp_geojson_file)
                    with open(temp_geojson_path, 'w') as temp_file:
                        json.dump(temp_geojson, temp_file, indent=2)

                    geojson_files.append(temp_geojson_path)

        return geojson_files
    
    # def geojsons_and_shapefiles_to_gpkg(self, files, out_ds):

    #     log_plugin_message("received files " + str(files))

    #     # List to store names of created layers (for tracking)
    #     created_layers = []

    #     # Loop over each file (GeoJSON or Shapefile) and copy it to the GeoPackage
    #     for file in files:
    #         ds = ogr.Open(file)
    #         if ds is None:
    #             print(f"Could not open {file}")
    #             continue

    #         lyr = ds.GetLayer()

    #         # Layer name (based on filename without extension)
    #         layer_name = os.path.splitext(os.path.basename(file))[0]

    #         # Copy the layer to the output GeoPackage
    #         out_ds.CopyLayer(lyr, layer_name)
    #         created_layers.append(layer_name)

    #         # Cleanup
    #         del ds

    #     return created_layers


    def load_alias_mapping(self, alias_file):
        """Load alias mappings from an .ini file."""
        config = configparser.ConfigParser()
        config.read(alias_file)
        # Assume all mappings are under a single section called 'aliases'
        return dict(config['aliases']) if 'aliases' in config else {}

    def get_renamed_layer_defn(self, layer):
        """Create a new LayerDefn with renamed fields based on the alias mapping."""
        layer_defn = layer.GetLayerDefn()
        new_layer_defn = ogr.FeatureDefn()
        
        for i in range(layer_defn.GetFieldCount()):
            field_defn = layer_defn.GetFieldDefn(i)
            original_name = field_defn.GetName()
            alias_name = self.alias_mapping.get(original_name, original_name)  # Use alias if available
            
            new_field_defn = ogr.FieldDefn(alias_name, field_defn.GetType())
            new_layer_defn.AddFieldDefn(new_field_defn)
            
        return new_layer_defn

    def geojsons_and_shapefiles_to_gpkg(self, files, out_ds):
        """Add layers from GeoJSON/Shapefile files to a GeoPackage with renamed fields."""
        log_plugin_message("received files " + str(files))

        # List to store names of created layers (for tracking)
        created_layers = []

        # Loop over each file (GeoJSON or Shapefile) and copy it to the GeoPackage
        for file in files:
            ds = ogr.Open(file)
            if ds is None:
                print(f"Could not open {file}")
                continue

            lyr = ds.GetLayer()

            # Layer name (based on filename without extension)
            layer_name = os.path.splitext(os.path.basename(file))[0]

            # Get new layer definition with renamed fields
            new_layer_defn = self.get_renamed_layer_defn(lyr)
            new_layer = out_ds.CreateLayer(layer_name, geom_type=lyr.GetGeomType())

            # Add fields from new layer definition to the new layer
            for i in range(new_layer_defn.GetFieldCount()):
                new_layer.CreateField(new_layer_defn.GetFieldDefn(i))

            # Copy features with renamed fields to the new layer
            for feature in lyr:
                new_feature = ogr.Feature(new_layer.GetLayerDefn())
                for i in range(lyr.GetLayerDefn().GetFieldCount()):
                    original_field_name = lyr.GetLayerDefn().GetFieldDefn(i).GetName()
                    alias_field_name = self.alias_mapping.get(original_field_name, original_field_name)
                    
                    # Set the field in the new feature using the renamed field name
                    new_feature.SetField(alias_field_name, feature.GetField(original_field_name))

                # Set the geometry for the new feature
                new_feature.SetGeometry(feature.GetGeometryRef())
                new_layer.CreateFeature(new_feature)
                new_feature = None  # Clean up

            created_layers.append(layer_name)

            # Cleanup
            del ds

        return created_layers

    def iter_found_files_and_pass_to_geopackage(self, data, output_gpkg):

        # Create the output GPKG file only once
        drv = ogr.GetDriverByName('GPKG')
        out_ds = drv.CreateDataSource(output_gpkg)

        if os.path.exists(output_gpkg):
            log_plugin_message("geopackage exists!")
            # os.remove(output_gpkg)  # Remove existing file if present

            group_name = "My Merged Data"
            # Iterate over the dictionary
            log_plugin_message(f"geopackage process!")
            log_plugin_message(str(data.items()))
            for file_type, groups in data.items():
                self.show_success_message(f"File Type: {file_type}")  # 'shp' or 'geojson'
                for group, file_list in groups.items():
                    log_plugin_message(f"Processing Group: {group}")
                    log_plugin_message("list is")
                    log_plugin_message(str(file_list))
                    group_name = group
                    # Pass the open GeoPackage data source (out_ds) to the function
                    self.geojsons_and_shapefiles_to_gpkg(file_list, out_ds)

            self.add_layers_from_geopackage(output_gpkg)

            # Cleanup: Close the GeoPackage
            del out_ds

    def geojsons_to_gpkg(self, geojson_files, output_gpkg):
        # Create the output GPKG file
        drv = ogr.GetDriverByName('GPKG')
        # if os.path.exists(output_gpkg):
        #     os.remove(output_gpkg)  # Remove existing file if present
        out_ds = drv.CreateDataSource(output_gpkg)

        # List to store names of created layers (for tracking)
        created_layers = []

        # Loop over each GeoJSON file and copy it to the GeoPackage
        for geojson_file in geojson_files:
            ds = ogr.Open(geojson_file)
            if ds is None:
                log_plugin_message(f"Could not open {geojson_file}", "error")
                continue

            lyr = ds.GetLayer()

            # Layer name (based on filename without extension)
            layer_name = os.path.splitext(os.path.basename(geojson_file))[0]

            # Copy the layer to the output GeoPackage
            out_ds.CopyLayer(lyr, layer_name)
            created_layers.append(layer_name)

            # Cleanup
            del ds

        # Cleanup the GPKG data source
        # del out_ds

        return created_layers

    def load_geojson(self, output_dir, basename):
        """
        Load a GeoJSON file, separate its features by geometry type (Point, Line, Polygon),
        and return them as separate QgsVectorLayers.
        """
        geojson_filename = f"{basename}_all.geojson"
        geojson_path = os.path.join(output_dir, geojson_filename)
        layers = []

        if os.path.exists(geojson_path):
            log_plugin_message(f"Loading GeoJSON file: {geojson_path}")
            output_gpkg = os.path.join(os.path.dirname(geojson_path), 'output.gpkg')
            created_layers = self.split_geojson_to_gpkg(geojson_path, output_gpkg)
            log_plugin_message(f"Created layers in GeoPackage: {created_layers}")
            root = QgsProject.instance().layerTreeRoot()
            group = root.addGroup("My Merged DataX")
            group.setExpanded(True)
            self.add_layers_from_geopackage(output_gpkg, group)

        return layers

    def save_shapefile_layers_to_geopackage(self, all_layers, gpkg_path, group):
        """
        Save all provided layers to a single GeoPackage.
        Args:
            all_layers (list): List of QgsVectorLayer objects
            gpkg_path (str): Path where the GeoPackage should be saved
            group: Layer group for organization
        Returns:
            bool: True if successful, False otherwise
        """
        if not all_layers:
            self.show_error_message("No layers to save")
            return False



        # Remove existing file if it exists
        if os.path.exists(gpkg_path):
            try:
                os.remove(gpkg_path)
                log_plugin_message(f"Removed existing GeoPackage: {gpkg_path}")
            except Exception as e:
                self.show_error_message(f"Failed to remove existing GeoPackage: {str(e)}")
                return False



        # Create a coordinate transform context
        transform_context = QgsProject.instance().transformContext()
        overall_success = True



        for index, layers in enumerate(all_layers):
            for layer in layers:
                self.show_success_message(f"shape {layer}")
                if not layer.isValid():
                    self.show_error_message(f"Layer {layer.name()} is invalid")
                    continue


                # Configure save options
                options = QgsVectorFileWriter.SaveVectorOptions()
                options.driverName = "GPKG"
                options.fileEncoding = "UTF-8"  # Explicitly set UTF-8 encoding
                
                # Create a unique layer name
                base_layer_name = layer.name().replace(" ", "_")
                options.layerName = f"{base_layer_name}_{index}"

                # Set action based on whether file exists
                if index == 0:
                    options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile
                else:
                    options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer

                # Add all fields from the source layer
                options.attributes = range(layer.fields().count())

                try:
                    # Write the layer
                    error, error_message, new_filepath, new_layer = QgsVectorFileWriter.writeAsVectorFormatV3(
                        layer,
                        gpkg_path,
                        transform_context,
                        options
                    )

                    if error != QgsVectorFileWriter.NoError:
                        self.show_error_message(f"Failed to save layer {options.layerName}: {error_message}")
                        overall_success = False
                    else:
                        self.show_success_message(f"Successfully saved layer: {options.layerName}")
                        
                        # Verify the layer was actually written
                        if not os.path.exists(gpkg_path):
                            self.show_error_message(f"GeoPackage file was not created at: {gpkg_path}")
                            overall_success = False
                            break

                except Exception as e:
                    self.show_error_message(f"Exception while saving layer {options.layerName}: {str(e)}")
                    overall_success = False

        if overall_success:
            self.show_success_message(f"GeoPackage saved successfully at: {gpkg_path}")
            # Load the GeoPackage into QGIS
            self.add_layers_from_geopackage(gpkg_path, group)
        else:
            self.show_error_message("Failed to save some layers to GeoPackage")

        return overall_success

    def add_layers_from_geopackage(self, gpkg_path):
        """
        Dynamically create groups based on layer name prefixes and add corresponding layers from the GeoPackage.
        """
        # Open the GeoPackage using OGR
        conn = ogr.Open(gpkg_path)
        if conn is None:
            log_plugin_message("Failed to open GeoPackage.", "error")
            return

        # Reference to the root of the QGIS layer tree
        root = QgsProject.instance().layerTreeRoot()

        layer_count = conn.GetLayerCount()
        
        # Dictionary to keep track of groups to avoid finding or creating them repeatedly
        group_dict = {}
        
        # Iterate over all layers in the GeoPackage
        for i in range(layer_count):
            layer = conn.GetLayerByIndex(i)
            layer_name = layer.GetName()
            
            # Split the layer name at the first underscore to get the group name
            group_name = layer_name.split('_', 1)[0]

            # Check if the group already exists in the dictionary
            if group_name not in group_dict:
                # Find the group in the layer tree; if it does not exist, create it
                group = root.findGroup(group_name)
                if group is None:
                    group = root.addGroup(group_name)
                # Store the group reference in the dictionary
                group_dict[group_name] = group
            else:
                # Get the existing group from the dictionary
                group = group_dict[group_name]
            
            # Construct the layer URI for QGIS
            layer_uri = f"{gpkg_path}|layername={layer_name}"

            # Create a QgsVectorLayer without adding it directly to the project
            new_layer = QgsVectorLayer(layer_uri, layer_name, "ogr")
            
            # Check if the layer is valid before adding it to the group
            if new_layer.isValid():
                # Add the layer to the project
                QgsProject.instance().addMapLayer(new_layer, False)  # Add layer to project without showing it
                group.insertLayer(0, new_layer)  # Insert layer at the top of the group
                log_plugin_message(f"Successfully added layer: {layer_name} under group: {group_name}")
            else:
                log_plugin_message(f"Failed to add layer: {layer_name}", "error")

            # Todo: cleanup files
            # self.handle_file_cleanup()

def classFactory(iface):
    return S2gDataProcessorDockWidget(iface)

