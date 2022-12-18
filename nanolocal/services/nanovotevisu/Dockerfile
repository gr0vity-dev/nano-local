FROM node:14-alpine as build
ARG ENVIRONMENT="live"
ARG REMOTE_ADDRESS="127.0.0.1"
ARG HOST_ACCOUNT="nano_1fzwxb8tkmrp8o66xz7tcx65rm57bxdmpitw39ecomiwpjh89zxj33juzt6p"

WORKDIR /usr/local/app
RUN apk update
RUN apk add git
RUN git clone https://github.com/numsu/nano-vote-visualizer.git
WORKDIR /usr/local/app/nano-vote-visualizer
COPY ./services/nanovotevisu/environment.prod.ts ./src/environments/environment.prod.ts
RUN sed -i "s/localhost/${REMOTE_ADDRESS}/g" ./src/environments/environment.prod.ts
RUN sed -i "s/HOST_ACCOUNT/${HOST_ACCOUNT}/g" ./src/environments/environment.prod.ts

RUN npm install
RUN npm run build:${ENVIRONMENT}

FROM nginx:alpine
COPY --from=build /usr/local/app/nano-vote-visualizer/dist/nano-vote-visualizer /usr/share/nginx/html
EXPOSE 80