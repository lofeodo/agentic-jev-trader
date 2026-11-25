# The Python image: one image for every Python piece (spec appendix 10, section 3), each
# started by its own command:
#   memory server   python -m jev_trader.memory serve
#   API             python -m jev_trader.api serve
#   sim job         python -m jev_trader.sim resume <sim id>
#   dataset build   python -m jev_trader.dataset build <settings file>
# Built and loaded into kind by `conda run -n agentic-jev-trader python infra/images.py build`, tagged with the git commit.
#
# It never holds a secret: only the folders copied below enter it, and .dockerignore keeps
# .env, keys and saved tables out of what Docker is even sent. Secrets reach a running
# container from the cluster.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# The code reads config/, prompts/ and datasets/ beside src/, as in a checkout, so the
# package is installed in place (`-e .`) under /app.
WORKDIR /app

# The pinned dependencies first, without this package, so a code change reuses this layer.
COPY requirements.txt ./
RUN grep -v '^-e ' requirements.txt > /tmp/pinned.txt \
    && pip install -r /tmp/pinned.txt \
    && rm /tmp/pinned.txt

COPY pyproject.toml ./
COPY src ./src
COPY config ./config
COPY prompts ./prompts
COPY datasets ./datasets
RUN pip install --no-deps -e .

# The commit the image was built from: a sim records it (there is no git in the image).
ARG CODE_VERSION=unknown
ENV CODE_VERSION=${CODE_VERSION}

# Runs as a plain user; logs/ is the one folder the code writes to.
RUN useradd --create-home --uid 10001 jev \
    && mkdir logs \
    && chown jev logs
USER jev

# Each piece names its own command; with none, the image lists the commands.
CMD ["python", "-c", "print('python -m jev_trader.memory serve | jev_trader.api serve | jev_trader.sim resume <id> | jev_trader.dataset build <file>')"]
