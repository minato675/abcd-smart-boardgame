# 빌드 스테이지
FROM node:24.18.0-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .

# .env.production 에 없는 값(ElevenLabs 키)을 Jenkins credential 로 주입한다.
# Vite 는 process.env 값을 .env 파일보다 우선하므로, ENV 로 깔아 두면 build 시 반영된다.
ARG VITE_ELEVENLABS_VOICE_ID
ARG VITE_ELEVENLABS_API_KEY
ENV VITE_ELEVENLABS_VOICE_ID=$VITE_ELEVENLABS_VOICE_ID
ENV VITE_ELEVENLABS_API_KEY=$VITE_ELEVENLABS_API_KEY

RUN npm run build

# 실행 스테이지
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html

# 프로젝트 내의 default.conf를 컨테이너 내부로 복사 (기존 sed 구문 대체)
COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 8333
CMD ["nginx", "-g", "daemon off;"]