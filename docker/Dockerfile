# =============================================================================
# Dockerfile (제공된 Go 바이너리 컨테이너화용)
#   - binary 는 x86 AL2023, go1.22.2 linux/amd64 에서 빌드됨
#   - 바이너리 파일명(user/product/stress)을 빌드 ARG 로 전달
#   - 빌드 컨텍스트 = docker/ 디렉토리 (바이너리들이 위치한 곳)
#   - 사용 예:
#       docker build --platform linux/amd64 --build-arg APP_BINARY=user \
#         -t <ecr-url>/apdev/user:latest -f docker/Dockerfile docker
# =============================================================================
FROM public.ecr.aws/amazonlinux/amazonlinux:2023

WORKDIR /app

# 빌드할 앱 바이너리 파일명 (user / product / stress)
ARG APP_BINARY

# 컨텍스트(docker/)의 해당 바이너리를 /app/app 으로 복사
COPY ./${APP_BINARY} /app/app
RUN chmod +x /app/app

EXPOSE 8080

# 앱은 TCP/8080 바인딩, stdout/stderr 로 access log 출력
ENTRYPOINT ["/app/app"]
