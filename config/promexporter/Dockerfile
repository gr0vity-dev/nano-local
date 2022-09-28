FROM python:3.7-alpine

WORKDIR /
RUN apk update
RUN apk add git gcc musl-dev linux-headers
RUN git clone https://github.com/pwojcikdev/nano-prom-exporter.git app

WORKDIR /app
RUN pip install -r requirements.txt

ENTRYPOINT [ "python", "-m", "nano_prom_exporter" ]