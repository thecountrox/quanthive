FROM python:3-alpine
WORKDIR /app
COPY ./app /app
RUN pip install -r requirements.txt
EXPOSE 8000
CMD uvicorn main:app --host 0.0.0.0
