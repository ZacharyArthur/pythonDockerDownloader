"""
Docker Image Puller - Pure Python CLI for pulling and saving Docker images

A pure Python tool for downloading Docker images from Docker Hub without requiring
Docker itself. Perfect for air-gapped environments, corporate networks with proxies,
and transferring images between systems.

Features:
- No Docker installation required (pure Python, standard library only)
- Full corporate proxy support with authentication
- Multi-architecture support (amd64, arm64, etc.)
- SSL/TLS configuration options
- Real-time download progress tracking
- Outputs Docker-compatible tar files

Usage:
    python docker_pull.py <image:tag> [options]

Examples:
    python docker_pull.py ubuntu:latest
    python docker_pull.py nginx:alpine --output my-nginx.tar
    python docker_pull.py --arch arm64 alpine:latest
    python docker_pull.py ubuntu:20.04 --proxy http://proxy:8080 --proxy-auth user:pass

Requirements:
- Python 3.6 or later
- Internet connection (or corporate network with proxy)

Copyright (c) 2025 ZacharyArthur
Licensed under the MIT License - see LICENSE file for details
"""

import argparse
import gzip
import json
import logging
import os
import re
import shutil
import signal
import socket
import ssl
import sys
import tarfile
import tempfile
import time
import traceback
import urllib.request
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import (
    HTTPRedirectHandler,
    ProxyHandler,
    Request,
    build_opener,
    install_opener,
    urlopen,
)

# Module-level logger
logger = logging.getLogger(__name__)


def setup_logging(level=logging.INFO, debug=False):
    """Configure logging for the application.

    Args:
        level (int): Base logging level (INFO, WARNING, ERROR)
        debug (bool): Enable debug logging if True
    """
    # Set debug level if requested
    if debug:
        level = logging.DEBUG

    # Configure root logger
    logging.basicConfig(
        level=level,
        format="%(message)s",  # Clean format for CLI tool
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Configure module logger
    logger.setLevel(level)

    # Suppress urllib3 warnings unless in debug mode
    if not debug:
        logging.getLogger("urllib3").setLevel(logging.WARNING)


class Config:
    """Configuration management for Docker Image Puller"""

    def __init__(
        self, auth_token=None, proxy_config=None, debug=False, timeout_config=None
    ):
        # Registry configuration
        self.registry_url = "https://registry-1.docker.io"
        self.auth_url = "https://auth.docker.io"
        self.auth_token = auth_token
        self.debug = debug

        # Proxy configuration
        self.proxy_config = self._validate_proxy_config(proxy_config or {})

        # Timeout configuration
        timeout_config = timeout_config or {}
        self.request_timeout = timeout_config.get("request_timeout", 30)
        self.download_timeout = timeout_config.get("download_timeout", 300)
        self.chunk_timeout = timeout_config.get("chunk_timeout", 60)

        # Validate configuration
        self._validate_config()

    def _validate_proxy_config(self, proxy_config):
        """Validate and normalize proxy configuration.

        Merges provided proxy settings with environment variables.
        Environment variables are used as fallback when not explicitly provided.

        Args:
            proxy_config (dict): User-provided proxy configuration

        Returns:
            dict: Validated and normalized proxy configuration
        """
        # Merge environment proxy settings
        if not proxy_config.get("http_proxy"):
            proxy_config["http_proxy"] = os.environ.get("HTTP_PROXY") or os.environ.get(
                "http_proxy"
            )

        if not proxy_config.get("https_proxy"):
            proxy_config["https_proxy"] = os.environ.get(
                "HTTPS_PROXY"
            ) or os.environ.get("https_proxy")

        if not proxy_config.get("no_proxy"):
            proxy_config["no_proxy"] = os.environ.get("NO_PROXY") or os.environ.get(
                "no_proxy"
            )

        return proxy_config

    def _validate_config(self):
        """Validate configuration values"""
        if self.request_timeout <= 0:
            raise ValueError("request_timeout must be positive")
        if self.download_timeout <= 0:
            raise ValueError("download_timeout must be positive")
        if self.chunk_timeout <= 0:
            raise ValueError("chunk_timeout must be positive")

    def has_proxy(self):
        """Check if proxy configuration is present"""
        return bool(
            self.proxy_config.get("http_proxy") or self.proxy_config.get("https_proxy")
        )

    def get_no_proxy_list(self):
        """Get list of hosts that should bypass proxy"""
        no_proxy = self.proxy_config.get("no_proxy")
        if not no_proxy:
            return []
        return [host.strip() for host in no_proxy.split(",")]


class ProxyManager:
    """Handles proxy configuration and URL sanitization"""

    def __init__(self, config):
        self.config = config
        self.no_proxy_list = config.get_no_proxy_list()
        self.setup_proxy()

    def setup_proxy(self):
        """Configure proxy settings for urllib"""
        if not self.config.has_proxy():
            self._setup_no_proxy()
            return

        proxy_handlers = {}

        logger.info("Using proxy configuration:")

        http_proxy = self.config.proxy_config.get("http_proxy")
        https_proxy = self.config.proxy_config.get("https_proxy")

        if http_proxy:
            if self.config.proxy_config.get("proxy_auth"):
                http_proxy = self._add_proxy_auth(
                    http_proxy, self.config.proxy_config["proxy_auth"]
                )
            proxy_handlers["http"] = http_proxy
            logger.info(f"  HTTP Proxy: {self.sanitize_proxy_url(http_proxy)}")

        if https_proxy:
            if self.config.proxy_config.get("proxy_auth"):
                https_proxy = self._add_proxy_auth(
                    https_proxy, self.config.proxy_config["proxy_auth"]
                )
            proxy_handlers["https"] = https_proxy
            logger.info(f"  HTTPS Proxy: {self.sanitize_proxy_url(https_proxy)}")

        if self.config.proxy_config.get("no_proxy"):
            logger.info(f"  No Proxy: {self.config.proxy_config.get('no_proxy')}")

        proxy_handler = ProxyHandler(proxy_handlers)

        # Create redirect handler that strips auth headers
        class NoAuthRedirectHandler(HTTPRedirectHandler):
            def http_error_301(self, req, fp, code, msg, headers):
                if "Authorization" in req.headers:
                    del req.headers["Authorization"]
                return super().http_error_301(req, fp, code, msg, headers)

            def http_error_302(self, req, fp, code, msg, headers):
                if "Authorization" in req.headers:
                    del req.headers["Authorization"]
                return super().http_error_302(req, fp, code, msg, headers)

            def http_error_303(self, req, fp, code, msg, headers):
                if "Authorization" in req.headers:
                    del req.headers["Authorization"]
                return super().http_error_303(req, fp, code, msg, headers)

            def http_error_307(self, req, fp, code, msg, headers):
                if "Authorization" in req.headers:
                    del req.headers["Authorization"]
                return super().http_error_307(req, fp, code, msg, headers)

        if self.config.proxy_config.get("insecure"):
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            https_handler = urllib.request.HTTPSHandler(context=ctx)
            opener = build_opener(proxy_handler, https_handler, NoAuthRedirectHandler)
            logger.info("  SSL Verification: Disabled (insecure mode)")
        else:
            opener = build_opener(proxy_handler, NoAuthRedirectHandler)

        install_opener(opener)

    def _setup_no_proxy(self):
        """Setup opener without proxy"""

        class NoAuthRedirectHandler(HTTPRedirectHandler):
            def http_error_301(self, req, fp, code, msg, headers):
                if "Authorization" in req.headers:
                    del req.headers["Authorization"]
                return super().http_error_301(req, fp, code, msg, headers)

            def http_error_302(self, req, fp, code, msg, headers):
                if "Authorization" in req.headers:
                    del req.headers["Authorization"]
                return super().http_error_302(req, fp, code, msg, headers)

            def http_error_303(self, req, fp, code, msg, headers):
                if "Authorization" in req.headers:
                    del req.headers["Authorization"]
                return super().http_error_303(req, fp, code, msg, headers)

            def http_error_307(self, req, fp, code, msg, headers):
                if "Authorization" in req.headers:
                    del req.headers["Authorization"]
                return super().http_error_307(req, fp, code, msg, headers)

        if self.config.proxy_config.get("insecure"):
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            https_handler = urllib.request.HTTPSHandler(context=ctx)
            opener = build_opener(https_handler, NoAuthRedirectHandler)
        else:
            opener = build_opener(NoAuthRedirectHandler)

        install_opener(opener)

    def _add_proxy_auth(self, proxy_url, auth_string):
        """Add authentication credentials to proxy URL.

        Args:
            proxy_url (str): Base proxy URL
            auth_string (str): Authentication in format "username:password"

        Returns:
            str: Proxy URL with embedded authentication credentials
        """
        if "@" in proxy_url:
            return proxy_url

        parsed = urlparse(proxy_url)
        if ":" in auth_string:
            username, password = auth_string.split(":", 1)
        else:
            logger.warning("Proxy authentication must be in format 'username:password'")
            return proxy_url

        if parsed.port:
            netloc = f"{username}:{password}@{parsed.hostname}:{parsed.port}"
        else:
            netloc = f"{username}:{password}@{parsed.hostname}"

        return f"{parsed.scheme}://{netloc}{parsed.path}"

    def sanitize_proxy_url(self, url):
        """Remove credentials from proxy URL for display"""
        if not url:
            return url

        try:
            parsed = urlparse(url)
            if parsed.username or parsed.password:
                if parsed.port:
                    netloc = f"{parsed.hostname}:{parsed.port}"
                else:
                    netloc = parsed.hostname

                sanitized = f"{parsed.scheme}://{netloc}"
                if parsed.path:
                    sanitized += parsed.path
                if parsed.params:
                    sanitized += f";{parsed.params}"
                if parsed.query:
                    sanitized += f"?{parsed.query}"
                if parsed.fragment:
                    sanitized += f"#{parsed.fragment}"

                return sanitized
        except (ValueError, TypeError, AttributeError):
            return self._mask_credentials_fallback(url)

        return url

    def _mask_credentials_fallback(self, text):
        """Fallback credential masking for malformed URLs or general text"""
        if not text:
            return text

        patterns = [
            r"://[^:/@]+:[^@]+@",  # ://user:pass@
            r"://[^:/@]+@",  # ://user@
        ]

        result = text
        for pattern in patterns:
            result = re.sub(pattern, "://***:***@", result)

        return result

    def sanitize_debug_output(self, text):
        """Sanitize any text that might contain credentials for debug output"""
        if not text or not self.config.debug:
            return text

        return self._mask_credentials_fallback(str(text))

    def should_bypass_proxy(self, hostname):
        """Check if hostname should bypass proxy"""
        if not self.no_proxy_list:
            return False

        for no_proxy_host in self.no_proxy_list:
            if no_proxy_host == "*":
                return True
            elif no_proxy_host.startswith(".") and hostname.endswith(no_proxy_host):
                return True
            elif hostname == no_proxy_host or hostname.endswith("." + no_proxy_host):
                return True

        return False


class ProgressReporter:
    """Enhanced progress reporting with Unicode progress bars and ETA calculation"""

    def __init__(self, total_size=None, description="Download", show_speed=True):
        """Initialize progress reporter.

        Args:
            total_size (int, optional): Total expected size in bytes
            description (str): Description to show before progress bar
            show_speed (bool): Whether to show download speed and ETA
        """
        self.total_size = total_size
        self.downloaded = 0
        self.description = description
        self.show_speed = show_speed
        self.start_time = self._get_time()
        self.last_update = self.start_time

        # Terminal width detection
        self.terminal_width = self._get_terminal_width()

    def _get_time(self):
        """Get current time in seconds"""
        return time.time()

    def _get_terminal_width(self):
        """Get terminal width, default to 80 if detection fails"""
        try:
            return shutil.get_terminal_size().columns
        except (OSError, AttributeError):
            return 80

    def update(self, bytes_downloaded):
        """Update progress with new bytes downloaded.

        Args:
            bytes_downloaded (int): Additional bytes downloaded since last update
        """
        if bytes_downloaded <= 0:
            return

        self.downloaded += bytes_downloaded
        current_time = self._get_time()

        # Throttle display updates
        if current_time - self.last_update < 0.1 and self.downloaded < (
            self.total_size or float("inf")
        ):
            return

        self._display_progress()
        self.last_update = current_time

    def _display_progress(self):
        """Display current progress bar and stats"""
        # Calculate progress percentage
        if self.total_size:
            progress_pct = min(100.0, (self.downloaded / self.total_size) * 100)
        else:
            progress_pct = 0

        # Format downloaded amount
        downloaded_str = self._format_bytes(self.downloaded)

        # Build progress bar
        if self.total_size:
            total_str = self._format_bytes(self.total_size)
            size_info = f"{downloaded_str}/{total_str}"
            progress_bar = self._build_progress_bar(progress_pct)
        else:
            size_info = downloaded_str
            progress_bar = f"[{'█' * 10}] ???%"

        # Calculate speed and ETA
        speed_info = ""
        if self.show_speed:
            elapsed = self._get_time() - self.start_time
            if elapsed > 0:
                speed = self.downloaded / elapsed
                speed_str = f"{self._format_bytes(speed)}/s"

                if self.total_size and speed > 0:
                    remaining = (self.total_size - self.downloaded) / speed
                    eta_str = self._format_duration(remaining)
                    speed_info = f" | {speed_str} | ETA: {eta_str}"
                else:
                    speed_info = f" | {speed_str}"

        # Build complete progress line
        progress_line = f"  {self.description}: {progress_bar} {size_info}{speed_info}"

        # Truncate to terminal width if needed
        if len(progress_line) > self.terminal_width:
            available = (
                self.terminal_width
                - len(f"  {self.description}: ")
                - len(size_info)
                - len(speed_info)
                - 3
            )
            if available > 10:  # Minimum width required
                progress_bar = self._build_progress_bar(progress_pct, available)
                progress_line = (
                    f"  {self.description}: {progress_bar} {size_info}{speed_info}"
                )
            else:
                # Minimal display for narrow terminals
                progress_line = f"  {downloaded_str} {int(progress_pct)}%"

        # Print with carriage return for overwrite
        print(f"\r{progress_line}", end="", flush=True)

    def _build_progress_bar(self, progress_pct, width=30):
        """Build Unicode progress bar.

        Args:
            progress_pct (float): Progress percentage (0-100)
            width (int): Width of progress bar in characters

        Returns:
            str: Formatted progress bar
        """
        filled_width = int(width * progress_pct / 100)

        # Unicode block characters for smooth progress
        filled_char = "█"
        empty_char = "░"

        # Create partial fill for smoother appearance
        partial_progress = (width * progress_pct / 100) - filled_width
        if partial_progress > 0.75:
            partial_char = "▉"
        elif partial_progress > 0.5:
            partial_char = "▊"
        elif partial_progress > 0.25:
            partial_char = "▌"
        elif partial_progress > 0:
            partial_char = "▎"
        else:
            partial_char = ""

        # Build the bar
        bar_content = (
            filled_char * filled_width
            + partial_char
            + empty_char * (width - filled_width - len(partial_char))
        )

        return f"[{bar_content[:width]}] {progress_pct:5.1f}%"

    def _format_bytes(self, size):
        """Format bytes into human readable string.

        Args:
            size (int): Size in bytes

        Returns:
            str: Formatted size string
        """
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024.0:
                if unit == "B":
                    return f"{int(size)} {unit}"
                else:
                    return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"

    def _format_duration(self, seconds):
        """Format duration into human readable string.

        Args:
            seconds (float): Duration in seconds

        Returns:
            str: Formatted duration string
        """
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            secs = int(seconds % 60)
            return f"{minutes}m{secs:02d}s"
        else:
            hours = int(seconds / 3600)
            minutes = int((seconds % 3600) / 60)
            return f"{hours}h{minutes:02d}m"

    def finish(self):
        """Complete the progress display with a newline"""
        if self.downloaded > 0:
            print()  # New line to finish progress display


class DockerImagePuller:
    def __init__(
        self, auth_token=None, proxy_config=None, debug=False, timeout_config=None
    ):
        # Create configuration object
        self.config = Config(auth_token, proxy_config, debug, timeout_config)

        # Public API attributes - provide direct access to configuration
        self.registry_url = self.config.registry_url
        self.auth_url = self.config.auth_url
        self.auth_token = self.config.auth_token
        self.proxy_config = self.config.proxy_config
        self.request_timeout = self.config.request_timeout
        self.download_timeout = self.config.download_timeout
        self.chunk_timeout = self.config.chunk_timeout

        # Create proxy manager
        self.proxy_manager = ProxyManager(self.config)

        # Set up no_proxy_list for direct access
        self.no_proxy_list = self.proxy_manager.no_proxy_list

    def setup_proxy(self):
        """Configure proxy settings for urllib - delegated to ProxyManager"""
        self.proxy_manager.setup_proxy()

    def add_proxy_auth(self, proxy_url, auth_string):
        """Add authentication to proxy URL - delegated to ProxyManager"""
        return self.proxy_manager._add_proxy_auth(proxy_url, auth_string)

    def sanitize_proxy_url(self, url):
        """Remove credentials from proxy URL for display - delegated to ProxyManager"""
        return self.proxy_manager.sanitize_proxy_url(url)

    def _mask_credentials_fallback(self, text):
        """Fallback credential masking - delegated to ProxyManager"""
        return self.proxy_manager._mask_credentials_fallback(text)

    def sanitize_debug_output(self, text):
        """Sanitize any text that might contain credentials for debug output - delegated to ProxyManager"""
        return self.proxy_manager.sanitize_debug_output(text)

    def _stream_download(self, response, digest, expected_size=None):
        """Stream download with progress tracking and memory efficiency.

        Downloads large blobs using streaming to avoid memory issues.
        Includes enhanced progress reporting with Unicode bars and ETA.

        Args:
            response: HTTP response object to stream from
            digest (str): Blob digest for identification in error messages
            expected_size (int, optional): Expected download size in bytes

        Returns:
            bytes: Downloaded data, or None if download failed

        Raises:
            TimeoutError: If download stalls or chunk timeout exceeded
        """

        # Setup timeout handling for stuck downloads
        def timeout_handler(_signum, _frame):
            raise TimeoutError(f"Download chunk timeout after {self.chunk_timeout}s")

        # Use temporary file for streaming
        temp_data = tempfile.NamedTemporaryFile(delete=False)
        total_size = 0
        chunk_size = 65536  # 64KB chunks
        last_activity = time.time()

        # Initialize progress reporter for files > 1MB
        progress_reporter = None
        if expected_size and expected_size > 1024 * 1024:  # Over 1MB
            blob_name = digest[:12] + "..." if len(digest) > 12 else digest
            progress_reporter = ProgressReporter(expected_size, f"Layer {blob_name}")

        try:
            if hasattr(signal, "SIGALRM"):  # Unix systems only
                signal.signal(signal.SIGALRM, timeout_handler)

            while True:
                if hasattr(signal, "SIGALRM"):
                    signal.alarm(self.chunk_timeout)

                try:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break

                    temp_data.write(chunk)
                    chunk_len = len(chunk)
                    total_size += chunk_len
                    last_activity = time.time()

                    # Update progress reporter
                    if progress_reporter:
                        progress_reporter.update(chunk_len)
                    elif total_size > 1024 * 1024:  # Fallback for unknown size
                        # Fallback progress display
                        mb_downloaded = total_size / (1024 * 1024)
                        print(f"  Downloaded {mb_downloaded:.1f} MB...", end="\r")

                    # Check for stalled downloads
                    if time.time() - last_activity > self.chunk_timeout:
                        raise TimeoutError(
                            f"Download stalled - no data received for {self.chunk_timeout}s"
                        )

                except socket.timeout:
                    raise TimeoutError("Download chunk timeout")
                finally:
                    if hasattr(signal, "SIGALRM"):
                        signal.alarm(0)  # Cancel timeout

            # Finish progress reporting
            if progress_reporter:
                progress_reporter.finish()
            elif total_size > 1024 * 1024:
                print()  # New line after fallback progress

            # Read the data back from temp file
            temp_data.close()
            with open(temp_data.name, "rb") as f:
                data = f.read()

            return data

        except (TimeoutError, socket.timeout) as e:
            if progress_reporter:
                progress_reporter.finish()
            logger.error(f"Download timeout for blob {digest}: {e}")
            return None
        except Exception as e:
            if progress_reporter:
                progress_reporter.finish()
            logger.error(f"Streaming error for blob {digest}: {e}")
            return None
        finally:
            # Cleanup
            if hasattr(signal, "SIGALRM"):
                signal.alarm(0)
            temp_data.close()
            try:
                os.unlink(temp_data.name)
            except OSError:
                pass

    def should_bypass_proxy(self, hostname):
        """Check if hostname should bypass proxy - delegated to ProxyManager"""
        return self.proxy_manager.should_bypass_proxy(hostname)

    def make_request(self, url, headers=None):
        """Make HTTP request with proxy handling"""
        req_headers = headers or {}

        logger.debug(f"Request URL: {self.sanitize_debug_output(url)}")
        logger.debug(f"Headers: {self.sanitize_debug_output(req_headers)}")

        # Check if we should bypass proxy for this URL
        parsed_url = urlparse(url)
        if self.should_bypass_proxy(parsed_url.hostname):
            logger.debug(f"Bypassing proxy for {parsed_url.hostname}")
            # Temporarily disable proxy for this request
            old_proxies = {}
            for proxy_var in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]:
                if proxy_var in os.environ:
                    old_proxies[proxy_var] = os.environ[proxy_var]
                    del os.environ[proxy_var]

            try:
                req = Request(url, headers=req_headers)
                response = urlopen(req, timeout=self.request_timeout)
                logger.debug(f"Response code: {response.code}")
                return response
            finally:
                # Restore proxy settings
                for proxy_var, value in old_proxies.items():
                    os.environ[proxy_var] = value
        else:
            req = Request(url, headers=req_headers)
            response = urlopen(req, timeout=self.request_timeout)
            logger.debug(f"Response code: {response.code}")
            return response

    def get_auth_token(self, image_name):
        """Get authentication token for Docker Hub"""
        if self.auth_token:
            return self.auth_token

        scope = f"repository:{image_name}:pull"
        params = {"service": "registry.docker.io", "scope": scope}

        url = f"{self.auth_url}/token?{urlencode(params)}"

        try:
            with self.make_request(url) as response:
                data = json.loads(response.read())
                return data.get("token")
        except (HTTPError, URLError) as e:
            logger.error(f"Error getting auth token: {e}")
            logger.info(
                "If using a corporate proxy, verify proxy configuration is correct"
            )
            sys.exit(1)
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Error parsing auth token response: {e}")
            sys.exit(1)
        except Exception as e:
            logger.error(f"Unexpected error getting auth token: {e}")
            sys.exit(1)

    def get_manifest(
        self, image_name, tag, token, architecture="amd64", os_type="linux"
    ):
        """Get image manifest from registry, handling multi-arch manifest lists"""
        url = f"{self.registry_url}/v2/{image_name}/manifests/{tag}"

        # First, try to get manifest list (for multi-arch images)
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.docker.distribution.manifest.list.v2+json,application/vnd.docker.distribution.manifest.v2+json,application/vnd.oci.image.index.v1+json,application/vnd.oci.image.manifest.v1+json",
        }

        try:
            with self.make_request(url, headers) as response:
                manifest_data = json.loads(response.read())

                # Check if this is a manifest list (multi-arch)
                if "manifests" in manifest_data:
                    logger.info(
                        "Multi-architecture image detected. Available platforms:"
                    )

                    # List available platforms
                    valid_manifests = []
                    for m in manifest_data["manifests"]:
                        platform = m.get("platform", {})
                        arch = platform.get("architecture", "unknown")
                        os = platform.get("os", "unknown")
                        variant = platform.get("variant", "")

                        # Skip invalid entries
                        if arch == "unknown" or os == "unknown":
                            continue

                        valid_manifests.append(m)
                        variant_str = f"-{variant}" if variant else ""
                        logger.info(f"  - {os}/{arch}{variant_str}")

                    # Find matching manifest for requested architecture
                    selected_manifest = None

                    # First try exact match
                    for m in valid_manifests:
                        platform = m.get("platform", {})
                        if (
                            platform.get("architecture") == architecture
                            and platform.get("os") == os_type
                        ):
                            selected_manifest = m
                            break

                    # If no exact match and looking for arm, try variants
                    if not selected_manifest and architecture in ["arm", "arm64"]:
                        for m in valid_manifests:
                            platform = m.get("platform", {})
                            p_arch = platform.get("architecture", "")
                            p_os = platform.get("os", "")
                            p_variant = platform.get("variant", "")

                            # Match arm variants
                            if p_os == os_type:
                                if architecture == "arm64" and (
                                    p_arch == "arm64"
                                    or (p_arch == "arm" and p_variant == "v8")
                                ):
                                    selected_manifest = m
                                    break
                                elif architecture == "arm" and p_arch == "arm":
                                    selected_manifest = m
                                    break

                    if not selected_manifest and valid_manifests:
                        # Fallback to first available platform
                        logger.warning(f"No exact match for {os_type}/{architecture}")
                        logger.info("Using first available platform as fallback")
                        selected_manifest = valid_manifests[0]
                        platform = selected_manifest.get("platform", {})
                        logger.info(
                            f"Using: {platform.get('os')}/{platform.get('architecture')}"
                        )

                    if not selected_manifest:
                        logger.error("No valid manifest found")
                        sys.exit(1)

                    platform = selected_manifest.get("platform", {})
                    logger.info(
                        f"Selected platform: {platform.get('os')}/{platform.get('architecture')}"
                    )

                    # Now fetch the specific manifest using its digest
                    specific_digest = selected_manifest["digest"]
                    url = f"{self.registry_url}/v2/{image_name}/manifests/{specific_digest}"

                    headers = {
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/vnd.docker.distribution.manifest.v2+json,application/vnd.oci.image.manifest.v1+json",
                    }

                    with self.make_request(url, headers) as response:
                        specific_manifest = json.loads(response.read())

                        # Check if we got an OCI manifest and convert if needed
                        if (
                            "mediaType" in specific_manifest
                            and "oci" in specific_manifest.get("mediaType", "")
                        ):
                            logger.info("  (OCI format image)")

                        return specific_manifest

                # It's already a regular manifest
                elif "config" in manifest_data:
                    return manifest_data

                # OCI format manifest
                elif "mediaType" in manifest_data:
                    return manifest_data

                # Older schema v1 manifest (deprecated but might still exist)
                elif (
                    "schemaVersion" in manifest_data
                    and manifest_data["schemaVersion"] == 1
                ):
                    logger.warning("Image uses deprecated manifest schema v1")
                    logger.warning(
                        "This format is not fully supported. Image may not load correctly."
                    )
                    # Try to convert v1 to v2-like structure
                    return self.convert_schema_v1(manifest_data)

                else:
                    logger.error(
                        f"Unknown manifest format. Keys found: {list(manifest_data.keys())}"
                    )
                    logger.error(
                        "Manifest content: %s",
                        json.dumps(manifest_data, indent=2)[:500],
                    )
                    sys.exit(1)

        except HTTPError as e:
            if e.code == 404:
                logger.error(f"Image {image_name}:{tag} not found")
            else:
                logger.error(f"Error getting manifest: {e}")
                try:
                    error_body = e.read().decode("utf-8")
                    if error_body:
                        logger.error("Error details: %s", error_body)
                except (UnicodeDecodeError, AttributeError):
                    pass
            sys.exit(1)
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Error parsing manifest response: {e}")
            sys.exit(1)
        except Exception as e:
            logger.error(f"Unexpected error getting manifest: {e}")
            traceback.print_exc()
            sys.exit(1)

    def convert_schema_v1(self, v1_manifest):
        """Attempt to convert schema v1 manifest to v2-like structure"""
        # Best-effort v1 to v2 conversion
        logger.info("Converting v1 manifest to v2 format...")

        # Extract layer digests from v1 fsLayers
        layers = []
        if "fsLayers" in v1_manifest:
            for fs_layer in v1_manifest["fsLayers"]:
                layers.append(
                    {
                        "digest": fs_layer.get("blobSum", ""),
                        "size": 0,  # v1 doesn't include size
                        "mediaType": "application/vnd.docker.image.rootfs.diff.tar.gzip",
                    }
                )

        # Create a minimal v2-like structure
        # Note: v1 doesn't have a separate config blob
        return {
            "schemaVersion": 2,
            "config": {
                "digest": "sha256:" + "0" * 64,  # Placeholder
                "size": 0,
                "mediaType": "application/vnd.docker.container.image.v1+json",
            },
            "layers": layers,
        }

    def download_blob(self, image_name, digest, token, retry_with_new_token=True):
        """Download a blob (layer) from Docker registry.

        Handles authentication, redirects, and CDN optimization.
        Automatically retries with fresh token on 401 errors.

        Args:
            image_name (str): Repository name (e.g., 'library/alpine')
            digest (str): SHA256 digest of the blob to download
            token (str): Bearer token for authentication
            retry_with_new_token (bool): Retry once with fresh token on 401

        Returns:
            bytes: Blob data, or None if download failed

        Raises:
            Various network and HTTP errors are caught and logged
        """
        url = f"{self.registry_url}/v2/{image_name}/blobs/{digest}"

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.docker.image.rootfs.diff.tar.gzip,application/octet-stream,*/*",
        }

        try:
            # Make the request - redirects will be handled automatically
            # and auth headers will be stripped by our custom redirect handler
            req = Request(url, headers=headers)

            logger.debug(f"Downloading blob from: {url}")

            # For blob downloads, temporarily bypass proxy for CDN URLs
            # Save current proxy settings
            old_proxies = {}
            bypass_proxy_for_cdn = False

            try:
                # First, make a HEAD request to see if we'll be redirected to a CDN
                head_req = Request(url, headers=headers)
                head_req.get_method = lambda: "HEAD"

                try:
                    with urlopen(
                        head_req, timeout=self.request_timeout
                    ) as head_response:
                        # Check if we got redirected to a CDN
                        final_url = head_response.geturl()
                        if final_url != url:
                            # We got redirected, check if it's to S3/CDN
                            if (
                                "amazonaws.com" in final_url
                                or "cloudfront.net" in final_url
                            ):
                                bypass_proxy_for_cdn = True
                                logger.debug(
                                    f"Will bypass proxy for CDN URL: {final_url[:100]}..."
                                )
                except HTTPError as e:
                    # If we get a redirect status, extract the Location header
                    if e.code in [301, 302, 303, 307, 308]:
                        location = e.headers.get("Location", "")
                        if "amazonaws.com" in location or "cloudfront.net" in location:
                            bypass_proxy_for_cdn = True
                            logger.debug(
                                f"Will bypass proxy for CDN redirect: {location[:100]}..."
                            )
            except (HTTPError, URLError, OSError, socket.timeout):
                # HEAD request failed, continue with GET
                pass

            # If we need to bypass proxy for CDN, temporarily disable it
            if bypass_proxy_for_cdn:
                for proxy_var in [
                    "HTTP_PROXY",
                    "HTTPS_PROXY",
                    "http_proxy",
                    "https_proxy",
                ]:
                    if proxy_var in os.environ:
                        old_proxies[proxy_var] = os.environ[proxy_var]
                        del os.environ[proxy_var]

                # Reinstall opener without proxy
                if self.proxy_config.get("insecure"):
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    https_handler = urllib.request.HTTPSHandler(context=ctx)
                    opener = build_opener(https_handler)
                else:
                    opener = build_opener()
                install_opener(opener)

                logger.debug("Temporarily disabled proxy for CDN download")

            # Now make the actual download request
            with urlopen(req, timeout=self.download_timeout) as response:
                # Check if we got redirected
                final_url = response.geturl()
                if final_url != url:
                    logger.debug(f"Followed redirect to: {final_url[:100]}...")

                # Get content length if available
                content_length = response.headers.get("Content-Length")
                expected_size = int(content_length) if content_length else None

                # Use streaming download to prevent memory issues
                return self._stream_download(response, digest, expected_size)

        except HTTPError as e:
            if e.code == 401 and retry_with_new_token:
                # Token might not have the right scope, get a new one
                logger.debug("Got 401, retrying with new token...")
                logger.info("Authorization failed, requesting new token...")
                new_token = self.get_auth_token(image_name)
                return self.download_blob(
                    image_name, digest, new_token, retry_with_new_token=False
                )

            logger.error(f"Error downloading blob {digest}: HTTP {e.code} - {e.reason}")

            # Print response body for debugging
            try:
                error_body = e.read().decode("utf-8")
                if error_body:
                    logger.error("Error details: %s", error_body[:500])
            except (UnicodeDecodeError, AttributeError):
                pass

            logger.debug(f"Request headers were: {self.sanitize_debug_output(headers)}")

            return None

        except (URLError, OSError) as e:
            logger.error(f"Network error downloading blob {digest}: {e}")
            logger.debug("Exception traceback:", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"Unexpected error downloading blob {digest}: {e}")
            logger.debug("Exception traceback:", exc_info=True)
            return None

        finally:
            # Restore proxy settings if we bypassed them
            if bypass_proxy_for_cdn and old_proxies:
                for proxy_var, value in old_proxies.items():
                    os.environ[proxy_var] = value

                # Reinstall the original opener with proxy
                self.setup_proxy()

                logger.debug("Restored proxy settings")

    def create_docker_tar(
        self,
        image_name,
        tag,
        manifest,
        config_blob,
        layers,
        output_file,
        progress_reporter=None,
    ):
        """Create a Docker-compatible tar file from downloaded components.

        Assembles the manifest, config, and layers into a standard Docker tar
        format that can be loaded with 'docker load'.

        Args:
            image_name (str): Full image name (e.g., 'library/alpine')
            tag (str): Image tag (e.g., 'latest')
            manifest (dict): Image manifest metadata
            config_blob (bytes): Image configuration blob
            layers (list): List of layer dictionaries with digest, size, data
            output_file (str): Path where to save the tar file
            progress_reporter (ProgressReporter, optional): Progress reporter for tar creation

        Creates:
            A tar file containing:
            - manifest.json: Docker format manifest
            - {config_digest}.json: Image configuration
            - repositories: Repository tags mapping
            - {layer_digest}/: Layer directories with layer.tar, json, VERSION
        """

        # Parse image name for repository
        if "/" in image_name:
            namespace, repo = image_name.split("/", 1)
        else:
            namespace = "library"
            repo = image_name

        full_image_name = f"{namespace}/{repo}"

        # Calculate progress steps
        total_steps = 4 + len(
            layers
        )  # manifest, config, repositories, tar creation + layers
        current_step = 0

        def update_progress(step_name="Processing"):
            nonlocal current_step
            current_step += 1
            if progress_reporter:
                # Simulate progress for tar creation
                progress_reporter.downloaded = int((current_step / total_steps) * 100)
                progress_reporter.total_size = 100
                progress_reporter.description = step_name
                progress_reporter._display_progress()

        # Create temporary directory for building tar
        with tempfile.TemporaryDirectory() as tmpdir:
            update_progress("Preparing config")

            # Save config JSON
            config_digest = manifest["config"]["digest"].replace("sha256:", "")
            config_file = f"{config_digest}.json"
            config_path = os.path.join(tmpdir, config_file)

            with open(config_path, "wb") as f:
                f.write(config_blob)

            update_progress("Processing layers")

            # Save layers
            layer_files = []
            for i, layer_info in enumerate(layers):
                layer_digest = layer_info["digest"].replace("sha256:", "")
                layer_dir = os.path.join(tmpdir, layer_digest)
                os.makedirs(layer_dir, exist_ok=True)

                layer_tar_path = os.path.join(layer_dir, "layer.tar")

                # Check if layer data is gzipped and decompress if needed
                layer_data = layer_info["data"]
                if layer_data[:2] == b"\x1f\x8b":  # gzip magic number
                    try:
                        layer_data = gzip.decompress(layer_data)
                    except (OSError, gzip.BadGzipFile):
                        pass  # Not gzipped or error decompressing

                with open(layer_tar_path, "wb") as f:
                    f.write(layer_data)

                # Create VERSION file
                version_path = os.path.join(layer_dir, "VERSION")
                with open(version_path, "w") as f:
                    f.write("1.0")

                # Create layer.json
                layer_json_path = os.path.join(layer_dir, "json")
                layer_json = {
                    "id": layer_digest,
                    "created": datetime.now(timezone.utc).isoformat(),
                    "container_config": {
                        "Hostname": "",
                        "Domainname": "",
                        "User": "",
                        "AttachStdin": False,
                        "AttachStdout": False,
                        "AttachStderr": False,
                        "Tty": False,
                        "OpenStdin": False,
                        "StdinOnce": False,
                        "Env": None,
                        "Cmd": None,
                        "Image": "",
                        "Volumes": None,
                        "WorkingDir": "",
                        "Entrypoint": None,
                        "OnBuild": None,
                        "Labels": None,
                    },
                }

                with open(layer_json_path, "w") as f:
                    json.dump(layer_json, f)

                layer_files.append(layer_digest)
                update_progress(f"Layer {i + 1}/{len(layers)}")

            update_progress("Creating manifest")

            # Create manifest.json
            manifest_json = [
                {
                    "Config": config_file,
                    "RepoTags": [f"{full_image_name}:{tag}"],
                    "Layers": [f"{lf}/layer.tar" for lf in layer_files],
                }
            ]

            manifest_path = os.path.join(tmpdir, "manifest.json")
            with open(manifest_path, "w") as f:
                json.dump(manifest_json, f)

            # Create repositories file
            repositories = {
                full_image_name: {tag: layer_files[-1] if layer_files else ""}
            }

            repositories_path = os.path.join(tmpdir, "repositories")
            with open(repositories_path, "w") as f:
                json.dump(repositories, f)

            update_progress("Building tar file")

            # Create the tar file
            with tarfile.open(output_file, "w") as tar:
                # Add manifest.json
                tar.add(manifest_path, arcname="manifest.json")

                # Add config
                tar.add(config_path, arcname=config_file)

                # Add repositories
                tar.add(repositories_path, arcname="repositories")

                # Add each layer directory
                for layer_digest in layer_files:
                    layer_dir = os.path.join(tmpdir, layer_digest)
                    for root, _dirs, files in os.walk(layer_dir):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, tmpdir)
                            tar.add(file_path, arcname=arcname)

            update_progress("Completed")

    def pull_image(
        self, image_spec, output_file=None, architecture="amd64", os_type="linux"
    ):
        """Pull a Docker image and save as tar with enhanced progress reporting.

        Args:
            image_spec (str): Image specification (name:tag)
            output_file (str, optional): Output tar filename
            architecture (str): Target architecture
            os_type (str): Target operating system
        """

        # Parse image specification
        if ":" in image_spec:
            image_name, tag = image_spec.rsplit(":", 1)
        else:
            image_name = image_spec
            tag = "latest"

        # Handle official images (prepend library/)
        if "/" not in image_name:
            full_image_name = f"library/{image_name}"
        else:
            full_image_name = image_name

        if not output_file:
            safe_name = image_name.replace("/", "_")
            output_file = f"{safe_name}_{tag}.tar"

        logger.info(f"Downloading image: {full_image_name}:{tag}")

        # Get auth token
        token = self.get_auth_token(full_image_name)

        # Get manifest
        logger.info("Retrieving image manifest...")
        manifest = self.get_manifest(full_image_name, tag, token, architecture, os_type)

        # Download config
        logger.info("Downloading image configuration...")
        config_digest = manifest.get("config", {}).get("digest")
        if not config_digest:
            logger.error("No config digest found in manifest")
            logger.error("Manifest structure: %s", json.dumps(manifest, indent=2)[:500])
            sys.exit(1)

        config_blob = self.download_blob(full_image_name, config_digest, token)

        if not config_blob:
            logger.error("Failed to download config")
            sys.exit(1)

        # Download layers with overall progress tracking
        layers = []
        layer_list = manifest.get("layers", [])
        total_layers = len(layer_list)

        if total_layers == 0:
            logger.warning("No layers found in manifest")
            logger.error("Manifest structure: %s", json.dumps(manifest, indent=2)[:500])
        else:
            # Calculate total download size for overall progress
            total_download_size = sum(layer.get("size", 0) for layer in layer_list)

            logger.info(
                f"Downloading {total_layers} layers ({self._format_bytes(total_download_size)} total)..."
            )

            # Create overall progress reporter
            overall_progress = ProgressReporter(
                total_download_size if total_download_size > 0 else None,
                "Overall progress",
                show_speed=True,
            )

            downloaded_size = 0

        for i, layer in enumerate(layer_list):
            digest = layer.get("digest")
            size = layer.get("size", 0)

            if not digest:
                logger.warning(f"Layer {i + 1} missing digest, skipping")
                continue

            size_str = f"{self._format_bytes(size)}" if size else "unknown size"
            layer_desc = f"Layer {i + 1}/{total_layers}"

            # Show individual layer info
            logger.info(f"{layer_desc} ({digest[:12]}... {size_str})")

            blob_data = self.download_blob(full_image_name, digest, token)

            if not blob_data:
                logger.error(f"Failed to download layer {digest}")
                logger.info("Continuing with remaining layers")
                continue

            # Update overall progress
            if total_layers > 0:
                downloaded_size += len(blob_data)
                overall_progress.downloaded = downloaded_size
                overall_progress._display_progress()

            layers.append({"digest": digest, "size": size, "data": blob_data})

        # Finish overall progress
        if total_layers > 0:
            overall_progress.finish()

        if not layers:
            logger.error("No layers were successfully downloaded")
            sys.exit(1)

        # Create Docker tar
        logger.info(f"Creating tar file: {output_file}")

        # Show tar creation progress for large images
        tar_progress = ProgressReporter(description="Creating tar", show_speed=False)

        self.create_docker_tar(
            full_image_name,
            tag,
            manifest,
            config_blob,
            layers,
            output_file,
            tar_progress,
        )

        tar_progress.finish()

        # Calculate final size
        file_size = os.path.getsize(output_file)
        logger.info(
            f"Successfully created {output_file} (size: {self._format_bytes(file_size)})"
        )
        logger.info(f"To load this image, run: docker load -i {output_file}")

    def _format_bytes(self, size):
        """Format bytes into human readable string (helper method).

        Args:
            size (int): Size in bytes

        Returns:
            str: Formatted size string
        """
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024.0:
                if unit == "B":
                    return f"{int(size)} {unit}"
                else:
                    return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"


def main():
    parser = argparse.ArgumentParser(
        description="Pull Docker images from Docker Hub and save as tar files (with proxy support)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment Variables:
  HTTP_PROXY / http_proxy     - HTTP proxy URL
  HTTPS_PROXY / https_proxy   - HTTPS proxy URL  
  NO_PROXY / no_proxy         - Comma-separated list of hosts to bypass proxy

Examples:
  %(prog)s ubuntu:20.04
  %(prog)s alpine --output alpine-latest.tar
  
  # Pull ARM64 image
  %(prog)s ubuntu:latest --arch arm64
  
  # With proxy
  %(prog)s nginx:latest --proxy http://proxy.company.com:8080
  
  # With proxy authentication
  %(prog)s alpine --proxy http://proxy.company.com:8080 --proxy-auth username:password
  
  # Using environment variables
  export HTTPS_PROXY=http://proxy.company.com:8080
  export NO_PROXY=localhost,127.0.0.1,.local
  %(prog)s ubuntu:latest
  
  # Disable SSL verification for corporate proxies
  %(prog)s nginx --proxy https://proxy.company.com:8080 --insecure
        """,
    )

    parser.add_argument(
        "image", help="Docker image to pull (e.g., ubuntu:20.04, alpine, nginx:latest)"
    )

    parser.add_argument(
        "-o",
        "--output",
        help="Output tar filename (default: imagename_tag.tar)",
        default=None,
    )

    parser.add_argument(
        "-t",
        "--token",
        help="Docker Hub authentication token (for private repositories)",
        default=None,
    )

    # Architecture and OS arguments
    parser.add_argument(
        "--arch",
        "--architecture",
        help="Target architecture (default: amd64)",
        default="amd64",
        choices=[
            "amd64",
            "arm64",
            "arm",
            "386",
            "ppc64le",
            "s390x",
            "mips64le",
            "riscv64",
        ],
    )

    parser.add_argument(
        "--os",
        help="Target operating system (default: linux)",
        default="linux",
        choices=["linux", "windows"],
    )

    # Proxy arguments
    parser.add_argument(
        "-p",
        "--proxy",
        help="Proxy URL (e.g., http://proxy.company.com:8080)",
        default=None,
    )

    parser.add_argument(
        "--proxy-auth",
        help="Proxy authentication in format username:password",
        default=None,
    )

    parser.add_argument(
        "--http-proxy",
        help="HTTP proxy URL (overrides environment variable)",
        default=None,
    )

    parser.add_argument(
        "--https-proxy",
        help="HTTPS proxy URL (overrides environment variable)",
        default=None,
    )

    parser.add_argument(
        "--no-proxy", help="Comma-separated list of hosts to bypass proxy", default=None
    )

    parser.add_argument(
        "-k",
        "--insecure",
        action="store_true",
        help="Disable SSL certificate verification (useful for corporate proxies)",
    )

    parser.add_argument(
        "--debug", action="store_true", help="Enable debug output for troubleshooting"
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging (INFO level)",
    )

    parser.add_argument(
        "-q", "--quiet", action="store_true", help="Quiet mode - only show errors"
    )

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Set logging level explicitly",
        default=None,
    )

    args = parser.parse_args()

    # Set up logging based on arguments
    log_level = logging.WARNING  # Default level

    if args.debug:
        log_level = logging.DEBUG
    elif args.verbose:
        log_level = logging.INFO
    elif args.quiet:
        log_level = logging.ERROR
    elif args.log_level:
        log_level = getattr(logging, args.log_level)

    setup_logging(level=log_level, debug=args.debug)

    # Build proxy configuration
    proxy_config = {}

    # Handle simplified --proxy argument
    if args.proxy:
        proxy_config["http_proxy"] = args.proxy
        proxy_config["https_proxy"] = args.proxy

    # Handle specific proxy settings
    if args.http_proxy:
        proxy_config["http_proxy"] = args.http_proxy

    if args.https_proxy:
        proxy_config["https_proxy"] = args.https_proxy

    if args.no_proxy:
        proxy_config["no_proxy"] = args.no_proxy

    if args.proxy_auth:
        proxy_config["proxy_auth"] = args.proxy_auth

    if args.insecure:
        proxy_config["insecure"] = True

    # Create puller instance
    puller = DockerImagePuller(
        auth_token=args.token, proxy_config=proxy_config, debug=args.debug
    )

    try:
        puller.pull_image(
            args.image, args.output, architecture=args.arch, os_type=args.os
        )
    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        sys.exit(1)
    except (HTTPError, URLError, OSError) as e:
        logger.error(f"Network/IO Error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
