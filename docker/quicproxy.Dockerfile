FROM rust:1-bookworm AS builder

ARG QUICPROXY_REPOSITORY=https://github.com/RealBikiniBottom/QuicProxy.git
ARG QUICPROXY_REF=master
RUN apt-get update \
    && apt-get install --yes --no-install-recommends clang cmake git pkg-config \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch "${QUICPROXY_REF}" "${QUICPROXY_REPOSITORY}" /src
WORKDIR /src
RUN cargo build --release --locked --no-default-features --features quinn

FROM debian:bookworm-slim
RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /src/target/release/quicproxy /usr/local/bin/quicproxy
ENTRYPOINT ["/usr/local/bin/quicproxy"]

