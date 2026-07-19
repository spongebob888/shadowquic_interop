.PHONY: test generate run serve

test:
	python3 -m unittest discover -s tests -v

generate:
	python3 -m shadowquic_interop generate

run:
	python3 -m shadowquic_interop run

serve: generate
	python3 -m http.server 8000 --directory site

