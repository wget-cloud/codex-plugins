PYTHON ?= python3
PYTHON_NO_BYTECODE = PYTHONDONTWRITEBYTECODE=1 $(PYTHON)
IMPLEMENTATION_PLUGIN := plugins/wget-cloud-implementation

.PHONY: validate structure hooks-test official-validators skills-build

OFFICIAL_VALIDATOR_ARGS ?= --allow-download

validate: structure hooks-test official-validators

structure:
	$(PYTHON_NO_BYTECODE) scripts/build_wgc_skills.py --check
	$(PYTHON_NO_BYTECODE) scripts/validate_marketplace.py
	$(PYTHON_NO_BYTECODE) -m unittest discover -s scripts/tests -v
	$(PYTHON_NO_BYTECODE) -B -c "from pathlib import Path; files = [Path(path) for path in ['scripts/validate_marketplace.py', 'scripts/run_official_validators.py', '$(IMPLEMENTATION_PLUGIN)/hooks/wgc_hooks.py']]; [compile(path.read_text(encoding='utf-8'), str(path), 'exec') for path in files]"

hooks-test:
	$(PYTHON_NO_BYTECODE) -m unittest discover -s $(IMPLEMENTATION_PLUGIN)/hooks/tests -v

official-validators:
	$(PYTHON_NO_BYTECODE) scripts/run_official_validators.py $(OFFICIAL_VALIDATOR_ARGS)

skills-build:
	$(PYTHON_NO_BYTECODE) scripts/build_wgc_skills.py
