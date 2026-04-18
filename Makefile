# ERP Analyst Agent — Developer Makefile

.PHONY: install demo run test lint clean

## Install all Python dependencies
install:
	pip install -r requirements.txt

## Generate the demo ERP SQLite database
demo:
	python data/generate_demo_db.py

## Run the Streamlit app
run:
	streamlit run app/main.py

## Run both: generate demo DB then start app
start: demo run

## Run tests
test:
	pytest tests/ -v --tb=short

## Lint with ruff
lint:
	ruff check app/ tests/ --fix

## Format with black
format:
	black app/ tests/ data/

## Clean up __pycache__ and .pyc files
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
