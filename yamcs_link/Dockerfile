# Use official Python image as base
FROM python:3

# Set working directory
WORKDIR /test

# Copy the host's custom code
COPY ./src /test

# Set the command to run yamcs_link.py
CMD ["python", "yamcs_link.py"]