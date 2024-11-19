import os
import platform
import logging
from PyQt5 import QtWidgets, uic, QtCore, QtGui
from qgis.core import QgsProject, QgsVectorLayer, Qgis, QgsMessageLog
from qgis.utils import iface
from dataclasses import dataclass, field
import shutil
import uuid
from qgis.core import QgsVectorFileWriter, QgsProject, QgsDataSourceUri
from osgeo import ogr

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
        """Constructor."""
        super(S2gDataProcessorDockWidget, self).__init__(parent)
        self.setupUi(self)

        self.ensure_binary_executable()

        self.output_base_name = None
        self.output_directory = None
        self.CONCAT_OUTPUT_NAME = "concatenated_output.txt"
        # Add this line after your other initializations
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
        
        return os.path.normpath('"'+path+'"')

    def save_command_history(self):
        """Save the current command history to a file."""
        try:
            with open(self.command_history_file, 'w', encoding='utf-8') as f:
                f.write(self.command_code_field.toPlainText())
            logger.info(f"Command history saved to {self.command_history_file}")
        except Exception as e:
            self.show_error_message(f"Error saving command history: {e}")
            logger.error(f"Error saving command history: {e}")

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

    def get_selected_label_mode_poly(self):
        """Get the selected label mode from the QComboBox."""
        return self.label_mode_poly.currentText()

    def show_message(self, message, level=Qgis.Info):
        """Display a message using QgsMessageBar."""
        message_bar = iface.messageBar()
        message_bar.pushMessage("Plugin Message", message, level=level, duration=5)


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

        command_options.parser_path = self.select_parser_input.text()
        return command_options

    def build_command(self, generated_input_file):
        """Build the command to execute survey2gis."""
        binary_path = self.get_binary_path()
        command = [binary_path]
        
        # Include options and flags with the equal sign for options
        command.extend(self.command_options.to_command_list())
        
        # Add input file to the command (as a single argument)
        command.append(generated_input_file)
        
        return command


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
            self.load_shapefiles()
            return
            
        command = self.current_commands[self.current_command_index]
        try:
            # Properly handle the command string, respecting quoted paths
            command_parts = []
            current_part = ''
            in_quotes = False
            
            for char in command:
                if char == '"':
                    if in_quotes:
                        if current_part:
                            command_parts.append(current_part)
                            current_part = ''
                    in_quotes = not in_quotes
                elif char == ' ' and not in_quotes:
                    if current_part:
                        command_parts.append(current_part)
                        current_part = ''
                else:
                    current_part += char
                    
            if current_part:
                command_parts.append(current_part)
                
            # Remove any empty parts
            command_parts = [part for part in command_parts if part]
            
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
            
            # Log the exact command being executed
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

    def handle_process_finished_sequential(self, exit_code, exit_status):
        """Handle the completion of a single process in the sequence."""
        # Join all output for interpretation
        output_text = ''.join(self.current_command_output)
        
        self.output_log.append(f"\nProcess finished with exit code: {exit_code}")
        logger.debug(f"Process finished with exit code: {exit_code}")
        logger.debug(f"Process output: {output_text}")
        
        if exit_code == 0 and "ERROR" not in output_text:
            self.output_log.append(f"\nCommand {self.current_command_index + 1} completed successfully")
            logger.info(f"Command {self.current_command_index + 1} completed successfully")
            
            # Try to load shapefiles if they were produced
            # try:
            #     self.load_shapefiles(output_text)
            # except Exception as e:
            #     logger.warning(f"Non-critical error loading shapefiles: {e}")
            
            # Move to next command
            self.current_command_index += 1
            self.run_next_command()
        else:
            error_message = (f"Command {self.current_command_index + 1} failed "
                            f"with exit code {exit_code}")
            if "ERROR" in output_text:
                error_message += f"\nError in survey2gis output detected"
            
            self.output_log.append(f"\n{error_message}")
            self.show_error_message(error_message)
            logger.error(error_message)

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

        


    def load_shapefiles(self):
        """
        Load produced shapefiles into QGIS based on commands in command_code_field.
        Each command contains output directory (-o) and basename (-n) options.
        """
        try:
            self.show_success_message("=== Starting load_shapefiles function ===")
            
            # Get all commands from the command code field
            commands = [cmd.strip() for cmd in self.command_code_field.toPlainText().split('\n') if cmd.strip()]
            self.show_success_message(f"Found {len(commands)} commands to process")
            
            if not commands:
                logger.error("No commands found to process")
                return

            root = QgsProject.instance().layerTreeRoot()
            shapefile_suffixes = ["_line.shp", "_point.shp", "_poly.shp"]
            
            # Keep track of processed basenames to avoid duplicates
            processed_basenames = set()
            self.show_success_message("Initializing processed_basenames set")

            for command_index, command in enumerate(commands):
                self.show_success_message(f"\nProcessing command {command_index + 1}/{len(commands)}")
                logger.debug(f"Command: {command}")

                # Split the command while preserving quoted strings
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

                logger.debug(f"Parsed command parts: {parts}")

                # Extract output directory and basename from command
                output_dir = None
                basename = None
                
                for i, part in enumerate(parts):
                    if part == '-o' and i + 1 < len(parts):
                        output_dir = parts[i + 1].strip('"')
                        self.show_success_message(f"Found output directory: {output_dir}")
                    elif part == '-n' and i + 1 < len(parts):
                        basename = parts[i + 1].strip('"')
                        self.show_success_message(f"Found basename: {basename}")

                if not output_dir or not basename:
                    logger.warning(f"Missing output directory or basename in command: {command}")
                    continue
                        
                # Skip if we've already processed this basename
                if basename in processed_basenames:
                    logger.warning(f"Skipping already processed basename: {basename}")
                    continue
                
                self.show_success_message(f"Adding {basename} to processed basenames")
                processed_basenames.add(basename)
                logger.debug(f"Current processed basenames: {processed_basenames}")

                # Check if any shapefiles exist for this basename before creating the group
                has_shapefiles = False
                for suffix in shapefile_suffixes:
                    full_path = os.path.join(output_dir, basename + suffix)
                    if os.path.exists(full_path):
                        has_shapefiles = True
                        self.show_success_message(f"Found shapefile: {full_path}")
                        break
                            
                if not has_shapefiles:
                    logger.warning(f"No shapefiles found for basename: {basename}")
                    continue

                self.show_success_message(f"Creating group for basename: {basename}")
                group = root.addGroup(basename)
                all_layers = []

                # Check for and load each possible shapefile
                for suffix in shapefile_suffixes:
                    shapefile_path = os.path.join(output_dir, basename + suffix)
                    
                    if os.path.exists(shapefile_path):
                        self.show_success_message(f"Loading shapefile: {shapefile_path}")
                        layer_name = os.path.splitext(os.path.basename(shapefile_path))[0]
                        layer = QgsVectorLayer(shapefile_path, layer_name, "ogr")

                        if layer.isValid():
                            # QgsProject.instance().addMapLayer(layer, False)
                            # group.addLayer(layer)
                            all_layers.append(layer)
                            self.show_success_message(f"Successfully added layer: {layer_name}")
                        else:
                            logger.error(f"Failed to create valid layer for: {shapefile_path}")

                group.setExpanded(True)
                self.show_success_message(f"Finished processing basename: {basename}")
                self.save_layers_to_geopackage(all_layers, output_dir, group)

            self.show_success_message("=== Completed load_shapefiles function ===")

        except Exception as e:
            logger.error(f"Error in load_shapefiles: {str(e)}")
            logger.error(f"Exception details:", exc_info=True)  # This will log the full stack trace
            self.show_error_message(f"Error loading shapefiles: {str(e)}")


    def save_layers_to_geopackage(self, all_layers, output_dir, group):
        # Generate a unique filename
        unique_name = f"geopackage_{uuid.uuid4().hex}.gpkg"
        gpkg_path = os.path.join(output_dir, unique_name)
        self.show_success_message(f"GeoPackage path: {gpkg_path}")

        # Create a coordinate transform context
        transform_context = QgsProject.instance().transformContext()

        # Create options for the GeoPackage
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"  # GeoPackage format
        options.fileEncoding = all_layers[0].dataProvider().encoding()  # Use the encoding of the first layer

        # Initialize a flag to track overall success
        overall_success = True

        # Iterate over the layers and save each one to the GeoPackage
        for index, layer in enumerate(all_layers):
            # Set layer-specific options
            options.layerName = f"{layer.name()}_{index}"  # Use the layer name correctly
            
            # For the first layer, create the file. For subsequent layers, append.
            if index == 0:
                options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile  # Create the file on the first iteration
            else:
                options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer  # Add layers after the first one

            # Attempt to write the layer
            try:
                self.show_success_message(f"Processing layer: {layer.name()}")  # Log the layer being processed
                error = QgsVectorFileWriter.writeAsVectorFormatV3(
                    layer,
                    gpkg_path,
                    transform_context,
                    options
                )

                # Check for errors
                if error[0] != QgsVectorFileWriter.NoError:  # Check if the first element of error is not 0
                    self.show_error_message(f"Failed to save layer {layer.name()}: Error code {error}")
                    overall_success = False  # Set the flag to False on error
                else:
                    self.show_success_message(f"Successfully saved layer: {options.layerName}")  # Log successful save

            except Exception as e:
                self.show_error_message(f"Failed to save layer {layer.name()}: {str(e)}")
                overall_success = False  # Set the flag to False on exception

        # Final success message
        if overall_success:
            self.show_success_message(f"GeoPackage saved at: {gpkg_path}")

            # Load the GeoPackage into QGIS
            self.add_layers_from_geopackage(gpkg_path, group)
        else:
            self.show_error_message(f"Some layers were not saved successfully. Check the logs.")

        return overall_success


    def add_layers_from_geopackage(self, gpkg_path, group):
        """
        Automatically add all layers from the GeoPackage to the QGIS project.
        """
        # Open the GeoPackage using OGR
        conn = ogr.Open(gpkg_path)
        if conn is None:
            self.show_error_message("Failed to open GeoPackage.")
            return

        layer_count = conn.GetLayerCount()
        # Iterate over all layers in the GeoPackage
        for i in range(layer_count - 1, -1, -1):
            layer = conn.GetLayerByIndex(i)
            layer_name = layer.GetName()
            
            # Construct the layer URI for QGIS
            layer_uri = f"{gpkg_path}|layername={layer_name}"

            # Add the layer to the QGIS project
            new_layer = iface.addVectorLayer(layer_uri, layer_name, "ogr")
            
            if new_layer is not None and new_layer.isValid():
                # Now add the valid layer to the specified group
                # group.addLayer(new_layer)
                self.show_success_message(f"Successfully added layer: {layer_name}")
            else:
                self.show_error_message(f"Failed to add layer: {layer_name}")


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

