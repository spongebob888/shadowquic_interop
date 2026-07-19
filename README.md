# shadowquic_interop

`shadowquic_interop` runs a client/server compatibility matrix for the
[ShadowQUIC protocol](https://github.com/spongebob888/shadowquic), stores each
run as versioned JSON, and builds a static report for GitHub Pages.

The runnable matrix currently contains:

| Implementation | Client | Server | Image source |
| --- | :---: | :---: | --- |
| shadowquic | yes | yes | `ghcr.io/spongebob888/shadowquic:latest` |
| QuicProxy | yes | yes | Built from upstream `master` |
| mihomo Meta | yes | yes | Built from upstream `Meta` |

Mihomo is built explicitly from its
[`Meta` branch](https://github.com/MetaCubeX/mihomo/tree/Meta). That branch
contains the ShadowQUIC outbound and listener implementations; the `main`
branch does not currently expose them.

The specification's ProxyPen link contains a username typo. The runner builds
the active project at
[`spongebob888/proxypen`](https://github.com/spongebob888/proxypen).

## How it works

Each runnable client/server pair gets a private Docker bridge network:

1. The server starts with a generated ShadowQUIC/JLS configuration.
2. The client starts with a generated configuration and a SOCKS5 listener.
3. ProxyPen requests the public target over HTTP/2 and HTTP/3 through SOCKS5.
4. The runner records protocol timings, endpoint output, and a cell status.
5. Containers and the network are removed even when setup or probing fails.

`pass`, `fail`, `error`, and `unsupported` are distinct. A protocol failure
means ProxyPen reached the test path and rejected the result. An error means
the harness, image, or endpoint failed before it could produce a valid probe.
`unsupported` remains part of the schema for future capability differences.

## Requirements

- Python 3.11 or newer
- Docker Engine with Linux containers
- Internet access for image builds and the public test target

The Python package has no third-party runtime dependencies.

## Run locally

```bash
python3 -m unittest discover -s tests -v
python3 -m shadowquic_interop run
python3 -m shadowquic_interop generate
python3 -m http.server 8000 --directory site
```

Open `http://localhost:8000`. Generated endpoint logs are under `work/`, and
machine-readable results are under `results/`.

Useful selections:

```bash
# One pair, both probes, without rebuilding local images
python3 -m shadowquic_interop run \
  --clients quicproxy \
  --servers shadowquic \
  --no-build

# Only HTTP/3 with a different public target
python3 -m shadowquic_interop run \
  --protocols http3 \
  --target https://cloudflare.com/

# Return nonzero when a runnable matrix cell fails
python3 -m shadowquic_interop run --fail-on-test-failure
```

Run `python3 -m shadowquic_interop implementations` for the endpoint registry
and `python3 -m shadowquic_interop run --help` for every option.

## Result data

Every run creates `results/<UTC timestamp>.json` and refreshes
`results/latest.json`. Schema version 1 includes:

- run timestamps, target, protocols, and runner version
- endpoint source, image, and client/server capabilities
- one result per matrix cell
- one HTTP result per requested protocol, including ProxyPen metrics
- an optional error message and endpoint log directory

The report generator reads every valid JSON file in `results/`, de-duplicates
run IDs, and embeds the archive into `site/index.html`. Published URLs accept
`?run=<run-id>&protocol=http3`.

## GitHub automation

[`ci.yml`](.github/workflows/ci.yml) validates every push and pull request.
[`interop.yml`](.github/workflows/interop.yml) runs daily at 16:30 UTC and can
also be started manually. It builds current upstream images, executes the
matrix, uploads diagnostic logs, commits the new JSON result to the default
branch, and deploys the complete archive through GitHub Pages.

In repository settings, set **Pages > Build and deployment > Source** to
**GitHub Actions**. The workflow needs the included `contents`, `pages`, and
`id-token` permissions; organization or branch rules may still need to allow
the scheduled result commit.

## Endpoint maintenance

Endpoint metadata and config renderers live in
`shadowquic_interop/adapters.py`. Mihomo Meta, QuicProxy, and ProxyPen build
definitions live under `docker/`. Their default refs intentionally track
upstream for daily compatibility testing; pass Docker build arguments such as
`--build-arg MIHOMO_REF=<tag-or-branch>` or
`--build-arg QUICPROXY_REF=<tag-or-branch>` when reproducing an older build.
