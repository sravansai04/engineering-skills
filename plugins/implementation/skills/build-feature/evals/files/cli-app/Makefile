.PHONY: test lint

# Run the whole suite, or one module: make test TEST=tests.test_list
test:
	python3 -m unittest $(or $(TEST),discover -s tests -t .) -v

lint:
	python3 -m compileall -q cli tests
