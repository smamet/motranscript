# Agent notes

For first-time install or when the local stack will not start, read and follow [`.cursor/skills/setup/SKILL.md`](.cursor/skills/setup/SKILL.md).

Quick path for humans and agents:

```bash
cp .env.example .env   # if needed
./sail up
```

Then open http://localhost:8010 — default admin is `admin@example.com` / `admin` (change immediately).

Do not SSH to remote hosts, import production data, or commit secrets.
