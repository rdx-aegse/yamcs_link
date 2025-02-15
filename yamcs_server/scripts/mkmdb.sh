#!/bin/bash

# Check if at least one directory is provided
if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
    echo "Usage: $0 <input_directory> [output_directory]"
    exit 1
fi

input_directory="$1"
output_directory="${2:-.}"  # Default to current directory if no output directory is provided

echo "Converting all CSV files in $input_directory to XLS workbooks in $output_directory"

# Navigate to the specified input directory
cd "$input_directory"

# Create an associative array to hold links to sheets grouped by prefix
declare -A sheets

# Loop through all CSV files in the directory
shopt -s nullglob  # Enable nullglob so that *.csv expands to nothing if no matches found
for file in *.csv; do
    # Extract the prefix (part before the underscore)
    prefix="${file%%_*}"
    # Extract sheetName from the filename (for each prefix_sheetName.csv get sheetName)
    sheetName="${file#*_}"  # Remove everything before and including the underscore
    sheetName="${sheetName%.csv}"  # Remove .csv extension

    # Create folder $prefix if it doesn't exist
    mkdir -p "$prefix"
    # Create a symbolic link with filename sheetName pointing to the CSV file prefix_sheetName.csv
    sheetPath="$prefix/$sheetName"
    echo "Registering worksheet $sheetName (file $file) to workbook $prefix as temporary symlink $sheetPath"
    ln -s "../$file" "$sheetPath"

    # Append the link to the worksheet to the corresponding prefix in the array
    sheets["$prefix"]+="$sheetPath "
done

# Convert each group of CSV files into a single XLS file in the specified output directory
for prefix in "${!sheets[@]}"; do
    output_file="$output_directory/${prefix}.xls"  # Define output file path

    # Echo the resulting command called (verbose)
    echo "Converting ${sheets[$prefix]} to $output_file"
    
    ssconvert --merge-to="$output_file" ${sheets[$prefix]}

    # Clean up temporary directory after conversion
    rm -rf "$prefix"
done
