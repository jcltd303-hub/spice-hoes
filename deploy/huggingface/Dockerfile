FROM node:22-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends     python3 python3-pip ffmpeg git     && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY package*.json ./
RUN npm install --no-audit --no-fund

COPY requirements.txt ./
RUN pip3 install --break-system-packages -r requirements.txt

COPY . .
RUN npm run build

ENV NODE_ENV=production
ENV PORT=7860
EXPOSE 7860

CMD ["npm", "start"]
