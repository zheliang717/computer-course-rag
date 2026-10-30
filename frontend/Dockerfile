FROM python:3.12-slim

WORKDIR /web
ARG WEB_DIST=dist
COPY ${WEB_DIST} ./dist
COPY server.py ./server.py
EXPOSE 80
CMD ["python", "server.py"]
