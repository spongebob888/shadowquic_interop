FROM rust:1-bookworm AS builder

ARG SHADOWQUIC_REPOSITORY=https://github.com/spongebob888/shadowquic.git
ARG SHADOWQUIC_REF=main
RUN apt-get update \
    && apt-get install --yes --no-install-recommends clang cmake git pkg-config \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch "${SHADOWQUIC_REF}" "${SHADOWQUIC_REPOSITORY}" /src
WORKDIR /src
RUN cargo build --release --locked --package shadowquic

FROM debian:bookworm-slim
RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /src/target/release/shadowquic /usr/local/bin/shadowquic
ENTRYPOINT ["/usr/local/bin/shadowquic"]
