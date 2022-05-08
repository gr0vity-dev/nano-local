#Forked from https://github.com/dsiganos/nano-workspace/blob/main/docker/Dockerfile
FROM ubuntu:20.04

ARG DEBIAN_FRONTEND=noninteractive
ARG TAG=develop

RUN apt-get update
RUN apt-get install -y wget make cmake git p7zip-full g++ qt5-default
RUN git clone https://github.com/dsiganos/nano-workspace.git 
RUN make -C nano-workspace git.clone.done NANO_BRANCH=$TAG
RUN make -C nano-workspace boost
RUN make -C nano-workspace