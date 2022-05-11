FROM ubuntu:20.04

ARG DEBIAN_FRONTEND=noninteractive

RUN groupadd --gid 1000 nanocurrency && \
useradd --uid 1000 --gid nanocurrency --shell /bin/bash --create-home nanocurrency

USER nanocurrency
WORKDIR /home/nanocurrency

COPY nano_node /usr/bin/