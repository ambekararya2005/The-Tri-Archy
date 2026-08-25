# The API, for Hugging Face Spaces (the fallback target) or any container host.
#
# Spaces expects the app on 7860; Render and Railway inject $PORT. Both are
# honoured because mantis/api/__main__.py reads $PORT with a default, so this
# image works unchanged on all three.
FROM python:3.11-slim

WORKDIR /app

# Dependencies first, so a source-only change does not reinstall LightGBM.
COPY pyproject.toml README.md ./
COPY mantis ./mantis
RUN pip install --no-cache-dir -e .

# The committed artefacts the API serves. data/generated is gitignored except
# for these, which are the demo's whole payload: pre-scored authorisations, the
# arena, and the OOD probe result.
COPY RESULTS.md ./RESULTS.md
COPY data/cache ./data/cache
COPY data/reference ./data/reference
COPY data/generated/arena.json data/generated/console_feed.json data/generated/l3_ood.json data/generated/population.manifest.json ./data/generated/
COPY docs ./docs

ENV PORT=7860
EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",7860)}/health')"

CMD ["python", "-m", "mantis.api", "--host", "0.0.0.0"]
