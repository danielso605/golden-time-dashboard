# 우리 동네는 골든타임 안에 있을까? - Flask 대시보드 이미지
FROM python:3.11-slim

# 그래프 한글 폰트(나눔고딕) 설치
RUN apt-get update && apt-get install -y --no-install-recommends fonts-nanum \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /root/.cache/matplotlib

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000
# gunicorn: 실제 서비스용 웹 서버로 Flask 앱(app.py 의 app)을 실행
CMD ["gunicorn", "-b", "0.0.0.0:5000", "-w", "2", "--timeout", "120", "app:app"]
