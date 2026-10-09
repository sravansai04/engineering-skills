.PHONY: test lint

# Run the whole suite, or one file: make test TEST=tests/cli/test_list.py
test:
	uv run pytest -q $(or $(TEST),tests)

lint:
	uv run ruff check cli tests
