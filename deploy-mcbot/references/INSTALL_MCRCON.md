# Installing mcrcon

mcrcon is a CLI tool for sending RCON commands to Minecraft servers.

## Build from source (recommended)

```bash
git clone https://github.com/Tiiffi/mcrcon.git
cd mcrcon
gcc -o mcrcon mcrcon.c
sudo cp mcrcon /usr/local/bin/
```

## Verify installation

```bash
mcrcon --help
```

## Test connection

```bash
mcrcon -H localhost -P 25575 -p your-password "list"
```

Should return the list of online players.
