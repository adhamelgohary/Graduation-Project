# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set work directory
WORKDIR /app

# Install dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . /app

# Expose port
EXPOSE 8000

# Copy start script
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Run start script
CMD ["bash", "/app/start.sh"]