import pytest
from unittest.mock import MagicMock, patch
import os
from pathlib import Path
from ..components.data_normalizer import DataNormalizer
import sys
import os

# Path to your QGIS installation
qgis_path = "/Applications/QGIS.app/Contents/MacOS"

# Update Python paths
sys.path.append(os.path.join(qgis_path, "Resources/python"))
sys.path.append(os.path.join(qgis_path, "Resources/python/plugins"))



@pytest.fixture
def mock_parent_widget():
    """Fixture to create a mock for the parent widget with necessary attributes."""
    mock_widget = MagicMock()
    mock_widget.input_select.text.return_value = "input.txt; input2.txt"
    mock_widget.output_select_input.text.return_value = "/fake/output/dir"
    mock_widget.styles_folder_path_input.text.return_value = "/fake/styles/dir"
    mock_widget.CONCAT_OUTPUT_NAME = "concatenated_output.txt"
    mock_widget.cols_after_ids_input.text.return_value = "column1-column2"
    return mock_widget

@pytest.fixture
def data_normalizer(mock_parent_widget):
    """Fixture to create a DataNormalizer instance with a mock parent widget."""
    return DataNormalizer(mock_parent_widget)

def test_select_input_files(data_normalizer, mock_parent_widget):
    """Test selecting input files and setting input field text."""
    with patch('PyQt5.QtWidgets.QFileDialog.getOpenFileNames', return_value=(['file1.dat', 'file2.txt'], "")):
        data_normalizer.select_input_files()
        mock_parent_widget.input_select.setText.assert_called_once_with('file1.dat; file2.txt')

def test_reset_text_field(data_normalizer, mock_parent_widget):
    """Test that reset_text_field sets the text field to an empty string."""
    data_normalizer.reset_text_field(mock_parent_widget.input_select)
    mock_parent_widget.input_select.setText.assert_called_once_with("")

def test_select_output_directory(data_normalizer, mock_parent_widget):
    """Test selecting an output directory."""
    with patch('PyQt5.QtWidgets.QFileDialog.getExistingDirectory', return_value="/output/dir"):
        data_normalizer.select_output_directory()
        mock_parent_widget.output_select_input.setText.assert_called_once_with("/output/dir")

def test_run_normalize_missing_fields(data_normalizer, mock_parent_widget):
    """Test that run_normalize logs an error if required fields are empty."""
    mock_parent_widget.input_select.text.return_value = ""  # Empty input field
    data_normalizer.run_normalize()
    data_normalizer.logger.log_message.assert_called_once_with(
        "Please fill all required fields in Tab 'Normalize'",
        level="error", to_tab=True, to_gui=True, to_notification=True
    )

def test_run_normalize_success(data_normalizer, mock_parent_widget):
    """Test the successful run of run_normalize."""
    with patch.object(data_normalizer, '_concatenate_files'), \
         patch.object(data_normalizer, '_clean_file_content'), \
         patch.object(data_normalizer, '_copy_qml_files'), \
         patch.object(data_normalizer, '_replace_geotag_symbols'), \
         patch.object(data_normalizer, '_fix_line_numbering'), \
         patch.object(data_normalizer, '_add_columns_after_line_number'):

        # Check that all processing steps are called correctly
        data_normalizer.run_normalize()
        data_normalizer._concatenate_files.assert_called_once()
        data_normalizer._clean_file_content.assert_called_once()
        data_normalizer._copy_qml_files.assert_called()
        data_normalizer._replace_geotag_symbols.assert_called()
        data_normalizer._fix_line_numbering.assert_called()
        data_normalizer._add_columns_after_line_number.assert_called()

def test_concatenate_files(data_normalizer, mock_parent_widget, tmpdir):
    """Test concatenating multiple input files."""
    # Create temp files in the temp directory
    input_file1 = tmpdir.join("file1.txt")
    input_file1.write("Line 1\nLine 2\n")
    input_file2 = tmpdir.join("file2.txt")
    input_file2.write("Line 3\n")

    mock_parent_widget.input_select.text.return_value = f"{input_file1}; {input_file2}"
    mock_parent_widget.output_select_input.text.return_value = str(tmpdir)
    mock_parent_widget.CONCAT_OUTPUT_NAME = "output.txt"

    data_normalizer._concatenate_files()

    # Check output file
    output_file = tmpdir.join("output.txt")
    assert output_file.read() == "Line 1\nLine 2\nLine 3\n"

def test_clean_file_content(data_normalizer, tmpdir):
    """Test cleaning file content to remove extra spaces and empty lines."""
    input_file = tmpdir.join("uncleaned.txt")
    input_file.write("  Line 1   \n\nLine    2\n  ")
    data_normalizer._clean_file_content(str(input_file))

    # Check cleaned content
    assert input_file.read() == "Line 1\nLine 2\n"

def test_copy_qml_files(data_normalizer, mock_parent_widget, tmpdir):
    """Test copying .qml files from styles directory to output directory."""
    # Setup fake directories and files
    styles_dir = tmpdir.mkdir("styles")
    styles_dir.join("style1.qml").write("style1")
    styles_dir.join("style2.qml").write("style2")
    output_dir = tmpdir.mkdir("output")

    mock_parent_widget.styles_folder_path_input.text.return_value = str(styles_dir)
    mock_parent_widget.output_select_input.text.return_value = str(output_dir)

    data_normalizer._copy_qml_files()

    # Verify files are copied
    assert output_dir.join("qml").join("style1.qml").check(file=True)
    assert output_dir.join("qml").join("style2.qml").check(file=True)

def test_replace_geotag_symbols(data_normalizer, mock_parent_widget, tmpdir):
    """Test replacing '&' with '$' in a file."""
    output_file = tmpdir.join("concatenated_output.txt")
    output_file.write("Sample & text\nAnother & line\n")

    mock_parent_widget.output_select_input.text.return_value = str(tmpdir)
    mock_parent_widget.CONCAT_OUTPUT_NAME = "concatenated_output.txt"

    data_normalizer._replace_geotag_symbols()

    assert output_file.read() == "Sample $ text\nAnother $ line\n"
