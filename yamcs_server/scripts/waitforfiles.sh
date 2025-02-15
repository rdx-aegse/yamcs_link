#!/bin/bash

if [ $# -eq 0 ]; then
    echo "Usage: $0 <folder_path>"
    exit 1
fi

folder_path="$1"
timeout=30  # seconds

if [ ! -d "$folder_path" ]; then
    echo "Error: '$folder_path' is not a valid directory."
    exit 1
fi

echo "Waiting for files in folder '$folder_path'..."

t=0
while [ -z "$(ls -A "$folder_path")" ]; do
    sleep 1
    ((t++))
    if [ $t -ge $timeout ]; then
        echo "Timeout reached. Folder is still empty."
        exit 1
    fi
done

echo "Folder is no longer empty. Resuming execution"
