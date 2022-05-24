FROM node:16-alpine

ARG REMOTE_ADDRESS="127.0.0.1"

# Create app directory
WORKDIR /usr/src/app

RUN apk update
RUN apk add git
RUN git clone https://github.com/running-coder/nanolooker.git
WORKDIR /usr/src/app/nanolooker


RUN sed -i 's/localhost:27017/nl_nanolooker_mongo:27017/g' ./server/constants.js
#COPY test.txt .env
# Install app dependencies
# A wildcard is used to ensure both package.json AND package-lock.json are copied
# where available (npm@5+)
RUN npm install
RUN npm run build
#replace nanolooker websocket with genesis websocket (not properly configurable via env variables)
RUN cd dist && sed -i "s/wss:\/\/www.nanolooker.com\/ws/ws:\/\/${REMOTE_ADDRESS}:47000/g" $(grep -rl wss://www.nanolooker.com/ws ./)


# Bundle app source
COPY . .

EXPOSE 3010
CMD [ "npm", "run", "start:server" ] 
#, "node", "server/server.js" ]