from PyQt5 import QtWidgets, uic
from PyQt5.QtCore import QSettings
import os
from datetime import datetime
import shutil
from .. s2g_logging import Survey2GISLogger

FORM_CLASS, _ = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), '..', "s2g_data_processor_dockwidget_base.ui")
)

class DataNormalizer:
    def __init__(self):
        self.parent_widget = None
        self.logger = None
        # Change settings to be more explicit with organization and application name
        self.settings = QSettings('CSGIS', 'Survey2GIS_DataProcessor')
        
        self.saveable_fields = {
            'input_select': ('s2g_normalize/input_select', ''),
            'output_select_input': ('s2g_normalize/output_select_input', ''),
            'output_filename_input': ('s2g_normalize/output_filename_input', ''),
            'styles_folder_path_input': ('s2g_normalize/styles_folder_path_input', ''),
            'cols_after_ids_input': ('s2g_normalize/cols_after_ids_input', ''),
            'copy_styles_checkbox': ('s2g_normalize/copy_styles_checkbox', False),
            'standard_geotags_checkbox': ('s2g_normalize/standard_geotags_checkbox', False),
            'fix_lines_checkbox': ('s2g_normalize/fix_lines_checkbox', False),
            'cols_after_id_checkbox': ('s2g_normalize/cols_after_id_checkbox', False),
            'search_character': ('s2g_normalize/search_character', ''),
            'replace_character': ('s2g_normalize/replace_character', ''),
            'epsg_input': ('s2g_normalize/epsg_input', ''),
        }

    def setup(self, parent_widget):
        """Initialize the normalizer with parent widget."""
        self.parent_widget = parent_widget
        self.logger = Survey2GISLogger(parent_widget)
        
        # Connect signals first
        self.connect_signals()
        
        # Add settings checkbox to GUI
        self.add_settings_persistence_checkbox()
        
        # Load settings after GUI is fully set up
        QtWidgets.QApplication.processEvents()  # Let the GUI finish updating
        self.load_settings()

    def add_settings_persistence_checkbox(self):
        """Add checkbox for settings persistence to the GUI."""
        try:
            # Create checkbox for settings persistence
            self.settings_persist_checkbox = QtWidgets.QCheckBox("Save settings for next session")
            self.settings_persist_checkbox.setChecked(self.settings.value('s2g_normalize/persist_settings', False, type=bool))
            
            # Find the normalize tab's layout
            normalize_tab = self.parent_widget.tabWidget.widget(0) 
            if hasattr(normalize_tab, 'layout'):
                layout = normalize_tab.layout()
                if layout:
                    # Add checkbox to the bottom of the layout
                    layout.addWidget(self.settings_persist_checkbox)
                    
                    # Connect checkbox state change
                    self.settings_persist_checkbox.stateChanged.connect(self.on_settings_persistence_changed)
            
        except Exception as e:
            self.logger.log_message(f"Error adding settings persistence checkbox: {e}", 
                                  level="error", to_tab=True, to_gui=True, to_notification=False)

    def on_settings_persistence_changed(self, state):
        """Handle changes to the settings persistence checkbox."""
        self.settings.setValue('s2g_normalize/persist_settings', bool(state))
        if state:
            # If enabled, immediately save current values
            self.save_settings()
        else:
            # If unchecked, clear all saved settings
            self.clear_settings()
        
        # Force settings to be written to disk
        self.settings.sync()

    def save_settings(self):
        """Save current widget values to settings if persistence is enabled."""
        if not hasattr(self, 'settings_persist_checkbox') or not self.settings_persist_checkbox.isChecked():
            return

        try:
            # Begin a settings group to keep all settings together
            self.settings.beginGroup('s2g_normalize')
            
            # Save persistence setting
            self.settings.setValue('persist_settings', True)
            
            # Save all values in a single transaction
            for widget_name, (setting_key, _) in self.saveable_fields.items():
                widget = getattr(self.parent_widget, widget_name)
                
                if isinstance(widget, QtWidgets.QLineEdit):
                    value = widget.text()
                    # Save with explicit type hint
                    self.settings.setValue(setting_key.replace('s2g_normalize/', ''), str(value))
                    self.logger.log_message(f"Saved {setting_key}: '{value}'", 
                                        level="info", to_tab=True, to_gui=False, to_notification=False)
                
                elif isinstance(widget, QtWidgets.QCheckBox):
                    value = widget.isChecked()
                    # Save with explicit type hint
                    self.settings.setValue(setting_key.replace('s2g_normalize/', ''), bool(value))
                    self.logger.log_message(f"Saved {setting_key}: {value}", 
                                        level="info", to_tab=True, to_gui=False, to_notification=False)
            
            # End the settings group
            self.settings.endGroup()
            
            # Force write to disk
            self.settings.sync()

        except Exception as e:
            self.logger.log_message(f"Error saving settings: {str(e)}", 
                                level="error", to_tab=True, to_gui=True, to_notification=False)

    def load_settings(self):
        """Load saved settings if persistence is enabled."""
        try:
            # Begin reading from the settings group
            self.settings.beginGroup('s2g_normalize')
            
            # Check if persistence is enabled
            persist_enabled = self.settings.value('persist_settings', False, type=bool)
            
            if not persist_enabled:
                self.settings.endGroup()
                return
                
            # Debug current settings state
            self.logger.log_message("Current settings values:", 
                                level="info", to_tab=True, to_gui=True, to_notification=False)
            
            for key in self.settings.childKeys():
                value = self.settings.value(key)
                self.logger.log_message(f"Found setting: {key} = {value}", 
                                    level="info", to_tab=True, to_gui=True, to_notification=False)
            
            # Load all values
            for widget_name, (setting_key, default_value) in self.saveable_fields.items():
                try:
                    widget = getattr(self.parent_widget, widget_name)
                    key = setting_key.replace('s2g_normalize/', '')
                    
                    if isinstance(widget, QtWidgets.QLineEdit):
                        value = self.settings.value(key, default_value, type=str)
                        if value is not None:
                            widget.setText(value)
                            self.logger.log_message(f"Loaded QLineEdit {widget_name}: '{value}'", 
                                                level="info", to_tab=True, to_gui=True, to_notification=False)
                    
                    elif isinstance(widget, QtWidgets.QCheckBox):
                        value = self.settings.value(key, default_value, type=bool)
                        widget.setChecked(value)
                        self.logger.log_message(f"Loaded QCheckBox {widget_name}: {value}", 
                                            level="info", to_tab=True, to_gui=True, to_notification=False)
                    
                except Exception as widget_error:
                    self.logger.log_message(f"Error loading widget {widget_name}: {str(widget_error)}", 
                                        level="error", to_tab=True, to_gui=True, to_notification=False)
            
            # End reading from the settings group
            self.settings.endGroup()

        except Exception as e:
            self.logger.log_message(f"Error loading settings: {str(e)}", 
                                level="error", to_tab=True, to_gui=True, to_notification=True)
            self.settings.endGroup()


    def clear_settings(self):
        """Clear all saved settings."""
        try:
            self.settings.beginGroup('normalize')
            self.settings.remove('')  # Remove all settings in the group
            self.settings.endGroup()
            self.settings.sync()
            self.logger.log_message("Settings cleared successfully", 
                                level="info", to_tab=True, to_gui=False, to_notification=False)
        except Exception as e:
            self.logger.log_message(f"Error clearing settings: {str(e)}", 
                                level="error", to_tab=True, to_gui=True, to_notification=False)

    def connect_signals(self):
        """Connect all GUI signals and add autosave functionality."""
        if not self.parent_widget:
            return

        # Connect existing signals
        self.parent_widget.input_select_button.clicked.connect(self.select_input_files)
        self.parent_widget.input_data_reset_button.clicked.connect(
            lambda: self.reset_text_field(self.parent_widget.input_select)
        )
        self.parent_widget.output_select_button.clicked.connect(self.select_output_directory)
        self.parent_widget.output_reset_button.clicked.connect(
            lambda: self.reset_text_field(self.parent_widget.output_select_input)
        )
        self.parent_widget.output_filename_input.textChanged.connect(self.validate_filename_input)
        self.parent_widget.styles_input_select_button.clicked.connect(self.select_styles_input_directory)
        self.parent_widget.styles_reset_button.clicked.connect(
            lambda: self.reset_text_field(self.parent_widget.styles_folder_path_input)
        )
        self.parent_widget.run_button.clicked.connect(self.run_normalize)

        # Connect autosave for all saveable widgets
        for widget_name in self.saveable_fields:
            widget = getattr(self.parent_widget, widget_name)
            if isinstance(widget, QtWidgets.QLineEdit):
                widget.textChanged.connect(self.save_settings)
            elif isinstance(widget, QtWidgets.QCheckBox):
                widget.stateChanged.connect(self.save_settings)

    def select_input_files(self):
            """Open file dialog to select multiple input files and display in input_select field."""
            files, _ = QtWidgets.QFileDialog.getOpenFileNames(
                self.parent_widget, "Select Input File(s)", "", "Data Files (*.dat *.txt);;All Files (*)"
            )
            if files:
                files_list = "; ".join(files)
                self.parent_widget.input_select.setText(files_list)

    def select_output_directory(self):
        """Open file dialog to select an output directory."""
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self.parent_widget, "Select Output Directory", ""
        )
        if directory:
            self.parent_widget.output_select_input.setText(directory)
            self.parent_widget.command_options.output_directory = directory

    def select_styles_input_directory(self):
        """Open file dialog to select a styles directory."""
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self.parent_widget, "Select Styles Directory", ""
        )
        if directory:
            self.parent_widget.styles_folder_path_input.setText(directory)
            self.parent_widget.command_options.styles_folder_path_input = directory

    def reset_text_field(self, field):
        """Reset the text in a given field."""
        field.setText("")

    def validate_filename_input(self):
        """Validate filename input when it changes."""
        original_text = self.parent_widget.output_filename_input.text()
        filename_text = original_text.strip()
        invalid_chars = '<>:"/\\|?*\u00e4\u00f6\u00fc\u00df'  # German umlauts
        
        if filename_text:
            # Check for any kind of spaces or invalid characters
            if (any(char in filename_text for char in invalid_chars) or 
                '.' in filename_text or 
                ' ' in original_text):  # Check for ANY spaces in original input
                self.parent_widget.output_filename_input.setStyleSheet("background-color: #ffe6e6;")
                return False
            else:
                self.parent_widget.output_filename_input.setStyleSheet("background-color: #e6ffe6;")
                return True
        else:
            self.parent_widget.output_filename_input.setStyleSheet("")
            return False

    def validate_epsg_input(self):
        """Validate EPSG input when it changes."""
        epsg_text = self.parent_widget.epsg_input.text().strip()
        if epsg_text:
            try:
                epsg_code = int(epsg_text)
                if self.VALID_EPSG_RANGE[0] <= epsg_code <= self.VALID_EPSG_RANGE[1]:
                    self.parent_widget.epsg_input.setStyleSheet("background-color: #e6ffe6;")
                    return True
                else:
                    self.parent_widget.epsg_input.setStyleSheet("background-color: #ffe6e6;")
            except ValueError:
                self.parent_widget.epsg_input.setStyleSheet("background-color: #ffe6e6;")
        else:
            self.parent_widget.epsg_input.setStyleSheet("")
        return False

    def get_concat_filename(self):
        """Generate concatenated filename based on custom input or default pattern."""
        custom_filename = self.parent_widget.output_filename_input.text().strip()
        
        if custom_filename and self.validate_filename_input():
            return f"{custom_filename}.txt"
        
        return f"s2g_merged_input_files.txt"


    def run_normalize(self):
        if (not self.parent_widget.input_select.text().strip() or
            not self.parent_widget.output_select_input.text().strip()):
            self.logger.log_message("Please fill all required fields in Tab 'Normalize'", 
                                  level="error", to_tab=True, to_gui=True, to_notification=True)
            return

        try:
            output_directory = self.parent_widget.output_select_input.text().strip()
            # Get filename with potential EPSG code
            output_filename = self.get_concat_filename()
            output_file_path = os.path.join(output_directory, output_filename)

            self._concatenate_files(output_file_path)
            self._clean_file_content(output_file_path)

            if self.parent_widget.copy_styles_checkbox.isChecked():
                self._copy_qml_files()
            
            if self.parent_widget.standard_geotags_checkbox.isChecked():
                self._replace_geotag_symbols(output_file_path)
            
            if self.parent_widget.fix_lines_checkbox.isChecked():
                self._fix_line_numbering(output_file_path)

            if (self.parent_widget.cols_after_id_checkbox.isChecked() and 
                self.parent_widget.cols_after_ids_input.text().strip()):
                self._add_columns_after_line_number(output_file_path)

            # update the process text field
            self.parent_widget.process_input_file_input.setText(output_file_path)
            self.logger.log_message("Files successfully processed!", 
                                  level="info", to_tab=True, to_gui=True, to_notification=True)

        except Exception as e:
            self.logger.log_message(f"Error during file processing: {e}", 
                                  level="error", to_tab=True, to_gui=True, to_notification=True)

    # Keep all your existing helper methods (_concatenate_files, _clean_file_content, etc.)
    def _concatenate_files(self, output_file_path):
        """Concatenate selected .txt or .dat files alphabetically and save the result."""
        input_files = self.parent_widget.input_select.text().split("; ")
        input_files = sorted([os.path.normpath(file) for file in input_files if file.endswith(('.txt', '.dat'))])
        
        if not input_files:
            self.logger.log_message("No valid .txt or .dat files selected", 
                                  level="error", to_tab=True, to_gui=True, to_notification=True)
            raise FileNotFoundError("No valid .txt or .dat files selected")

        with open(output_file_path, 'w', encoding='utf-8') as output_file:
            for input_file in input_files:
                with open(input_file, 'r', encoding='utf-8') as f:
                    content = f.readlines()
                    content = [line.strip() for line in content if line.strip()]
                    if os.path.getsize(output_file_path) > 0:
                        with open(output_file_path, 'rb+') as check_file:
                            check_file.seek(-1, os.SEEK_END)
                            last_char = check_file.read(1).decode()
                        if last_char != "\n":
                            output_file.write("\n")
                    output_file.write("\n".join(content))
                    if content:
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
    def _replace_geotag_symbols(self, output_file_path):
            """
            Replace characters in the specified output file based on search and replace inputs.
            - If replace is empty: deletes the search string
            - If no spaces: replaces entire search string with replace string
            - If spaces present: replaces character by character where matches exist
            """
            try:
                if not self.parent_widget.standard_geotags_checkbox.isChecked():
                    return

                search_char = self.parent_widget.search_character.text().strip()
                if not search_char:  # No search character provided, do nothing
                    return

                replace_char = self.parent_widget.replace_character.text().strip()
                
                # Read the contents of the file
                with open(output_file_path, 'r', encoding='utf-8') as file:
                    content = file.read()

                updated_content = content
                
                # Case 1: Replace is empty -> delete search string
                if not replace_char:
                    updated_content = content.replace(search_char, '')
                    
                # Case 2: No spaces -> direct string replacement
                elif ' ' not in search_char and ' ' not in replace_char:
                    updated_content = content.replace(search_char, replace_char)
                    
                # Case 3: Spaces present -> character by character replacement
                else:
                    search_chars = search_char.split()
                    replace_chars = replace_char.split()
                    
                    for i, char in enumerate(search_chars):
                        if char and i < len(replace_chars):
                            updated_content = updated_content.replace(char, replace_chars[i])

                # Write the updated content back to the file
                with open(output_file_path, 'w', encoding='utf-8') as file:
                    file.write(updated_content)

                self.logger.log_message(
                    f"Character replacement completed in {output_file_path}", 
                    level="info", to_tab=True, to_gui=True, to_notification=False
                )

            except Exception as e:
                self.logger.log_message(
                    f"Error updating characters: {e}", 
                    level="error", to_tab=True, to_gui=True, to_notification=True)

    def _fix_line_numbering(self, output_file_path):
        """Fix line numbering in the specified file."""
        try:
            # Read the content of the file
            with open(output_file_path, 'r', encoding='utf-8') as file:
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
            with open(output_file_path, 'w', encoding='utf-8') as file:
                file.write("\n".join(fixed_lines) + "\n")

            self.logger.log_message(f"Line numbering fixed in {output_file_path}", 
                                level="info", to_tab=True, to_gui=True, to_notification=False)

        except Exception as e:
            self.logger.log_message(f"Error fixing line numbering in {output_file_path}: {e}", 
                                level="error", to_tab=True, to_gui=True, to_notification=True)

    def _add_columns_after_line_number(self, output_file_path):
        """Add columns after line number in the specified file."""
        try:
            # Get the raw input string
            raw_input = self.parent_widget.cols_after_ids_input.text().rstrip('\n')
            # Check if input ends with space before we clean it
            should_add_space = raw_input.endswith(' ')
            # Remove any trailing spaces for clean processing
            input_string = raw_input.rstrip()
            
            # Read the content of the file
            with open(output_file_path, 'r', encoding='utf-8') as file:
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
            with open(output_file_path, 'w', encoding='utf-8') as file:
                file.write("\n".join(updated_lines) + "\n")  # Ensure a newline at the end

            self.logger.log_message(f"Columns added to file: {output_file_path}", 
                                level="info", to_tab=True, to_gui=True, to_notification=False)

        except Exception as e:
            self.logger.log_message(f"Error adding columns to file {output_file_path}: {e}", 
                                level="error", to_tab=True, to_gui=True, to_notification=True)
            
            
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
