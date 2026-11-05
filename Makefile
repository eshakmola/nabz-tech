.PHONY: help install browsers test lint fmt all scrape gnews hub clean docker

help:
	@echo "install   : pip install -e .[dev]"
	@echo "browsers  : scrapling install (Chromium for Patchright)"
	@echo "test      : pytest (no browser needed)"
	@echo "lint/fmt  : ruff check / ruff format"
	@echo "scrape    : scrape Perplexity tech + build site/index.html"
	@echo "gnews     : scrape Google News RSS (links resolved, image+text)"
	@echo "hub       : scrape both + build site/index.html (All / Perplexity / G News)"
	@echo "docker    : build the container image"

install:
	python -m pip install -e ".[dev]"

browsers:
	scrapling install

test:
	python -m pytest --cov=pdx --cov-report=term-missing

lint:
	ruff check .

fmt:
	ruff format . && ruff check . --fix

scrape:
	python perplexity_tech_scraper.py --category tech --out output --site site

gnews:
	python gnews_scraper.py --limit 10 --out output --site site

hub:
	python build_hub.py --refresh --limit 10 --out site/index.html

clean:
	rm -rf output site smoke smoke2 .pytest_cache .ruff_cache __pycache__ pdx/__pycache__ coverage.xml *.zip

docker:
	docker build -t perplexity-discover-scraper:local .
