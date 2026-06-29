.PHONY: test check-python check-r

test: check-python check-r
	python -m unittest discover -s tests -v

check-python:
	python -m py_compile src/stage1/*.py src/stage2/*.py

check-r:
	Rscript scripts/check_r_dependencies.R
