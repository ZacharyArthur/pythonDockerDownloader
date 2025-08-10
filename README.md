# Docker Image Puller

A pure Python CLI tool for pulling and saving Docker images from Docker Hub without requiring Docker itself. Perfect for air-gapped environments, corporate networks with proxies, and situations where you need to transfer images between systems.

## Features

- **Pure Python** - No Docker installation required
- **Corporate Proxy Support** - Full HTTP/HTTPS proxy support with authentication
- **Multi-Architecture** - Pull images for different architectures (amd64, arm64, etc.)
- **SSL/TLS Configuration** - Option to disable SSL verification for corporate environments
- **Progress Tracking** - Real-time download progress for large images
- **OCI and Docker v2 Support** - Handles both modern and legacy image formats
- **CDN Optimization** - Automatically bypasses proxies for CDN downloads when beneficial

## Quick Start

```bash
# Pull latest Ubuntu image
python docker_pull.py ubuntu:latest

# Pull specific version and save with custom name
python docker_pull.py ubuntu:20.04 --output ubuntu-focal.tar

# Pull ARM64 image
python docker_pull.py ubuntu:latest --arch arm64

# Load the image in Docker
docker load -i ubuntu_latest.tar
```

## Installation

No installation required! Just download `docker_pull.py` and run it with Python 3.6+.

```bash
# Make the script executable (Linux/macOS)
chmod +x docker_pull.py

# Run directly
./docker_pull.py ubuntu:latest
```

## Usage

### Basic Usage

```bash
python docker_pull.py <image:tag> [options]
```

### Command Line Options

- `image` - Docker image to pull (e.g., ubuntu:20.04, nginx:latest)
- `-o, --output` - Output tar filename (default: imagename_tag.tar)
- `-t, --token` - Docker Hub authentication token (for private repositories)
- `--arch, --architecture` - Target architecture (default: amd64)
  - Choices: amd64, arm64, arm, 386, ppc64le, s390x, mips64le, riscv64
- `--os` - Target operating system (default: linux)
  - Choices: linux, windows

### Proxy Configuration

The tool supports multiple ways to configure proxy settings:

#### Command Line Arguments
```bash
# Simple proxy for both HTTP and HTTPS
python docker_pull.py ubuntu:latest --proxy http://proxy.company.com:8080

# Separate HTTP/HTTPS proxies
python docker_pull.py ubuntu:latest --http-proxy http://proxy.company.com:8080 --https-proxy https://proxy.company.com:8443

# Proxy with authentication
python docker_pull.py ubuntu:latest --proxy http://proxy.company.com:8080 --proxy-auth username:password

# Bypass proxy for certain hosts
python docker_pull.py ubuntu:latest --proxy http://proxy.company.com:8080 --no-proxy localhost,127.0.0.1,.local

# Disable SSL verification (for corporate proxies)
python docker_pull.py ubuntu:latest --proxy https://proxy.company.com:8080 --insecure
```

#### Environment Variables
```bash
export HTTP_PROXY=http://proxy.company.com:8080
export HTTPS_PROXY=http://proxy.company.com:8080
export NO_PROXY=localhost,127.0.0.1,.local
python docker_pull.py ubuntu:latest
```

### Advanced Examples

```bash
# Pull multi-architecture image (automatically selects best match)
python docker_pull.py --arch arm64 alpine:latest

# Pull Windows container image
python docker_pull.py --os windows --arch amd64 mcr.microsoft.com/windows/nanoserver:ltsc2022

# Debug mode for troubleshooting
python docker_pull.py ubuntu:latest --debug

# Corporate environment with proxy and custom SSL
python docker_pull.py nginx:latest \
  --proxy https://corporate-proxy.company.com:8080 \
  --proxy-auth myuser:mypass \
  --no-proxy registry-1.docker.io \
  --insecure
```

## Supported Image Formats

- **Docker Registry v2** - Modern Docker images
- **OCI (Open Container Initiative)** - Cloud-native container images  
- **Multi-architecture manifests** - Automatically selects correct architecture
- **Schema v1** - Legacy Docker images (limited support)

## How It Works

1. **Authentication** - Obtains anonymous or authenticated token from Docker Hub
2. **Manifest Retrieval** - Downloads image manifest containing layer information
3. **Layer Download** - Downloads all image layers with progress tracking
4. **Archive Creation** - Packages layers into Docker-compatible tar format
5. **Proxy Optimization** - Intelligently bypasses proxies for CDN downloads

## Corporate Environment Setup

For corporate networks with strict proxy requirements:

1. **Configure proxy settings** using environment variables or command line
2. **Add authentication** if your proxy requires it
3. **Disable SSL verification** if using self-signed certificates
4. **Whitelist Docker Hub** in your proxy if possible for better performance

```bash
# Example corporate setup
export HTTPS_PROXY=https://proxy.corp.com:8080
export NO_PROXY=localhost,127.0.0.1,*.corp.com
python docker_pull.py --insecure ubuntu:latest
```

## Troubleshooting

### Common Issues

**Connection errors behind proxy:**
- Verify proxy URL and credentials
- Use `--debug` flag to see detailed connection information
- Try `--insecure` flag for self-signed certificates

**Architecture not found:**
- Check available architectures with `--debug`
- Some images may not support all architectures

**Download failures:**
- Large images may timeout - the tool will retry automatically
- Check network connectivity and proxy settings
- Use `--debug` for detailed error information

### Debug Mode

Enable debug mode to see detailed information about requests, redirects, and proxy usage:

```bash
python docker_pull.py ubuntu:latest --debug
```

## Requirements

- Python 3.6 or later
- Standard library modules only (no external dependencies)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contributing

This is a standalone script designed for maximum portability. Keep dependencies minimal and maintain Python 3.6+ compatibility.