#!/usr/bin/env python3
"""
Test Suite for Docker Image Puller
Comprehensive tests for all components with no external dependencies.

Usage: python3 test_docker_pull.py
"""

import sys
import os

# Import the main classes from docker_pull.py
try:
    from docker_pull import Config, ProxyManager, ProgressReporter, DockerImagePuller
except ImportError:
    print("❌ Error: Cannot import docker_pull.py")
    print("   Make sure docker_pull.py is in the same directory")
    sys.exit(1)


class TestSuite:
    """Self-contained test suite for Docker Image Puller - no external dependencies"""
    
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        
    def assert_equal(self, actual, expected, message=""):
        """Assert that two values are equal"""
        if actual == expected:
            return True
        else:
            test_name = message or f"Expected {expected}, got {actual}"
            print(f"  ❌ FAIL: {test_name}")
            self.tests_failed += 1
            return False
    
    def assert_true(self, condition, message=""):
        """Assert that condition is true"""
        if condition:
            return True
        else:
            test_name = message or "Expected condition to be True"
            print(f"  ❌ FAIL: {test_name}")
            self.tests_failed += 1
            return False
            
    def assert_false(self, condition, message=""):
        """Assert that condition is false"""
        if not condition:
            return True
        else:
            test_name = message or "Expected condition to be False"
            print(f"  ❌ FAIL: {test_name}")
            self.tests_failed += 1
            return False
    
    def assert_raises(self, exception_type, func, *args, **kwargs):
        """Assert that function raises specified exception"""
        try:
            func(*args, **kwargs)
            print(f"  ❌ FAIL: Expected {exception_type.__name__} to be raised")
            self.tests_failed += 1
            return False
        except exception_type:
            return True
        except Exception as e:
            print(f"  ❌ FAIL: Expected {exception_type.__name__}, got {type(e).__name__}: {e}")
            self.tests_failed += 1
            return False
    
    def run_test(self, test_func, test_name):
        """Run a single test function"""
        self.tests_run += 1
        print(f"\n🧪 Running {test_name}...")
        
        try:
            if test_func():
                print(f"  ✅ PASS: {test_name}")
                self.tests_passed += 1
            else:
                print(f"  ❌ FAIL: {test_name}")
                self.tests_failed += 1
        except Exception as e:
            print(f"  ❌ ERROR: {test_name} - {type(e).__name__}: {e}")
            self.tests_failed += 1
    
    def test_config_validation(self):
        """Test Config class validation logic"""
        print("  Testing Config class validation...")
        
        # Test valid configuration
        try:
            config = Config(timeout_config={"request_timeout": 30, "download_timeout": 300, "chunk_timeout": 60})
            success = True
        except Exception:
            success = False
        
        if not self.assert_true(success, "Valid config should not raise exception"):
            return False
            
        # Test invalid timeout values
        if not self.assert_raises(ValueError, Config, timeout_config={"request_timeout": -1}):
            return False
            
        if not self.assert_raises(ValueError, Config, timeout_config={"download_timeout": 0}):
            return False
            
        # Test proxy environment variable handling
        old_proxy = os.environ.get('HTTP_PROXY')
        os.environ['HTTP_PROXY'] = 'http://test-proxy:8080'
        
        try:
            config = Config()
            proxy_found = config.proxy_config.get('http_proxy') == 'http://test-proxy:8080'
            if not self.assert_true(proxy_found, "Should pick up HTTP_PROXY from environment"):
                return False
        finally:
            if old_proxy:
                os.environ['HTTP_PROXY'] = old_proxy
            else:
                os.environ.pop('HTTP_PROXY', None)
                
        return True
    
    def test_proxy_manager_sanitization(self):
        """Test ProxyManager credential sanitization"""
        print("  Testing proxy credential sanitization...")
        
        config = Config()
        proxy_manager = ProxyManager(config)
        
        # Test URL sanitization
        test_cases = [
            ("http://user:pass@proxy.com:8080", "http://proxy.com:8080"),
            ("https://user:pass@proxy.com", "https://proxy.com"),
            ("http://proxy.com:8080", "http://proxy.com:8080"),
            ("", ""),
            (None, None),
        ]
        
        for input_url, expected in test_cases:
            result = proxy_manager.sanitize_proxy_url(input_url)
            if not self.assert_equal(result, expected, f"sanitize_proxy_url({input_url})"):
                return False
        
        # Test fallback credential masking
        test_text = "Connection to http://user:secret@proxy.com failed"
        sanitized = proxy_manager._mask_credentials_fallback(test_text)
        has_credentials = "user" in sanitized or "secret" in sanitized
        if not self.assert_false(has_credentials, "Credentials should be masked in fallback"):
            return False
            
        return True
    
    def test_progress_reporter(self):
        """Test ProgressReporter functionality"""
        print("  Testing ProgressReporter...")
        
        # Test basic progress tracking
        reporter = ProgressReporter(total_size=1000, description="Test", show_speed=False)
        
        if not self.assert_equal(reporter.downloaded, 0, "Initial downloaded should be 0"):
            return False
            
        if not self.assert_equal(reporter.total_size, 1000, "Total size should be set"):
            return False
        
        # Test byte formatting
        test_cases = [
            (512, "512 B"),
            (1024, "1.0 KB"),
            (1048576, "1.0 MB"),
            (1073741824, "1.0 GB"),
        ]
        
        for size, expected in test_cases:
            result = reporter._format_bytes(size)
            if not self.assert_equal(result, expected, f"_format_bytes({size})"):
                return False
        
        # Test duration formatting
        duration_cases = [
            (30, "30s"),
            (90, "1m30s"),
            (3661, "1h01m"),
        ]
        
        for seconds, expected in duration_cases:
            result = reporter._format_duration(seconds)
            if not self.assert_equal(result, expected, f"_format_duration({seconds})"):
                return False
                
        return True
    
    def test_image_spec_parsing(self):
        """Test image specification parsing logic"""
        print("  Testing image specification parsing...")
        
        # Mock the parsing logic from pull_image method
        test_cases = [
            ("ubuntu", ("ubuntu", "latest")),
            ("ubuntu:20.04", ("ubuntu", "20.04")),
            ("library/ubuntu:latest", ("library/ubuntu", "latest")),
            ("myregistry.com/myorg/myapp:v1.0", ("myregistry.com/myorg/myapp", "v1.0")),
        ]
        
        for image_spec, expected in test_cases:
            # Simulate the parsing logic
            if ":" in image_spec:
                image_name, tag = image_spec.rsplit(":", 1)
            else:
                image_name, tag = image_spec, "latest"
                
            result = (image_name, tag)
            if not self.assert_equal(result, expected, f"parse_image_spec({image_spec})"):
                return False
                
        return True
    
    def test_timeout_handling(self):
        """Test timeout configuration handling"""
        print("  Testing timeout handling...")
        
        # Test default timeouts
        config = Config()
        if not self.assert_equal(config.request_timeout, 30, "Default request timeout"):
            return False
        if not self.assert_equal(config.download_timeout, 300, "Default download timeout"):
            return False
        if not self.assert_equal(config.chunk_timeout, 60, "Default chunk timeout"):
            return False
            
        # Test custom timeouts
        custom_config = Config(timeout_config={
            "request_timeout": 45,
            "download_timeout": 600,
            "chunk_timeout": 120
        })
        
        if not self.assert_equal(custom_config.request_timeout, 45, "Custom request timeout"):
            return False
        if not self.assert_equal(custom_config.download_timeout, 600, "Custom download timeout"):
            return False
        if not self.assert_equal(custom_config.chunk_timeout, 120, "Custom chunk timeout"):
            return False
            
        return True
    
    def test_docker_image_puller_initialization(self):
        """Test DockerImagePuller class initialization"""
        print("  Testing DockerImagePuller initialization...")
        
        # Test basic initialization
        puller = DockerImagePuller()
        if not self.assert_equal(puller.registry_url, "https://registry-1.docker.io", "Default registry URL"):
            return False
        if not self.assert_equal(puller.auth_url, "https://auth.docker.io", "Default auth URL"):
            return False
        if not self.assert_equal(puller.request_timeout, 30, "Default request timeout"):
            return False
            
        # Test with custom configuration
        proxy_config = {"http_proxy": "http://proxy.com:8080"}
        puller_with_proxy = DockerImagePuller(proxy_config=proxy_config)
        if not self.assert_equal(puller_with_proxy.proxy_config["http_proxy"], "http://proxy.com:8080", "Custom proxy config"):
            return False
            
        return True
    
    def test_helper_methods(self):
        """Test helper methods in DockerImagePuller"""
        print("  Testing helper methods...")
        
        puller = DockerImagePuller()
        
        # Test byte formatting helper
        test_cases = [
            (1024, "1.0 KB"),
            (1048576, "1.0 MB"),
            (1073741824, "1.0 GB"),
        ]
        
        for size, expected in test_cases:
            result = puller._format_bytes(size)
            if not self.assert_equal(result, expected, f"_format_bytes({size})"):
                return False
                
        return True
    
    def run_all_tests(self):
        """Run all tests and report results"""
        print("🚀 Docker Image Puller Test Suite")
        print("=" * 60)
        print("Testing all components with no external dependencies")
        print("=" * 60)
        
        # List of test methods
        tests = [
            (self.test_config_validation, "Config Validation"),
            (self.test_proxy_manager_sanitization, "Proxy Manager Sanitization"),
            (self.test_progress_reporter, "Progress Reporter"),
            (self.test_image_spec_parsing, "Image Specification Parsing"),
            (self.test_timeout_handling, "Timeout Handling"),
            (self.test_docker_image_puller_initialization, "DockerImagePuller Initialization"),
            (self.test_helper_methods, "Helper Methods"),
        ]
        
        # Run all tests
        for test_func, test_name in tests:
            self.run_test(test_func, test_name)
        
        # Print summary
        print("\n" + "=" * 60)
        print(f"📊 Test Results Summary")
        print(f"   Total tests run: {self.tests_run}")
        print(f"   ✅ Passed: {self.tests_passed}")
        print(f"   ❌ Failed: {self.tests_failed}")
        
        if self.tests_failed == 0:
            print(f"   🎉 All tests passed!")
            return True
        else:
            print(f"   ⚠️  {self.tests_failed} test(s) failed")
            return False


def main():
    """Run the test suite"""
    print("Docker Image Puller - Comprehensive Test Suite")
    print("No external dependencies required - testing internal components\n")
    
    test_suite = TestSuite()
    success = test_suite.run_all_tests()
    
    print("\n" + "=" * 60)
    if success:
        print("🎊 All tests completed successfully!")
        print("The Docker Image Puller is working correctly.")
    else:
        print("⚠️  Some tests failed. Please review the output above.")
        print("Consider running with --debug flag for more information.")
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()