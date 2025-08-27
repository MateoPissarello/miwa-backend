### Use official Python image
FROM nikolaik/python-nodejs:python3.12-nodejs24-slim

# Update system packages to fix vulnerabilities and install git
RUN apt-get update && apt-get upgrade -y && apt-get clean && apt-get install -y git

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY ./backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY ./backend /app
# Expose port
EXPOSE 80

# Run the FastAPI app using uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80"]