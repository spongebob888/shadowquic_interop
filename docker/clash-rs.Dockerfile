FROM rust:1-bookworm AS builder

ARG CLASH_RS_REPOSITORY=https://github.com/ibigbug/clash-rs.git
ARG CLASH_RS_REF=master
ARG CARGO_BUILD_JOBS=4
RUN apt-get update \
    && apt-get install --yes --no-install-recommends clang cmake git libclang-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch "${CLASH_RS_REF}" "${CLASH_RS_REPOSITORY}" /src
WORKDIR /src
RUN CLASH_GIT_REF="refs/heads/${CLASH_RS_REF}" \
    CLASH_GIT_SHA="$(git rev-parse HEAD)" \
    cargo build --release --locked --package clash-rs \
    --no-default-features --features standard,aws-lc-rs

FROM debian:bookworm-slim
RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /src/target/release/clash-rs /usr/local/bin/clash-rs
ENTRYPOINT ["/usr/local/bin/clash-rs"]
