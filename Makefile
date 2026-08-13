PYTHON ?= python3
PLUGIN := plugins/wget-cloud-implementation

.PHONY: validate structure hooks-test

validate: structure hooks-test

structure:
	$(PYTHON) scripts/validate_marketplace.py
	$(PYTHON) -m py_compile scripts/validate_marketplace.py $(PLUGIN)/hooks/wgc_hooks.py

hooks-test:
	$(PYTHON) -m unittest discover -s $(PLUGIN)/hooks/tests -v
