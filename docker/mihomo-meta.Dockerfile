FROM golang:1.26-alpine AS builder

ARG MIHOMO_REPOSITORY=https://github.com/MetaCubeX/mihomo.git
ARG MIHOMO_REF=Meta
RUN apk add --no-cache git
RUN git clone --depth 1 --branch "${MIHOMO_REF}" "${MIHOMO_REPOSITORY}" /src
WORKDIR /src
RUN CGO_ENABLED=0 go build \
    -tags with_gvisor \
    -trimpath \
    -ldflags '-w -s -buildid=' \
    -o /usr/local/bin/mihomo .

FROM alpine:latest
RUN apk add --no-cache ca-certificates tzdata
COPY --from=builder /usr/local/bin/mihomo /usr/local/bin/mihomo
ENTRYPOINT ["/usr/local/bin/mihomo"]
