---
status: accepted
---

# Aliyun mirrors for pnpm, uv, and apt

MedicalRAG development, CI, and image builds use Aliyun package mirrors to keep dependency fetching reliable on machines with mainland-China network conditions.

- **pnpm** registry points at `https://registry.npmmirror.com`.
- **uv / PyPI** index points at `https://mirrors.aliyun.com/pypi/simple/` (for example through `UV_DEFAULT_INDEX` or the equivalent uv configuration).
- **apt** sources in Debian/Ubuntu Docker base images use the Aliyun mirror (`mirrors.aliyun.com`) where image builds need it.

Mirror configuration is bootstrap and network configuration only. Lockfiles and integrity hashes remain the canonical record of dependency identity and versions; a mirror never changes a package's identity, and a mirror outage must not silently bypass the lockfile. The Aliyun mirror choice therefore does not alter any dependency decision recorded in this plan.

## Consequences

- The project keeps a `.npmrc` (pnpm registry) and uv index configuration for development and CI.
- Dockerfiles for Python and Node images apply an apt sources-list override to the Aliyun mirror where the build environment requires it.
- Mirror settings are documented in the monorepo toolchain and Compose topology tickets; production image builds are reproducible from the lockfile regardless of which mirror serves the artifacts.
- The mirror decision is orthogonal to the arq and Python 3.14 decisions: it only changes where packages are fetched, never what is fetched.
