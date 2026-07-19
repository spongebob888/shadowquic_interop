FROM rust:1-bookworm AS builder

ARG PROXYPEN_REPOSITORY=https://github.com/spongebob888/proxypen.git
ARG PROXYPEN_REF=main
RUN git clone --depth 1 --branch "${PROXYPEN_REF}" "${PROXYPEN_REPOSITORY}" /src
WORKDIR /src
RUN cargo build --release --locked

FROM debian:bookworm-slim
RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /src/target/release/proxypen /usr/local/bin/proxypen
ENTRYPOINT ["/usr/local/bin/proxypen"]

