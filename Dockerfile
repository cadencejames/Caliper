# 1. Use a lightweight Python base image
FROM python:3.9-slim

# 2. Set the working directory inside the container
WORKDIR /app

# 3. Copy the requirements file first (for better caching)
COPY requirements.txt .

# 4. Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy the rest of your application code
COPY . .

# 6. Expose the port Flask runs on (internal container port)
EXPOSE 5000

# 7. The command to run when the container starts
# We use '0.0.0.0' to make sure it listens to outside traffic (the host)
CMD ["python", "app.py"]