.PHONY: start setup remove install deploy test

# Define variables for commands, files, and application settings
PYTHON = python3
PIP = pip
LOGFILE = output.log
APP_NAME = geo-tag-pipeline
APP_MODULE = api.main:app
HOST = 0.0.0.0
PORT = 8000
RELOAD = --reload

dev:
	@echo "Starting the application..."
	@uvicorn $(APP_MODULE) --host $(HOST) --port $(PORT) $(RELOAD)

setup:
	@echo "Updating system packages..."
	@yum update -y
	@echo "Installing Python 3.9 and pip..."
	@yum install -y $(PYTHON) python3-pip
	@echo "Installing required Python packages..."
	@$(PIP) install fastapi 'uvicorn[standard]' gunicorn

remove:
ifndef PACKAGE
	$(error PACKAGE is not set. Use: make remove PACKAGE="<package_name>")
endif
	@echo "Uninstalling package $(PACKAGE)..."
	@$(PIP) uninstall -y $(PACKAGE)
	@echo "Updating requirements.txt..."
	@$(PIP) freeze > requirements.txt

install:
ifdef PACKAGE
	@echo "Installing package $(PACKAGE)..."
	@$(PIP) install $(PACKAGE)
	@echo "Writing installed package to requirements.txt..."
	@$(PIP) freeze | grep $(PACKAGE) | tee -a requirements.txt
else
	@echo "No package specified. Installing from requirements.txt instead..."
	@$(PIP) install -r requirements.txt
endif

deploy:
	@echo "Pulling latest changes from Git..."
	@git pull
	@echo "Installing dependencies..."
	@$(PIP) install -r requirements.txt
	@echo "Checking and stopping $(APP_NAME) if it is already running..."
	@-PID=$$(sudo lsof -ti:8000); \
	if [ -n "$$PID" ]; then \
		echo "Stopping running instance on port 8000 with PID $$PID..."; \
		sudo kill -9 $$PID || echo "Failed to stop process $$PID"; \
	fi
	@sleep 5  # Gives some time for the process to be terminated
	@echo "Starting $(APP_NAME)..."
	@gunicorn -k uvicorn.workers.UvicornWorker $(APP_MODULE) --name $(APP_NAME) -b 0.0.0.0:8000 -D || { echo "Gunicorn failed to start. Deployment failed." && exit 1; }
	@echo "Successfully started $(APP_NAME)."

test:
	@echo "Running tests..."
	@${PYTHON} -m pytest tests/ --cov=tests --cov-report=term-missing

