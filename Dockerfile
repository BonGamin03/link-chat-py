FROM python:3.11-slim
WORKDIR /app
COPY link_chat.py /app/link_chat.py
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/link_chat.py /app/entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]
