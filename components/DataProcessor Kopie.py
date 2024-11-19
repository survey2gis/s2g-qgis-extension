import os
from PyQt5 import QtWidgets, uic, QtCore
from qgis.core import QgsProject, QgsVectorLayer, QgsApplication
from qgis.core import QgsProject
from osgeo import ogr, osr

from .. s2g_logging_new import Survey2GISLogger
import os
from qgis.core import QgsProject
import json
import re
import fnmatch
import configparser

FORM_CLASS, _ = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), '..', "s2g_data_processor_dockwidget_base.ui")
)



class DataProcessor:
    def __init__(self, parent_widget):
        """Access main widget for shared variables and settings."""
        self.parent_widget = parent_widget
        self.logger = Survey2GISLogger(parent_widget)

        self.command_history_file = os.path.join(os.path.dirname(__file__), "..", "command_history.txt")
        self.current_commands = []
        self.current_command_index = 0

        self.mapping_filename = os.path.join(os.path.dirname(__file__), "..", "alias.txt")
        self.alias_mapping = self.load_alias_mapping(self.mapping_filename )

        # Define field mapping for options
        self.option_fields = {
            'parser_path': self.parent_widget.select_parser_input,
            'output_base_name': self.parent_widget.name_generated_file_input,
            'output_directory': self.parent_widget.shape_output_path_input
        }
        
        # Define additional options and flags if needed
        self.additional_options_fields = {
            '--topology': self.parent_widget.topology_select,
            '--label-mode-poly': self.parent_widget.label_mode_poly_select,
            '--label': self.parent_widget.label_input,
            '--selection': self.parent_widget.selection_input,
            '--z-offset': self.parent_widget.z_offset_input,
            '--tolerance': self.parent_widget.tolerance_input,
            '--decimal-places': self.parent_widget.decimal_places_input,
            '--snapping': self.parent_widget.snapping_input,
            '--decimal-point': self.parent_widget.decimal_point_input,
            '--decimal-group': self.parent_widget.decimal_group_input,
            '--dangling': self.parent_widget.dangling_input,
            '--x-offset': self.parent_widget.x_offset_input,
            '--y-offset': self.parent_widget.y_offset_input,
            '--proj-in': self.parent_widget.proj_in_input,
            '--proj-out': self.parent_widget.proj_out_input
        }

        self.flag_options_fields = {
            '-c': self.parent_widget.strict_checkbox,
            '-e': self.parent_widget.english_checkbox,
            '-v': self.parent_widget.validate_checkbox,
            '-2': self.parent_widget.force_2d_checkbox,
        }

        self.connect_signals()
        self.load_command_history()

    def connect_signals(self):
        """Connect GUI elements to their respective methods."""

        # Data Input
        self.parent_widget.select_parsed_inputfile_button.clicked.connect(self.select_data_input_file)
        self.parent_widget.reset_parsed_inputfile_button.clicked.connect(
            lambda: self.reset_text_field(self.parent_widget.process_input_file_input)
        )

        # Parser Input
        self.parent_widget.select_parser_input_button.clicked.connect(self.select_parser_file)
        self.parent_widget.reset_parser_input_button.clicked.connect(
            lambda: self.reset_text_field(self.parent_widget.select_parser_input)
        )
        
        # Select Output directory
        self.parent_widget.select_shapeoutput_button.clicked.connect(self.select_output_directory)
        self.parent_widget.reset_shapeoutput_button.clicked.connect(
            lambda: self.reset_text_field(self.parent_widget.shape_output_path_input)
        )

        # alias Input
        self.parent_widget.alias_file_select_button.clicked.connect(self.select_alias_file)
        self.parent_widget.alias_file_reset_button.clicked.connect(
            lambda: self.reset_text_field(self.parent_widget.alias_file_input)
        )

        self.parent_widget.add_command_button.clicked.connect(self.add_command)
        self.parent_widget.save_commands_button.clicked.connect(self.save_command_history)
        self.parent_widget.run_commands_button.clicked.connect(self.run_commands)

    # => GUI Methods

    def reset_text_field(self, field):
        field.setText("")

    def select_data_input_file(self):
        """Open file dialog to select one parser file."""
        file, _ = QtWidgets.QFileDialog.getOpenFileName(
            self.parent_widget, "Select Parser File", "", "All Files (*)"
        )
        if file:
            self.parent_widget.process_input_file_input.setText(file)

    def select_parser_file(self):
        """Open file dialog to select one parser file."""
        file, _ = QtWidgets.QFileDialog.getOpenFileName(
            self.parent_widget, "Select Parser File", "", "All Files (*)"
        )
        if file:
            self.parent_widget.select_parser_input.setText(file)

    def select_alias_file(self):
        """Open file dialog to select one alias file."""
        file, _ = QtWidgets.QFileDialog.getOpenFileName(
            self.parent_widget, "Select alias File", "", "Data Files (*.dat *.txt);;All Files (*)"
        )
        if file:
            self.parent_widget.alias_file_input.setText(file)
            self.alias_mapping = self.load_alias_mapping(str(file))
            self.logger.log_message(f"Changed alias file to {file}", level="info", to_tab=False, to_gui=True, to_notification=False)


    def select_output_directory(self):
        """Open file dialog to select an output directory."""
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self.parent_widget, "Select Output Directory", ""
        )
        if directory:
            self.parent_widget.shape_output_path_input.setText(directory) 
            self.parent_widget.command_options.output_directory = directory 

    # => Command generation methods

    def add_command(self):
        """Process the files using the survey2gis command line tool."""
        try:
            # Check if any of the required fields are empty
            if (not self.parent_widget.process_input_file_input.text().strip() or
                not self.parent_widget.select_parser_input.text().strip() or
                not self.parent_widget.name_generated_file_input.text().strip()):
                self.logger.log_message("Please fill all required fields in Tab 'Process'", level="error", to_tab=False, to_gui=False, to_notification=True)
                return

            self.output_base_name = self.parent_widget.name_generated_file_input.text().strip()
            self.command_options = self.read_options()
            command = self.build_command(self.parent_widget.process_input_file_input.text().strip())
            joined_command = " ".join(command)

            self.logger.log_message(joined_command, level="info", to_tab=False, to_gui=True, to_notification=False)
            self.parent_widget.command_code_field.append(joined_command)
            
            # Add this line to save the command history after appending the new command
            self.save_command_history()

        except FileNotFoundError as e:
            self.logger.log_message(f"File not found: {e}", level="error", to_tab=True, to_gui=True, to_notification=True)

    def read_options(self):
        """Read options from UI fields and update command_options."""
        # Read main options
        for option, widget in self.option_fields.items():
            value = widget.currentText() if isinstance(widget, QtWidgets.QComboBox) else widget.text()
            setattr(self.parent_widget.command_options, option, value)

        # Read additional options
        for key, widget in self.additional_options_fields.items():
            if key == '--selection':
                # Skip adding selection to additional_options as we'll handle it separately
                value = widget.currentText() if isinstance(widget, QtWidgets.QComboBox) else widget.text()
                self.parent_widget.command_options.selections = self.process_selection_input(value)
                continue
            
            value = widget.currentText() if isinstance(widget, QtWidgets.QComboBox) else widget.text()
            self.parent_widget.command_options.additional_options[key] = value

        # Read flag options
        for flag, widget in self.flag_options_fields.items():
            is_set = widget.isChecked()
            self.parent_widget.command_options.flag_options[flag] = is_set

        self.parent_widget.command_options.parser_path = self.parent_widget.select_parser_input.text()
        return self.parent_widget.command_options

    def build_command(self, generated_input_file):
        """Build the command to execute survey2gis."""
        binary_path = self.parent_widget.get_binary_path()
        command = ['"'+binary_path+'"']
        
        # Add the base command options
        command.extend(self.parent_widget.command_options.to_command_list())
        
        # Add each selection separately with -S format
        if hasattr(self.parent_widget.command_options, 'selections'):
            for selection in self.parent_widget.command_options.selections:
                command.extend(['-S', selection])
        
        # Add input file to the command
        command.append(generated_input_file)

        return command


    def process_selection_input(self, text):
        """Process selection input handling both space-separated items and quoted items."""
        selections = []
        if not text.strip():
            return selections

        # Variable to track if we're inside quotes
        in_quotes = False
        current_item = []
        
        # Process character by character
        for char in text:
            if char == '"':
                in_quotes = not in_quotes
                continue
            elif char.isspace() and not in_quotes:
                if current_item:
                    selections.append('"' + ''.join(current_item) + '"')
                    current_item = []
            else:
                current_item.append(char)
        
        # Don't forget the last item
        if current_item:
            selections.append('"' + ''.join(current_item) + '"')

        return selections

    # => run s2g commands

    def run_commands(self):
        """Get and run all commands from the command code field"""

        try:
            # Get commands from the field and filter out empty lines
            commands = [cmd.strip() for cmd in self.parent_widget.command_code_field.toPlainText().split('\n') if cmd.strip()]
            
            if not commands:
                self.logger.log_message("No commands found to execute", level="info", to_tab=True, to_gui=True, to_notification=True)
                return
                
            self.current_commands = commands
            self.current_command_index = 0
            
            # Clear the output log before starting new command sequence
            self.logger.log_message(f"\n{'='*50}Starting command sequence execution for {len(commands)} command(s)", level="info", to_tab=True, to_gui=True, to_notification=False)

            # Start with the first command
            self.run_next_command()
            
        except Exception as e:
            self.logger.log_message(f"Error preparing commands: {e}", level="error", to_tab=True, to_gui=True, to_notification=True)


    def run_next_command(self):
        """Run the next command in the sequence or finish"""

        if self.current_command_index >= len(self.current_commands):
            self.logger.log_message("All commands survey2gis commands completed successfully", level="success", to_tab=True, to_gui=True, to_notification=True)
            self.load_survey_data()
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
            
            log_output = f"\n{'='*50}"
            log_output += f"Executing command {self.current_command_index + 1}/{len(self.current_commands)}:\n"
            log_output += command
            self.logger.log_message(log_output, level="info", to_tab=True, to_gui=True, to_notification=False)

            # Store current command output for interpretation
            self.current_command_output = []
            self.run_process_sequential(command_parts)
            
        except Exception as e:
            self.logger.log_message(f"Error processing command: {e}", level="error", to_tab=True, to_gui=True, to_notification=True)


    def run_process_sequential(self, command_parts):
        """Run a single process and handle its completion."""
        try:
            self.process = QtCore.QProcess(self.parent_widget)

            # Connect signals
            self.process.readyReadStandardOutput.connect(self.handle_stdout_sequential)
            self.process.readyReadStandardError.connect(self.handle_stderr_sequential)
            self.process.finished.connect(self.handle_process_finished_sequential)

            # Extract the program path and arguments
            program = command_parts[0]
            arguments = command_parts[1:]

            # Start the process
            self.process.start(program, arguments)

            # Wait for process to start
            if not self.process.waitForStarted(3000):  # 3 second timeout
                raise Exception("Process failed to start within timeout period")

        except Exception as e:
            self.logger.log_message(f"Failed to start process: {e}", level="error", to_tab=True, to_gui=True, to_notification=False)


    def handle_stdout_sequential(self):
        """Handle standard output from the current process."""
        data = self.process.readAllStandardOutput().data().decode()
        self.current_command_output.append(data)
        self.logger.log_message(f"{data}", level="info", to_tab=True, to_gui=True, to_notification=False)


    def handle_stderr_sequential(self):
        """Handle standard error from the current process."""
        data = self.process.readAllStandardError().data().decode()
        self.current_command_output.append(data)
        self.logger.log_message(f"{data}", level="info", to_tab=True, to_gui=True, to_notification=False)

    def handle_process_finished_sequential(self, exit_code, exit_status):
        """Handle the completion of a single process in the sequence."""
        output_text = ''.join(self.current_command_output)

        self.logger.log_message(f"Process finished with exit code: {exit_code}", level="info", to_tab=True, to_gui=True, to_notification=False)
        self.logger.log_message(f"Process output: {output_text}", level="info", to_tab=True, to_gui=True, to_notification=False)

        if exit_code == 0 and "ERROR" not in output_text:
            self.logger.log_message(f"Command {self.current_command_index + 1} completed successfully", level="info", to_tab=True, to_gui=True, to_notification=False)

            # Move to next command
            self.current_command_index += 1
            self.run_next_command()
        else:
            self._handle_command_failure(exit_code, output_text)


    def _handle_command_failure(self, exit_code, output_text):
        """Handle the failure of a command."""
        error_message = (f"Command {self.current_command_index + 1} failed "
                         f"with exit code {exit_code}")
        if "ERROR" in output_text:
            error_message += f"\nError in survey2gis output detected"

        self.logger.log_message(error_message, level="error", to_tab=True, to_gui=True, to_notification=True)



    # => Save layer from source into geopackage

    def load_survey_data(self):
        """
        Load supported survey data formats (shapefiles, geojson) and save them to a single GeoPackage.
        """
        try:
            self.logger.log_message(f"\n{'='*50} Starting load_survey_data function (convert to geopackage + load to QGIS) \n{'='*50}", level="info", to_tab=True, to_gui=True, to_notification=False)

            # Get all commands from the command code field
            commands = [cmd.strip() for cmd in self.parent_widget.command_code_field.toPlainText().split('\n') if cmd.strip()]
            self.logger.log_message(f"Found {len(commands)} commands to process", level="info", to_tab=True, to_gui=True, to_notification=False)

            if not commands:
                self.logger.log_message("No commands found to process", level="error", to_tab=True, to_gui=True, to_notification=False)
                return

            root = QgsProject.instance().layerTreeRoot()
            processed_basenames = set()

            # Initialize a list to hold all layers across multiple basenames
            all_shape_layers = []
            all_geojson_layers = []

            # Use a single GeoPackage file for all layers
            output_dir = None  # We'll update this as we extract it from commands
            gpkg_path = None   # GeoPackage path will be defined when we know output_dir

            for command_index, command in enumerate(commands):
                self.logger.log_message(f"\nProcessing command {command_index + 1}/{len(commands)}", level="info", to_tab=True, to_gui=True, to_notification=False)
                self.logger.log_message(f"Command: {command}", level="info", to_tab=True, to_gui=True, to_notification=False)

                # Split the command while preserving quoted strings
                parts = self._split_command(command)

                # Extract output directory and basename from command
                current_output_dir, basename = self._extract_output_and_basename(parts)
                if not current_output_dir or not basename:
                    self.logger.log_message(f"Missing output directory or basename in command: {command}", level="info", to_tab=True, to_gui=True, to_notification=False)
                    continue

                # Set the output directory and GeoPackage path
                if output_dir is None:
                    output_dir = current_output_dir
                    gpkg_path = os.path.join(output_dir, "merged_data.gpkg")  # One GeoPackage for all

                # Skip if already processed
                if basename in processed_basenames:
                    self.logger.log_message(f"Skipping already processed basename: {basename}", level="info", to_tab=True, to_gui=True, to_notification=False)
                    continue

                processed_basenames.add(basename)

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
            if all_geojson_layers:
                splitted_geojson = self.split_geojson_files(all_geojson_layers)

            all = self.scan_directory_for_spatialfiles(current_output_dir)
            self.logger.log_message(f"Created files are {str(all)}", level="info", to_tab=True, to_gui=False, to_notification=False)
            self.logger.log_message(f"gpg path ist {str(gpkg_path)}", level="info", to_tab=True, to_gui=False, to_notification=False)

            self.iter_found_files_and_pass_to_geopackage(all, gpkg_path)
            self.logger.log_message("=== Completed load_survey_data function ===", level="info", to_tab=True, to_gui=False, to_notification=False)

        except Exception as e:
            self.logger.log_message(f"Error: {str(e)}", level="error", to_tab=True, to_gui=True, to_notification=True)

    def load_shapefiles(self, output_dir, basename):
        """
        Load shapefiles (labels, point, line, polygon) and return a list of QgsVectorLayers.
        """
        self.logger.log_message(f"\nLoading shapefiles for {basename}", level="info", to_tab=True, to_gui=True, to_notification=False)

        suffixes = ["_labels.shp", "_line.shp", "_point.shp", "_poly.shp"]
        layers = self._load_layers_by_format(output_dir, basename, suffixes, 'shp')

        if len(layers) > 0:
            return layers
        else:
            self.logger.log_message(f"No shapefiles found for {basename}", level="info", to_tab=True, to_gui=True, to_notification=False)
            return False

    def load_geojson_files(self, output_dir, basename):
        """
        Load shapefiles (labels, point, line, polygon) and return a list of QgsVectorLayers.
        """
        self.logger.log_message(f"Loading geojson for {basename}", level="info", to_tab=True, to_gui=True, to_notification=False)

        file_path = os.path.join(output_dir, basename + "_all.geojson")
        if os.path.exists(file_path):
            self.logger.log_message(f"Loading geojson file: {file_path}", level="info", to_tab=True, to_gui=True, to_notification=False)
            return file_path

        return False

    def _load_layers_by_format(self, output_dir, basename, suffixes, format_name):
        """Load files of a specific format and return a list of QgsVectorLayers."""
        layers = []
        for suffix in suffixes:
            file_path = os.path.join(output_dir, suffix if format_name != "shp" else basename + suffix)
            if os.path.exists(file_path):
                layer = QgsVectorLayer(file_path, os.path.splitext(os.path.basename(file_path))[0], "ogr")

                if layer.isValid():
                    layers.append(layer)
                    self.logger.log_message(f"Successfully added {format_name} layer: {layer.name()}", level="info", to_tab=True, to_gui=True, to_notification=False)

                else:
                    self.logger.log_message(f"Failed to create valid layer for: {file_path}", level="error", to_tab=True, to_gui=True, to_notification=True)


        return layers


    def clean_geojson_file(self, file_path):
        """Clean a GeoJSON file by fixing common formatting issues."""
        try:
            with open(file_path, 'r') as file:
                content = file.read()
                
            # Remove trailing commas before closing brackets/braces
            content = re.sub(r',(\s*[}\]])', r'\1', content)
            
            # Attempt to parse the cleaned content to verify it's valid JSON
            try:
                return json.loads(content)
            except json.JSONDecodeError as e:
                # If still invalid, try more aggressive cleaning
                content = re.sub(r',\s*([}\]])', r'\1', content)  # More aggressive comma removal
                content = re.sub(r'}\s*,\s*]', '}]', content)     # Fix specific case of "}, ]"
                return json.loads(content)
            
        except Exception as e:
            self.logger.log_message(f"Error cleaning GeoJSON file: {str(e)}", level="error", to_tab=True, to_gui=True, to_notification=True)
            return None

    def split_geojson_files(self, all_geojson_files):
        """Split GeoJSON files by geometry type after cleaning them."""
        geojson_files = []

        for input_geojson_path in all_geojson_files:
            try:
                # Clean and load the GeoJSON file
                geojson_data = self.clean_geojson_file(input_geojson_path)
                if not geojson_data:
                    self.logger.log_message(f"Skipping invalid GeoJSON file: {input_geojson_path}", level="error", to_tab=True, to_gui=True, to_notification=True)
                    continue

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
                    if not feature or 'geometry' not in feature:
                        continue
                        
                    geometry = feature.get('geometry')
                    if not geometry or 'type' not in geometry:
                        continue
                        
                    geom_type = geometry.get('type')
                    
                    # Handle Z types, assuming they have extra coordinates
                    try:
                        if geom_type == 'Polygon' and any(len(coord) == 3 for ring in geometry.get('coordinates', []) for coord in ring):
                            geom_type = 'PolygonZ'
                        elif geom_type == 'LineString' and any(len(coord) == 3 for coord in geometry.get('coordinates', [])):
                            geom_type = 'LineStringZ'
                        elif geom_type == 'Point' and len(geometry.get('coordinates', [])) == 3:
                            geom_type = 'PointZ'
                    except Exception as e:
                        self.logger.log_message(f"Error processing coordinates: {str(e)}", level="warning", to_tab=True, to_gui=True, to_notification=False)
                        continue

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
                        
                        try:
                            with open(temp_geojson_path, 'w') as temp_file:
                                json.dump(temp_geojson, temp_file, indent=2)
                            geojson_files.append(temp_geojson_path)
                        except Exception as e:
                            self.logger.log_message(f"Error saving GeoJSON file {temp_geojson_path}: {str(e)}", level="error", to_tab=True, to_gui=True, to_notification=True)

            except Exception as e:
                self.logger.log_message(f"Error processing GeoJSON file {input_geojson_path}: {str(e)}", level="error", to_tab=True, to_gui=True, to_notification=True)

        return geojson_files
    
    def scan_directory_for_spatialfiles(self, directory):

        # Initialize an empty dictionary with 'shp' and 'geojson' as top-level keys
        grouped_files = {
            'shp': {},
            'geojson': {}
        }

        # Compile regex to match the keywords polygon, point, or line (case-insensitive)
        keyword_pattern = re.compile(r'(poly|point|line|labels)', re.IGNORECASE)

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
                            grouped_files[file_type][prefix] = {'polygon': [], 'line': [], 'point': [], 'labels': []}

                        # Classify and add the file to the appropriate list under the file type and prefix
                        file_path = os.path.join(root, file)
                        if 'poly' in file_lower:
                            grouped_files[file_type][prefix]['polygon'].append(file_path)
                        elif 'line' in file_lower:
                            grouped_files[file_type][prefix]['line'].append(file_path)
                        elif 'point' in file_lower:
                            grouped_files[file_type][prefix]['point'].append(file_path)
                        elif 'labels' in file_lower:
                            grouped_files[file_type][prefix]['labels'].append(file_path)

        # Convert the dictionary to the desired format: type -> prefix -> list with [polygons, lines, points, labels]
        result = {}
        for file_type, prefixes in grouped_files.items():
            result[file_type] = {}
            for prefix, file_dict in prefixes.items():
                # Combine the lists into the desired order: polygons first, lines second, points third, labels last
                result[file_type][prefix] = file_dict['polygon'] + file_dict['line'] + file_dict['point'] + file_dict['labels']

        self.intermediate_file_dict = result

        return result


    def iter_found_files_and_pass_to_geopackage(self, data, output_gpkg):

        # Create the output GPKG file only once
        drv = ogr.GetDriverByName('GPKG')
        out_ds = drv.CreateDataSource(output_gpkg)

        if os.path.exists(output_gpkg):
            self.logger.log_message(f"geopackage exists: {output_gpkg}", level="info", to_tab=True, to_gui=False, to_notification=False)

            # os.remove(output_gpkg)  # Remove existing file if present

            group_name = "My Merged Data"
            # Iterate over the dictionary
            self.logger.log_message(f"{str(data.items())}", level="info", to_tab=True, to_gui=False, to_notification=False)

            for file_type, groups in data.items():
                for group, file_list in groups.items():
                    self.logger.log_message(f"Processing Group: {group}", level="info", to_tab=True, to_gui=False, to_notification=False)
                    self.logger.log_message(f"list is {file_list}", level="info", to_tab=True, to_gui=False, to_notification=False)

                    group_name = group
                    # Pass the open GeoPackage data source (out_ds) to the function
                    self.geojsons_and_shapefiles_to_gpkg(file_list, out_ds)

            self.add_layers_from_geopackage(output_gpkg)

            # Cleanup: Close the GeoPackage
            del out_ds


    # def geojsons_and_shapefiles_to_gpkg(self, files, out_ds):
    #     """Add layers from GeoJSON/Shapefile files to a GeoPackage with renamed fields."""
    #     self.logger.log_message(f"received files {files} for geopackage", level="info", to_tab=True, to_gui=False, to_notification=False)

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

    #         # Get new layer definition with renamed fields
    #         new_layer_defn = self.get_renamed_layer_defn(lyr)
    #         new_layer = out_ds.CreateLayer(layer_name, geom_type=lyr.GetGeomType())

    #         # Add fields from new layer definition to the new layer
    #         for i in range(new_layer_defn.GetFieldCount()):
    #             new_layer.CreateField(new_layer_defn.GetFieldDefn(i))

    #         # Copy features with renamed fields to the new layer
    #         for feature in lyr:
    #             new_feature = ogr.Feature(new_layer.GetLayerDefn())
    #             for i in range(lyr.GetLayerDefn().GetFieldCount()):
    #                 original_field_name = lyr.GetLayerDefn().GetFieldDefn(i).GetName()
    #                 alias_field_name = self.alias_mapping.get(original_field_name, original_field_name)
                    
    #                 # Set the field in the new feature using the renamed field name
    #                 new_feature.SetField(alias_field_name, feature.GetField(original_field_name))

    #             # Set the geometry for the new feature
    #             new_feature.SetGeometry(feature.GetGeometryRef())
    #             new_layer.CreateFeature(new_feature)
    #             new_feature = None  # Clean up

    #         created_layers.append(layer_name)

    #         # Cleanup
    #         del ds

    #     return created_layers


    def geojsons_and_shapefiles_to_gpkg(self, files, out_ds):
        """Add layers from GeoJSON/Shapefile files to a GeoPackage with renamed fields."""
        created_layers = []
        
        # Create spatial reference for EPSG:25832
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(25832)

        for file in files:
            ds = ogr.Open(file)
            if ds is None:
                self.logger.log_message(f"Could not open {file}", level="error", to_tab=True, to_gui=True, to_notification=True)
                continue

            lyr = ds.GetLayer()
            layer_name = os.path.splitext(os.path.basename(file))[0]

            # Create new layer with SRS
            new_layer_defn = self.get_renamed_layer_defn(lyr)
            # new_layer = out_ds.CreateLayer(layer_name, srs, lyr.GetGeomType())
            new_layer = out_ds.CreateLayer(layer_name, geom_type=lyr.GetGeomType())

            # Add fields from new layer definition
            for i in range(new_layer_defn.GetFieldCount()):
                new_layer.CreateField(new_layer_defn.GetFieldDefn(i))

            # Copy features
            for feature in lyr:
                new_feature = ogr.Feature(new_layer.GetLayerDefn())
                for i in range(lyr.GetLayerDefn().GetFieldCount()):
                    original_field_name = lyr.GetLayerDefn().GetFieldDefn(i).GetName()
                    alias_field_name = self.alias_mapping.get(original_field_name, original_field_name)
                    new_feature.SetField(alias_field_name, feature.GetField(original_field_name))

                new_feature.SetGeometry(feature.GetGeometryRef())
                new_layer.CreateFeature(new_feature)
                new_feature = None

            created_layers.append(layer_name)
            ds = None

        return created_layers

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


    # ---> helper ?

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
            elif part == '-n' and i + 1 < len(parts):
                basename = parts[i + 1].strip('"')

        return output_dir, basename

    # => Load Shapefiles from source into qgis


    def add_layers_from_geopackage(self, gpkg_path):
        """Add layers from GeoPackage with project CRS and styles."""
        try:
            conn = ogr.Open(gpkg_path)
            if conn is None:
                self.logger.log_message(f"Failed to open GeoPackage: {gpkg_path}", level="error", to_tab=True, to_gui=True, to_notification=True)
                return

            # Get directories
            gpkg_dir = os.path.dirname(gpkg_path)
            qml_dir = os.path.join(gpkg_dir, "qml")
            svg_dir = os.path.join(qml_dir, "svg")
            
            has_qml_dir = os.path.exists(qml_dir) and os.path.isdir(qml_dir)
            has_svg_dir = os.path.exists(svg_dir) and os.path.isdir(svg_dir)
            
            # Get project CRS
            project_crs = QgsProject.instance().crs()
            
            if has_svg_dir:
                self.add_svg_path(svg_dir)
                self.logger.log_message(f"Added SVG path: {svg_dir}", level="info", to_tab=True, to_gui=True, to_notification=False)
            
            if has_qml_dir:
                self.logger.log_message(f"Found QML directory: {qml_dir}", level="info", to_tab=True, to_gui=True, to_notification=False)
            
            root = QgsProject.instance().layerTreeRoot()
            layer_count = conn.GetLayerCount()
            group_dict = {}
            
            for i in range(layer_count):
                layer = conn.GetLayerByIndex(i)
                layer_name = layer.GetName()
                group_name = layer_name.split('_', 1)[0]

                if group_name not in group_dict:
                    group = root.findGroup(group_name)
                    if group is None:
                        group = root.addGroup(group_name)
                    group_dict[group_name] = group
                else:
                    group = group_dict[group_name]
                
                layer_uri = f"{gpkg_path}|layername={layer_name}"
                new_layer = QgsVectorLayer(layer_uri, layer_name, "ogr")
                
                if new_layer.isValid():
                    # Set project CRS for the layer
                    new_layer.setCrs(project_crs)
                    
                    QgsProject.instance().addMapLayer(new_layer, False)
                    
                    if has_qml_dir:
                        qml_file = os.path.join(qml_dir, f"{layer_name}.qml")
                        if os.path.exists(qml_file):
                            style_success = False
                            style_message = ""
                            
                            modified_qml = self.update_svg_paths_in_qml(qml_file, svg_dir)
                            if modified_qml:
                                style_success = self.apply_modified_style(new_layer, modified_qml)[0]  # Get first element of tuple
                            else:
                                style_success, style_message = new_layer.loadNamedStyle(qml_file)
                            
                            if style_message:
                                self.logger.log_message(f"Applied style from {qml_file} to layer {layer_name}", 
                                                    level="info", to_tab=True, to_gui=True, to_notification=False)
                            else:
                                self.logger.log_message(f"Failed to apply style from {qml_file} to layer {layer_name}: {style_message}", 
                                                    level="warning", to_tab=True, to_gui=True, to_notification=False)
                    
                    group.insertLayer(0, new_layer)
                    self.logger.log_message(f"Successfully added layer: {layer_name} under group: {group_name}", 
                                        level="info", to_tab=True, to_gui=True, to_notification=False)
                else:
                    self.logger.log_message(f"Failed to add layer: {layer_name} to QGIS", 
                                        level="error", to_tab=True, to_gui=True, to_notification=True)

            del conn

        finally:
            if has_svg_dir:
                self.restore_svg_paths()
                self.logger.log_message(f"Restored original SVG paths", level="info", to_tab=True, to_gui=True, to_notification=False)
            # self.handle_file_cleanup()


    def add_svg_path(self, svg_path):
        """Add SVG path to QGIS settings temporarily for this session."""
        from qgis.core import QgsSettings
        settings = QgsSettings()
        
        # Get existing SVG paths
        svg_paths = settings.value("svg/searchPathsForSVG", [])
        if isinstance(svg_paths, str):
            svg_paths = [svg_paths]
        
        # Store original paths for later cleanup
        if not hasattr(self, '_original_svg_paths'):
            self._original_svg_paths = svg_paths.copy()
        
        # Add new path if it's not already in the list
        if svg_path not in svg_paths:
            svg_paths.append(svg_path)
            settings.setValue("svg/searchPathsForSVG", svg_paths)
            # No need to call refresh directly - QGIS will handle this
            self.logger.log_message(f"Temporarily added SVG path for this session: {svg_path}", 
                                level="info", to_tab=True, to_gui=True, to_notification=False)

    def restore_svg_paths(self):
        """Restore original SVG paths."""
        if hasattr(self, '_original_svg_paths'):
            from qgis.core import QgsSettings
            settings = QgsSettings()
            settings.setValue("svg/searchPathsForSVG", self._original_svg_paths)
            # No need to call refresh directly - QGIS will handle this
            self.logger.log_message("Restored original SVG paths", 
                                level="info", to_tab=True, to_gui=True, to_notification=False)

    def __del__(self):
        """Cleanup when the object is deleted."""
        self.restore_svg_paths()

    def update_svg_paths_in_qml(self, qml_file, svg_dir):
        """Update SVG paths in QML content to use absolute paths."""
        try:
            import xml.etree.ElementTree as ET
            
            # Parse the QML file
            tree = ET.parse(qml_file)
            root = tree.getroot()
            
            # Find all SVG marker elements
            modified = False
            for prop in root.findall(".//prop[@k='name']"):
                if 'svg' in prop.get('v', '').lower():
                    # Get the relative SVG path
                    svg_name = prop.get('v')
                    # Create absolute path
                    abs_path = os.path.join(svg_dir, os.path.basename(svg_name))
                    if os.path.exists(abs_path):
                        prop.set('v', abs_path)
                        modified = True
            
            if modified:
                # Return the modified XML as string
                return ET.tostring(root, encoding='unicode')
            return None
            
        except Exception as e:
            self.logger.log_message(f"Error updating SVG paths in QML: {str(e)}", 
                                level="error", to_tab=True, to_gui=True, to_notification=True)
            return None

    def apply_modified_style(self, layer, style_content):
        """Apply modified style content to layer."""
        import tempfile
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.qml', delete=False) as temp_file:
                temp_file.write(style_content)
                temp_file.flush()
                # Return the tuple from loadNamedStyle
                return layer.loadNamedStyle(temp_file.name)
        except Exception as e:
            self.logger.log_message(f"Error applying modified style: {str(e)}", 
                                level="error", to_tab=True, to_gui=True, to_notification=True)
            return False, str(e)  # Return tuple for consistency

    # => General GUI methods
    def save_command_history(self):
        """Save the current command history to a file."""
        try:
            with open(self.command_history_file, 'w', encoding='utf-8') as f:
                f.write(self.parent_widget.command_code_field.toPlainText())
            self.logger.log_message(f"Command history saved to {self.command_history_file}", level="success", to_tab=True, to_gui=False, to_notification=True)

        except Exception as e:
            self.logger.log_message(f"Error saving command history: {e}", level="error", to_tab=True, to_gui=True, to_notification=True)

    def load_command_history(self):
        """Load command history from file if it exists."""
        try:
            if os.path.exists(self.command_history_file):
                with open(self.command_history_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if content.strip():  # Check if file has non-whitespace content
                        self.parent_widget.command_code_field.setPlainText(content)
                        self.logger.log_message(f"Command history loaded from {self.command_history_file}", level="info", to_tab=True, to_gui=True, to_notification=False)

        except Exception as e:
            self.logger.log_message(f"Error loading command history: {e}", level="error", to_tab=True, to_gui=True, to_notification=False)

    def handle_file_cleanup(self):
        """
        Clean up generated files unless keep_files exists.
        For shapefiles, also removes associated files (.dbf, .shx, .prj, etc.).
        """
        # Step 1: Get base path
        base_path = os.path.dirname(__file__)
        
        # Step 2: Check for the presence of `keep_files`
        keep_files_path = os.path.join(base_path, '..', 'keep_files')
        self.logger.log_message(self.intermediate_file_dict, to_tab=True, to_gui=True, to_notification=False)

        # Step 3: If `keep_files` does not exist, delete files listed in the dictionary
        if not os.path.exists(keep_files_path):
            for file_type, groups in self.intermediate_file_dict.items():
                for group, file_list in groups.items():
                    for file_path in file_list:
                        if file_path.lower().endswith('.shp'):
                            # Handle shapefile and its associated files
                            self._delete_shapefile_set(file_path)
                        else:
                            # Handle regular file deletion
                            self._delete_single_file(file_path)
        else:
            self.logger.log_message(f"keep_files file found, skipping deletion.", 
                                level="info", to_tab=True, to_gui=True, to_notification=False)

    def _delete_shapefile_set(self, shp_path):
        """Delete a shapefile and all its associated files."""
        # Common shapefile extensions
        extensions = ['.shp', '.shx', '.dbf', '.prj', '.cpg', '.sbn', '.sbx', '.shp.xml', '.qix', '.gva']
        base_path = os.path.splitext(shp_path)[0]
        
        for ext in extensions:
            associated_file = base_path + ext
            self._delete_single_file(associated_file)

    def _delete_single_file(self, file_path):
        """Delete a single file with proper error handling and logging."""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                self.logger.log_message(f"Deleted: {file_path}", 
                                    level="info", to_tab=True, to_gui=True, to_notification=False)
            else:
                self.logger.log_message(f"File not found, could not delete: {file_path}", 
                                    level="info", to_tab=True, to_gui=True, to_notification=False)
        except Exception as e:
            self.logger.log_message(f"Error deleting {file_path}: {str(e)}", 
                                level="error", to_tab=True, to_gui=True, to_notification=True)
                              
    def load_alias_mapping(self, alias_file):

        if not os.path.exists(alias_file):
            return {}
        
        self.logger.log_message(f"Using alias file {alias_file}", level="info", to_tab=True, to_gui=True, to_notification=False)

        """Load alias mappings from an .ini file."""
        config = configparser.ConfigParser()
        config.read(alias_file)
        # Assume all mappings are under a single section called 'aliases'
        return dict(config['aliases']) if 'aliases' in config else {}