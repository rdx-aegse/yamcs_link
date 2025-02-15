#!/bin/bash

# Function to handle shutdown
shutdown() {
    echo "Shutting down..."
    docker-compose down -v
    exit
}

# Set up trap for SIGINT and SIGTERM
trap shutdown SIGINT SIGTERM

# Start docker-compose in detached mode
docker-compose up --build -d

# Follow logs in the background
docker-compose logs -f &

# Wait indefinitely
while true; do
    sleep 1
done
