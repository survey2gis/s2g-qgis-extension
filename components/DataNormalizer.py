
import os

from PyQt5 import QtWidgets, uic
import shutil
from .. s2g_logging_new import Survey2GISLogger

FORM_CLASS, _ = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), '..', "s2g_data_processor_dockwidget_base.ui")
)


class DataNormalizer:
    def __init__(self, parent_widget):
        """Initialize with a reference to the main widget and set up input handling."""
        self.parent_widget = parent_widget
        self.connect_signals()
        self.logger = Survey2GISLogger(parent_widget)

    def connect_signals(self):
        """Connect GUI elements to their respective methods."""

        # Input
        self.parent_widget.input_select_button.clicked.connect(self.select_input_files)
        self.parent_widget.input_data_reset_button.clicked.connect(
            lambda: self.reset_text_field(self.parent_widget.input_select)
        )

        # output
        self.parent_widget.output_select_button.clicked.connect(self.select_output_directory)
        self.parent_widget.output_reset_button.clicked.connect(
            lambda: self.reset_text_field(self.parent_widget.output_select_input)
        )

        # Tasks: copy styles
        self.parent_widget.styles_input_select_button.clicked.connect(self.select_styles_input_directory)
        self.parent_widget.styles_reset_button.clicked.connect(
            lambda: self.reset_text_field(self.parent_widget.styles_folder_path_input)
        )

        # Run tasks
        self.parent_widget.run_button.clicked.connect(self.run_normalize)

    # GUI Methods

    def reset_text_field(self, field):
        field.setText("")

    def select_input_files(self):
        """Open file dialog to select multiple input files and display in input_select field."""
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self.parent_widget, "Select Input File(s)", "", "Data Files (*.dat *.txt);;All Files (*)"
        )
        if files:
            files_list = "; ".join(files)
            self.parent_widget.input_select.setText(files_list)
            # self.logger.log_message(files_list, level="info", to_tab=True, to_gui=True, to_notification=True)

    def select_output_directory(self):
        """Open file dialog to select an output directory."""
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self.parent_widget, "Select Output Directory", ""
        )
        if directory:
            self.parent_widget.output_select_input.setText(directory)
            self.parent_widget.command_options.output_directory = directory  # Todo: why do we need this?

    def select_styles_input_directory(self):
        """Open file dialog to select an output directory."""
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self.parent_widget, "Select Output Directory", ""
        )
        if directory:
            self.parent_widget.styles_folder_path_input.setText(directory) 
            self.parent_widget.command_options.styles_folder_path_input = directory  # Todo: why do we need this?

    # Tasks

    def run_normalize(self):
        if (not self.parent_widget.input_select.text().strip() or
            not self.parent_widget.output_select_input.text().strip()):
            self.logger.log_message("Please fill all required fields in Tab 'Normalize'", level="error", to_tab=True, to_gui=True, to_notification=True)
            return

        try:
            self._concatenate_files()
            output_directory = self.parent_widget.output_select_input.text().strip()
            output_file_path = os.path.join(output_directory, self.parent_widget.CONCAT_OUTPUT_NAME) # Todo: should CONCAT_OUTPUT_NAME be moved to this class?

            # Clean the concatenated output file
            self._clean_file_content(output_file_path)

            if self.parent_widget.copy_styles_checkbox.isChecked():
                self._copy_qml_files()
            
            if self.parent_widget.standard_geotags_checkbox.isChecked():
                self._replace_geotag_symbols()  # Call the function to replace & with $
            
            if self.parent_widget.fix_lines_checkbox.isChecked():
                self._fix_line_numbering()  # Call the function to fix line numbering

            # Add columns after line numbering (if checkbox checked and input filled)
            if self.parent_widget.cols_after_id_checkbox.isChecked() and self.parent_widget.cols_after_ids_input.text().strip():
                self._add_columns_after_line_number(output_file_path)
            else:
                self.logger.log_message("Checkbox unchecked or input string is empty, skipping column addition.", level="info", to_tab=True, to_gui=False, to_notification=False)


            # update the process text field
            self.parent_widget.process_input_file_input.setText(output_file_path)
            self.logger.log_message("Files successfully processed!", level="info", to_tab=True, to_gui=True, to_notification=True)

        except Exception as e:
            self.logger.log_message(f"Error during file processing: {e}", level="error", to_tab=True, to_gui=True, to_notification=True)

    def _concatenate_files(self):
        """Concatenate selected .txt or .dat files alphabetically and save the result."""
        input_files = self.parent_widget.input_select.text().split("; ")
        input_files = sorted([os.path.normpath(file) for file in input_files if file.endswith(('.txt', '.dat'))])
        
        if not input_files:
            self.logger.log_message("No valid .txt or .dat files selected", level="error", to_tab=True, to_gui=True, to_notification=True)
            raise FileNotFoundError("No valid .txt or .dat files selected")

        # Output file path based on the selected output directory and base name
        output_directory = self.parent_widget.output_select_input.text().strip()
        output_file_path = os.path.join(output_directory, self.parent_widget.CONCAT_OUTPUT_NAME)

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

    def _clean_file_content(self, file_path):
        """
        Cleans the content of a file by:
        - Removing empty lines.
        - Converting multiple spaces or tabs to a single space.
        """
        try:
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
                file.write("\n".join(cleaned_lines) + "\n")

            self.logger.log_message(f"Cleaned file content in {file_path}", level="info", to_tab=True, to_gui=True, to_notification=False)

        except Exception as e:
            self.logger.log_message(f"Error cleaning file content: {e}", level="error", to_tab=True, to_gui=True, to_notification=True)

    def _copy_qml_files(self):
        """Copy QML style files and SVG folder from the selected styles folder to the output directory."""
        
        styles_folder_path = self.parent_widget.styles_folder_path_input.text().strip()
        if not styles_folder_path or not os.path.isdir(styles_folder_path):
            self.logger.log_message(f"Styles folder does not exist: {styles_folder_path}", level="error", to_tab=True, to_gui=True, to_notification=True)
            return

        # Get the output folder path and create necessary subfolders
        output_folder_path = self.parent_widget.output_select_input.text().strip()
        qml_output_folder = os.path.join(output_folder_path, "qml")
        svg_output_folder = os.path.join(output_folder_path, "qml", "svg")

        # Create QML folder
        try:
            os.makedirs(qml_output_folder, exist_ok=True) 
        except Exception as e:
            self.logger.log_message(f"Error creating QML folder: {e}", level="error", to_tab=True, to_gui=True, to_notification=True)
            return

        # Copy QML files
        qml_files = [f for f in os.listdir(styles_folder_path) if f.endswith(".qml")]
        if not qml_files:
            self.logger.log_message("No QML files found in the styles folder.", level="warning", to_tab=True, to_gui=True, to_notification=True)
        else:
            try:
                for qml_file in qml_files:
                    source = os.path.join(styles_folder_path, qml_file)
                    destination = os.path.join(qml_output_folder, qml_file)
                    shutil.copy(source, destination)
                self.logger.log_message(f"Successfully copied {len(qml_files)} QML file(s) to {qml_output_folder}", 
                                    level="info", to_tab=True, to_gui=True, to_notification=False)
            except Exception as e:
                self.logger.log_message(f"Error copying QML files: {e}", level="error", to_tab=True, to_gui=True, to_notification=True)

        # Check for and copy SVG folder
        svg_source_folder = os.path.join(styles_folder_path, "svg")
        if os.path.exists(svg_source_folder) and os.path.isdir(svg_source_folder):
            try:
                # Copy the entire SVG folder
                if os.path.exists(svg_output_folder):
                    shutil.rmtree(svg_output_folder)  # Remove existing folder if it exists
                shutil.copytree(svg_source_folder, svg_output_folder)
                
                # Count SVG files for logging
                svg_files = sum(1 for f in os.listdir(svg_output_folder) if f.endswith(".svg"))
                self.logger.log_message(f"Successfully copied SVG folder with {svg_files} SVG file(s) to {svg_output_folder}", 
                                    level="info", to_tab=True, to_gui=True, to_notification=False)
            except Exception as e:
                self.logger.log_message(f"Error copying SVG folder: {e}", level="error", to_tab=True, to_gui=True, to_notification=True)
        else:
            self.logger.log_message("No SVG folder found in the styles folder.", 
                                level="info", to_tab=True, to_gui=True, to_notification=False)
    def _replace_geotag_symbols(self):
        """Replace & with $ in concatenated_output.txt if the standard_geotags_checkbox is checked."""

        # Get the path of the concatenated output file
        output_directory = self.parent_widget.output_select_input.text().strip()
        concatenated_output_file = os.path.join(output_directory, self.parent_widget.CONCAT_OUTPUT_NAME)

        if not os.path.isfile(concatenated_output_file):
            self.logger.log_message(f"Output file not found: {concatenated_output_file}", level="error", to_tab=True, to_gui=True, to_notification=True)
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


            self.logger.log_message(f"Geotag symbols replaced in {concatenated_output_file}", level="info", to_tab=True, to_gui=True, to_notification=False)


        except Exception as e:
            self.logger.log_message("Error updating geotag symbols: {e}", level="error", to_tab=True, to_gui=True, to_notification=False)

    def _fix_line_numbering(self):
        """Fix line numbering in the concatenated_output.txt file if fix_lines_checkbox is checked."""

        # Get the path of the concatenated output file
        output_directory = self.parent_widget.output_select_input.text().strip()
        concatenated_output_file = os.path.join(output_directory, self.parent_widget.CONCAT_OUTPUT_NAME)

        if not os.path.isfile(concatenated_output_file):
            self.logger.log_message(f"Output file not found: {concatenated_output_file}", level="error", to_tab=True, to_gui=True, to_notification=False)
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

            self.logger.log_message(f"Line numbering fixed in {concatenated_output_file}", level="info", to_tab=True, to_gui=True, to_notification=False)

        except Exception as e:
            self.logger.log_message(f"Error fixing line numbering in {concatenated_output_file}: {e}", level="error", to_tab=True, to_gui=True, to_notification=True)


    def _add_columns_after_line_number(self, file_path):
        """
        Adds the split string (from the user input) directly after the line numbering in each line of the file.
        A space will be added before the rest of the line only if the input originally ended with exactly one space.
        """
        try:
            # Get the raw input string
            raw_input = self.parent_widget.cols_after_ids_input.text().rstrip('\n')
            # Check if input ends with space before we clean it
            should_add_space = raw_input.endswith(' ')
            # Remove any trailing spaces for clean processing
            input_string = raw_input.rstrip()
            
            # Read the content of the file
            with open(file_path, 'r', encoding='utf-8') as file:
                lines = file.readlines()

            updated_lines = []
            for line in lines:
                # Split the line into components
                parts = line.strip().split()

                if parts and parts[0].isdigit():  # Ensure the line starts with a number
                    remaining_parts = ' '.join(parts[1:])
                    updated_line = f"{parts[0]} {input_string}{' ' if should_add_space else ''}{remaining_parts}"
                    updated_lines.append(updated_line)
                else:
                    # In case the line doesn't start with a number, leave it unchanged
                    updated_lines.append(line.strip())

            # Write the updated content back to the file
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write("\n".join(updated_lines) + "\n")  # Ensure a newline at the end

            self.logger.log_message(f"Columns added to file: {file_path}", level="info", to_tab=True, to_gui=True, to_notification=False)

        except Exception as e:
            self.logger.log_message(f"Error adding columns to file {file_path}: {e}", level="error", to_tab=True, to_gui=True, to_notification=True)

    # def _add_columns_after_line_number(self, file_path):
    #     """
    #     Adds the split string (from the user input) after the line numbering in each line of the file.
    #     The input can contain an arbitrary number of parts separated by '-'.
    #     """
    # # Check if the checkbox is checked and input is not empty
    #     try:
    #         # Get the input string and split it by '-'
    #         input_string = self.parent_widget.cols_after_ids_input.text().strip().replace(' ', '')
    #         split_string = input_string.split('-')

    #         # Read the content of the file
    #         with open(file_path, 'r', encoding='utf-8') as file:
    #             lines = file.readlines()

    #         updated_lines = []
    #         for line in lines:
    #             # Split the line into components
    #             parts = line.strip().split()

    #             if parts and parts[0].isdigit():  # Ensure the line starts with a number
    #                 # Prepare the new line with all split parts
    #                 updated_line = f"{parts[0]} {' '.join(split_string)} {' '.join(parts[1:])}"
    #                 updated_lines.append(updated_line)
    #             else:
    #                 # In case the line doesn't start with a number, leave it unchanged
    #                 updated_lines.append(line.strip())

    #         # Write the updated content back to the file
    #         with open(file_path, 'w', encoding='utf-8') as file:
    #             file.write("\n".join(updated_lines) + "\n")  # Ensure a newline at the end
    #         self.logger.log_message(f"Columns added to file: {file_path}", level="info", to_tab=True, to_gui=True, to_notification=False)

    #     except Exception as e:
    #         self.logger.log_message(f"Error adding columns to file {file_path}: {e}", level="error", to_tab=True, to_gui=True, to_notification=True)
