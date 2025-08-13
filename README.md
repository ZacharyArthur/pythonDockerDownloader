# Docker Image Puller

[![Python](https://img.shields.io/badge/python-3.6+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen.svg)](#)

A pure Python CLI tool for downloading Docker images from Docker Hub without requiring Docker itself. Perfect for air-gapped environments, corporate networks with proxies, and transferring images between systems.

## Features

- **Zero Dependencies** - Uses only Python 3.6+ standard library
- **Corporate Proxy Support** - Full HTTP/HTTPS proxy support with authentication
- **Multi-Architecture** - Pull images for different architectures (amd64, arm64, etc.)
- **Progress Tracking** - Real-time download progress with Unicode progress bars
- **Format Support** - Handles Docker v2, OCI, and multi-architecture manifests
- **CDN Optimization** - Intelligent proxy bypass for faster CDN downloads

## Quick Start

```bash
# Download the script
wget https://raw.githubusercontent.com/ZacharyArthur/pythonDockerDownloader/main/docker_pull.py
chmod +x docker_pull.py

# Pull an image
python3 docker_pull.py ubuntu:latest

# Load in Docker
docker load -i ubuntu_latest.tar
```

## Usage

### Basic Commands

```bash
# Pull latest image
python3 docker_pull.py ubuntu:latest

# Custom output name
python3 docker_pull.py nginx:alpine -o my-nginx.tar

# Different architecture
python3 docker_pull.py ubuntu:latest --arch arm64

# Private repository
python3 docker_pull.py private/image:tag --token YOUR_TOKEN
```

### Proxy Configuration

```bash
# Simple proxy setup
python3 docker_pull.py ubuntu:latest --proxy http://proxy.company.com:8080

# With authentication
python3 docker_pull.py ubuntu:latest \
  --proxy http://proxy.company.com:8080 \
  --proxy-auth username:password

# Environment variables
export HTTPS_PROXY=http://proxy.company.com:8080
export NO_PROXY=localhost,127.0.0.1,.local
python3 docker_pull.py ubuntu:latest

# Corporate environment (disable SSL verification)
python3 docker_pull.py ubuntu:latest --proxy https://proxy.corp.com:8080 --insecure
```

### Command Options

| Option | Description | Default |
|--------|-------------|---------|
| `-o, --output` | Output filename | `imagename_tag.tar` |
| `--arch` | Target architecture | `amd64` |
| `--os` | Target OS | `linux` |
| `-t, --token` | Authentication token | None |
| `--proxy` | Proxy URL | None |
| `--proxy-auth` | Proxy credentials | None |
| `--insecure` | Disable SSL verification | False |
| `--debug` | Enable debug output | False |
| `-v, --verbose` | Verbose logging | False |
| `-q, --quiet` | Quiet mode | False |

**Supported architectures:** amd64, arm64, arm, 386, ppc64le, s390x, mips64le, riscv64

## How It Works

1. **Authenticate** - Obtains token from Docker Hub registry
2. **Get Manifest** - Downloads image manifest and selects architecture
3. **Download Layers** - Streams all image layers with progress tracking
4. **Create Archive** - Packages into Docker-compatible tar format

**Supported Formats:** Docker Registry v2, OCI images, multi-architecture manifests

## Corporate Networks

For restrictive corporate environments:

```bash
# Typical corporate setup
export HTTPS_PROXY=https://proxy.corp.com:8080
export NO_PROXY=localhost,*.corp.com
python3 docker_pull.py --insecure ubuntu:latest
```

**Tips:**
- Use `--insecure` for self-signed proxy certificates
- Add Docker Hub to proxy whitelist for better performance
- Use `--debug` to troubleshoot connection issues

## Troubleshooting

**Proxy Issues:**
- Verify proxy URL and credentials with `--debug`
- Try `--insecure` for certificate problems
- Check `NO_PROXY` settings for Docker Hub

**Architecture Errors:**
- Use `--debug` to see available platforms
- Some images don't support all architectures

**Download Failures:**
- Large images may timeout and retry automatically
- Check network connectivity and proxy configuration

## Requirements

- **Python 3.6 or later**
- **No external dependencies** - uses only standard library

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Contributing

This is designed as a single-file, zero-dependency tool. Contributions should maintain Python 3.6+ compatibility and avoid external dependencies.