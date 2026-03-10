ARG UID=1000
ARG GID=1000

FROM python:3.12-slim-bookworm

ARG UID
ARG GID

# Create a non-root user whose UID matches the host user
RUN groupadd -g "${GID}" appuser \
 && useradd  -u "${UID}" -g "${GID}" -m appuser

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements.txt

COPY affine_rpc/ ./affine_rpc/

USER appuser

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "-m", "affine_rpc.main"]
