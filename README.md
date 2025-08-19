# Python Docker Downloader

[![Python Version](https://img.shields.io/badge/python-3.6+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen.svg)](#)
[![GitHub Release](https://img.shields.io/github/v/release/ZacharyArthur/pythonDockerDownloader?include_prereleases)](https://github.com/ZacharyArthur/pythonDockerDownloader/releases)
[![GitHub Issues](https://img.shields.io/github/issues/ZacharyArthur/pythonDockerDownloader)](https://github.com/ZacharyArthur/pythonDockerDownloader/issues)
[![GitHub Stars](https://img.shields.io/github/stars/ZacharyArthur/pythonDockerDownloader)](https://github.com/ZacharyArthur/pythonDockerDownloader/stargazers)
[![Code Style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

A pure Python CLI tool for downloading Docker images without Docker itself. Single-file architecture with zero runtime dependencies, designed for air-gapped environments, corporate networks with proxy requirements, and seamless image transfers between systems.

## Features

- **Zero Dependencies** - Uses only Python 3.6+ standard library
- **Corporate Proxy Support** - Full HTTP/HTTPS proxy support with authentication
- **Multi-Architecture** - Pull images for different architectures (amd64, arm64, etc.)
- **Progress Tracking** - Real-time download progress with Unicode progress bars
- **Format Support** - Handles Docker v2, OCI, and multi-architecture manifests
- **CDN Optimization** - Intelligent proxy bypass for faster CDN downloads

## Installation

### Option 1: Direct Download
```bash
# Download the script
curl -O https://raw.githubusercontent.com/ZacharyArthur/pythonDockerDownloader/main/docker_pull.py
chmod +x docker_pull.py
```

### Option 2: Git Clone
```bash
git clone https://github.com/ZacharyArthur/pythonDockerDownloader.git
cd pythonDockerDownloader
```

### Requirements
- **Python 3.6 or later** - No additional dependencies required

## Quick Start

```bash
# Pull an image
python3 docker_pull.py ubuntu:latest

# Pull with custom output name
python3 docker_pull.py nginx:alpine -o my-nginx.tar

# Load into Docker (if Docker is available)
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

## Technical Details

### Architecture
- **Single-file design** - Complete functionality in `docker_pull.py`
- **Zero runtime dependencies** - Uses only Python 3.6+ standard library
- **Cross-platform compatibility** - Works on Linux, macOS, and Windows

### Supported Image Formats
- Docker Registry API v2
- OCI (Open Container Initiative) images
- Multi-architecture manifests
- Private repository authentication

### Code Quality
- **PEP 8 compliant** - Formatted with Ruff
- **Type hints** - Enhanced code clarity and IDE support
- **Comprehensive logging** - Debug and verbose modes available
- **Error handling** - Graceful failure with helpful messages

## Development

### Running Tests
```bash
# Run the test suite
python3 test_docker_pull.py

# Syntax validation
python3 -m py_compile docker_pull.py
```

### Code Quality Checks
```bash
# Install development tools (optional)
pip install ruff vulture

# Linting and formatting
ruff check .
ruff format .

# Dead code detection
vulture .
```

## Requirements

- **Python 3.6 or later**
- **No external dependencies** - uses only standard library

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Contributing

This project maintains a single-file, zero-dependency architecture for maximum portability. When contributing:

- Maintain Python 3.6+ compatibility
- Avoid external dependencies
- Follow PEP 8 style guidelines
- Include tests for new functionality
- Preserve the single-file design