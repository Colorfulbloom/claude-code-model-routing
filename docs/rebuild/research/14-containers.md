# Scout report: containerized dev setup (2026-11-08), saved by main session

Machine: macOS 27.2 arm64. node on PATH v20.19.6 via nvm (~/.nvm). Second node /opt/homebrew/bin/node v26.12.0. docker client 29.4.3 at /usr/local/bin/docker, Docker.app installed (daemon not checked). No Podman, Colima, OrbStack, devcontainer CLI, fnm, Volta, mise. uv at ~/anaconda3/bin/uv.

- Docker Desktop free for companies under 250 employees AND under $10M revenue, and non-commercial OSS. https://www.docker.com/pricing/faq/
- Bind mounts "have some performance overhead on Windows and macOS"; named volumes improve it. https://code.visualstudio.com/docs/devcontainers/containers
- OrbStack free for personal non-commercial use, $8/user/month for business. https://orbstack.dev/pricing
- Colima MIT, brew install. https://github.com/abiosoft/colima
- Apple container: "supported on macOS 26", Apple silicon only, Apache-2.0, under active development; macOS 27 support UNVERIFIED. https://github.com/apple/container
- Dev container Node images mcr.microsoft.com/devcontainers/javascript-node tags 22, 24, 26; "pin the image". https://github.com/devcontainers/images/tree/main/src/javascript-node
- Playwright Docker images v1.64.1; "always pin your Docker image"; use --init and --ipc=host. https://playwright.dev/docs/docker
- Vite server.host default localhost; 0.0.0.0 to listen on all; usePolling "leads to high CPU utilization". https://vite.dev/config/server-options
- Bind mounts give "write access to files on the host by default"; use ro. https://docs.docker.com/engine/storage/bind-mounts/
- Inference: keep the real server (reads/writes ~/.claude) on the host; container fits Vite build, Vitest, Playwright.
- Node managers: fnm https://github.com/Schniz/fnm ; mise https://mise.jdx.dev/lang/node.html ; Volta https://docs.volta.sh/reference/pin ; uv does not manage Node https://docs.astral.sh/uv/guides/install-python/
- Vitest "requires Vite >=v6.4.0 and Node >=v22.12.0". https://vitest.dev/guide/
- Recommendation: per-project Node pin now; Dev Container later for Playwright only if browser installs cause trouble. Alternative: full Dev Container.
