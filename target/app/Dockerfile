# 빌드 컨텍스트는 target/ (compose.yml 기준). planted/를 함께 담기 위해서다.
FROM python:3.12.8-slim

WORKDIR /srv
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 방치된 결함 파일(#8, #9). backup.zip은 빌드할 때 planted/에서 만든다.
COPY planted /srv/planted
RUN cd /srv/planted && python -c "import zipfile; z = zipfile.ZipFile('backup.zip', 'w', zipfile.ZIP_DEFLATED); z.write('db.sql'); z.write('.env', 'config/.env'); z.close()"

COPY app/jobnest /srv/jobnest

# 공유 볼륨 /state를 이 사용자 소유로 시작하게 한다(init이 영역 파일·인증서를 쓴다).
RUN useradd --system --uid 10001 jobnest && mkdir /state && chown jobnest /state
USER 10001

EXPOSE 8000
CMD ["uvicorn", "jobnest.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*", "--no-server-header"]
