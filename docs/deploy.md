# Production deploy (VPS + RunPod)

Who talks to whom (VPS, Serverless, GHCR, Hugging Face, training pod): [architecture.md](architecture.md). The VPS does **not** trigger the GPU image rebuild.

This guide uses placeholders. Replace `YOUR_DOMAIN`, `YOUR_VPS_USER@YOUR_VPS_HOST`, and `YOUR_GITHUB_USER` with your own values. Do not commit real hosts, SSH targets, or cookies.

## VPS

1. Unlock first login if the cloud provider password is expired (provider KVM / console).

2. Harden + Docker:

```bash
# from laptop after cloning
scp -r deploy YOUR_VPS_USER@YOUR_VPS_HOST:~/
ssh YOUR_VPS_USER@YOUR_VPS_HOST 'bash ~/deploy/harden.sh'
# log out/in for docker group
```

3. DNS: **A** record for your subdomain → the VPS public IP. Keep the proxy off until TLS is issued.

4. TLS:

```bash
DOMAIN=asr.example.com CERTBOT_EMAIL=you@example.com bash deploy/setup-nginx-certbot.sh
```

Then enable your CDN / proxy with SSL **Full (strict)** if you use one.

5. Deploy key (if the GitHub repo is private):

```bash
ssh-keygen -t ed25519 -f ~/.ssh/motranscript_deploy -N ""
# Add ~/.ssh/motranscript_deploy.pub as a read-only deploy key on the repo
```

6. App:

```bash
sudo mkdir -p /opt/motranscript && sudo chown "$USER:$USER" /opt/motranscript
GIT_SSH_COMMAND='ssh -i ~/.ssh/motranscript_deploy -o IdentitiesOnly=yes' \
  git clone git@github.com:YOUR_GITHUB_USER/motranscript.git /opt/motranscript
cd /opt/motranscript
cp .env.production.example .env
# edit .env: MYSQL_*, SECRET_KEY, HF_TOKEN, RUNPOD_*, PUBLIC_BASE_URL
bash deploy/deploy.sh
```

## RunPod Serverless (ASR)

Three different accounts, three roles:

| Where | What it stores |
| --- | --- |
| **GitHub** (`YOUR_GITHUB_USER/motranscript`) | Source code |
| **GHCR** (`ghcr.io/YOUR_GITHUB_USER/motranscript-asr`) | The **built GPU Docker image** (OS + Python + CUDA + our code). Not docker-compose. |
| **RunPod** | A Serverless **endpoint** that *pulls* that image onto a GPU when a job arrives |
| **Hugging Face** | ASR / diarization **models** downloaded at worker start (`HF_TOKEN`) |
| **VPS `.env`** | `RUNPOD_API_KEY` + `RUNPOD_ENDPOINT_ID` so the worker can call the endpoint |

`YOUR_REGISTRY` = `ghcr.io/YOUR_GITHUB_USER`. It is **not** a RunPod username and **not** a Hugging Face username.

### 1. Publish the image to GHCR

Do this on GitHub Actions (linux/amd64). A local `docker build` on a Mac ARM would emulate x86 and is slow/fragile for CUDA images.

```bash
# from the laptop, after the workflow file is on main
gh workflow run runpod-asr-image.yml -f tag=v4
gh run watch
```

The workflow builds `Dockerfile.runpod` and pushes:

- `ghcr.io/YOUR_GITHUB_USER/motranscript-asr:v4`
- `ghcr.io/YOUR_GITHUB_USER/motranscript-asr:<git-sha>`

Use an explicit tag (`v1`, `v2`, …), never `latest`.

If the package is private, RunPod needs a GitHub token that can **read** packages:

1. GitHub → Settings → Developer settings → [Personal access tokens](https://github.com/settings/tokens) → classic token
2. Scope: `read:packages` (and `write:packages` if you also push from your laptop)
3. Copy the token once

```bash
# laptop: optional, only if you push the image yourself
echo YOUR_GITHUB_PACKAGES_TOKEN | docker login ghcr.io -u YOUR_GITHUB_USER --password-stdin
```

### 2. Let RunPod pull the image

In [RunPod Console](https://console.runpod.io) → Settings → **Container Registry Auth**, or via API:

- name: `ghcr`
- username: `YOUR_GITHUB_USER`
- password: the GitHub token with `read:packages` (skip if the package is public)

Keep that token on RunPod only. The VPS does **not** pull the image, so do not put a GHCR token in `/opt/motranscript/.env`.

### 3. Create the Serverless endpoint

- Image: `ghcr.io/YOUR_GITHUB_USER/motranscript-asr:v4`
- Registry auth: as configured above
- GPU pool: `AMPERE_24` (A5000 / L4). Exclude Blackwell MIG 24GB — torch 2.4/cu124 cannot start on it (workers crash-loop, jobs stay `IN_QUEUE` until timeout).
- min workers **0**, max **1** (scale to zero when idle)
- idle timeout **15 min**
- execution timeout **40 min**
- FlashBoot **on**
- container disk **50 GB** (model downloads on cold start)
- env on the worker: `HF_TOKEN`, `WHISPER_MODEL=Systran/faster-whisper-large-v3`, `ENABLE_DIARIZATION=true`

### 4. Point the VPS at the endpoint

Only these RunPod values belong in `/opt/motranscript/.env` (plus `HF_TOKEN` already used for models):

```
INFERENCE_BACKEND=runpod
PUBLIC_BASE_URL=https://asr.example.com
RUNPOD_API_KEY=          # RunPod → Settings → API Keys
RUNPOD_ENDPOINT_ID=      # from the endpoint page / URL
```

Then:

```bash
cd /opt/motranscript && docker compose -f docker-compose.prod.yml up -d --force-recreate api worker
```

The worker signs `/api/internal/audio/{id}` so RunPod can download the WAV.

## YouTube cookies (optional, VPS bot check)

Datacenter IPs are often blocked (`Sign in to confirm you're not a bot`). yt-dlp can use a Netscape `cookies.txt` from a logged-in YouTube session.

Export cookies on your laptop only, copy them to the VPS under `/opt/motranscript/secrets/`, set `YT_DLP_COOKIES=/secrets/youtube.cookies.txt`, and recreate the api/worker containers. Use a dedicated Google account. Cookies expire — re-export when downloads fail again. Never commit `secrets/`.

### Rebuild after a handler / Dockerfile change

```bash
gh workflow run runpod-asr-image.yml -f tag=v4
# then update the RunPod endpoint imageName to :v4
```

## Activate a published model

After LoRA publish, on Sources page: register HF CT2 repo → activate → restart worker (and rebuild/restart Serverless workers so they pick up env/`WHISPER_MODEL` / hub download).

See also [training.md](training.md).
