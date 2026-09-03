PYTHON ?= python3
PYTHON_NO_BYTECODE = PYTHONDONTWRITEBYTECODE=1 $(PYTHON)
IMPLEMENTATION_PLUGIN := plugins/wget-cloud-implementation
MAINTAINER_PLUGIN := plugins/wget-cloud-plugin-maintainer

.PHONY: validate structure hooks-test eval-test shadow-eval official-validators

OFFICIAL_VALIDATOR_ARGS ?= --allow-download

validate: structure hooks-test eval-test official-validators

structure:
	$(PYTHON_NO_BYTECODE) scripts/validate_marketplace.py
	$(PYTHON_NO_BYTECODE) -m unittest discover -s scripts/tests -v
	$(PYTHON_NO_BYTECODE) -B -c "from pathlib import Path; files = [Path(path) for path in ['scripts/validate_marketplace.py', 'scripts/run_official_validators.py', '$(IMPLEMENTATION_PLUGIN)/hooks/wgc_hooks.py', '$(MAINTAINER_PLUGIN)/hooks/maintainer_hooks.py', '$(MAINTAINER_PLUGIN)/scripts/validate_eval_corpus.py', '$(MAINTAINER_PLUGIN)/scripts/run_shadow_eval.py', '$(MAINTAINER_PLUGIN)/scripts/verify_external_evidence.py', '$(MAINTAINER_PLUGIN)/scripts/validate_maintainer_contracts.py']]; [compile(path.read_text(encoding='utf-8'), str(path), 'exec') for path in files]"

hooks-test:
	$(PYTHON_NO_BYTECODE) -m unittest discover -s $(IMPLEMENTATION_PLUGIN)/hooks/tests -v
	$(PYTHON_NO_BYTECODE) -m unittest discover -s $(MAINTAINER_PLUGIN)/hooks/tests -v

eval-test:
	$(PYTHON_NO_BYTECODE) -m unittest discover -s $(MAINTAINER_PLUGIN)/scripts/tests -v
	$(PYTHON_NO_BYTECODE) $(MAINTAINER_PLUGIN)/scripts/validate_eval_corpus.py
	$(PYTHON_NO_BYTECODE) $(MAINTAINER_PLUGIN)/scripts/validate_maintainer_contracts.py

shadow-eval:
	$(PYTHON_NO_BYTECODE) $(MAINTAINER_PLUGIN)/scripts/run_shadow_eval.py --help

official-validators:
	$(PYTHON_NO_BYTECODE) scripts/run_official_validators.py $(OFFICIAL_VALIDATOR_ARGS)
