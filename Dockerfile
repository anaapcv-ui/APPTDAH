FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY gastos_bot ./gastos_bot
CMD ["python", "-m", "gastos_bot"]
