FROM alpine:latest AS downloader

ARG TARGETARCH
RUN apk add --no-cache ca-certificates curl
RUN build_arch="${TARGETARCH:-$(apk --print-arch)}" \
    && case "${build_arch}" in \
      amd64|x86_64) release_arch=x86_64 ;; \
      arm64|aarch64) release_arch=aarch64 ;; \
      *) echo "unsupported architecture: ${build_arch}" >&2; exit 1 ;; \
    esac \
    && curl --fail --location --retry 3 \
      --output /usr/local/bin/clash-rs \
      "https://github.com/Watfaq/clash-rs/releases/latest/download/clash-rs-${release_arch}-unknown-linux-musl" \
    && chmod 0755 /usr/local/bin/clash-rs

FROM alpine:latest
RUN apk add --no-cache ca-certificates tzdata
COPY --from=downloader /usr/local/bin/clash-rs /usr/local/bin/clash-rs
ENTRYPOINT ["/usr/local/bin/clash-rs"]
