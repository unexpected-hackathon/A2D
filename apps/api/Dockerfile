FROM python:3.12.8-slim

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY a2d /srv/a2d
COPY fixtures /srv/fixtures

RUN useradd --system --uid 10001 a2d && mkdir /srv/data && chown a2d /srv/data
USER 10001

EXPOSE 8000
CMD ["uvicorn", "a2d.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
