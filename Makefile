# 변수
DOCKER_COMPOSE=docker-compose
COMPOSE_FILE=docker-compose.yaml
API_DIR=api
NODE_DIR=node

FASTAPI_IMAGE=seoyoung1024/speech-feedback-service-fastapi:latest
NODE_IMAGE=seoyoung1024/speech-feedback-service-node:latest

.PHONY: help build push up down logs clean

help:
	@echo "make build    # 모든 도커 이미지 빌드"
	@echo "make push     # 모든 도커 이미지 푸시"
	@echo "make up       # docker-compose up -d"
	@echo "make down     # docker-compose down"
	@echo "make logs     # docker-compose logs -f"
	@echo "make clean    # 도커 이미지/컨테이너 정리"

build:
	docker build -t $(FASTAPI_IMAGE) $(API_DIR)
	docker build -t $(NODE_IMAGE) $(NODE_DIR)

push:
	docker push $(FASTAPI_IMAGE)
	docker push $(NODE_IMAGE)

up:
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) up -d --build

down:
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) down

logs:
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) logs -f

clean:
	docker system prune -f