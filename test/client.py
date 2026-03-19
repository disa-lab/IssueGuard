"""
Test Client for Secret Detection API
=====================================
Simple client to test the modular FastAPI server.

Usage:
    python client.py
    python client.py --file issue.txt
    python client.py --url http://localhost:8000
"""

import requests
import json
import argparse
from pathlib import Path


class SecretDetectionClient:
    """Client for interacting with the Secret Detection API."""
    
    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        """
        Initialize the client.
        
        Args:
            base_url: Base URL of the API server
        """
        self.base_url = base_url.rstrip('/')
    
    def health_check(self) -> dict:
        """
        Check if the API is healthy.
        
        Returns:
            Health check response
        """
        response = requests.get(f"{self.base_url}/health")
        response.raise_for_status()
        return response.json()
    
    def detect_secrets(
        self,
        text: str,
        max_results: int = None,
        batch_size: int = 32
    ) -> dict:
        """
        Detect secrets in text.
        
        Args:
            text: Text to analyze
            max_results: Maximum number of results
            batch_size: Batch size for inference
        
        Returns:
            Detection results
        """
        payload = {
            "text": text,
            "batch_size": batch_size
        }
        
        if max_results is not None:
            payload["max_results"] = max_results
        
        response = requests.post(
            f"{self.base_url}/detect",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        return response.json()
    
    def get_info(self) -> dict:
        """
        Get API information.
        
        Returns:
            API info
        """
        response = requests.get(f"{self.base_url}/")
        response.raise_for_status()
        return response.json()


def print_header(title: str):
    """Print a formatted header."""
    print("\n" + "="*70)
    print(title)
    print("="*70)


def print_secrets(result: dict):
    """Print detected secrets in a formatted way."""
    if not result['secrets']:
        print("\n✓ No secrets detected in the text.")
        return
    
    print(f"\n{'='*70}")
    print("DETECTED SECRETS (Ranked by Confidence)")
    print('='*70)
    
    for idx, secret in enumerate(result['secrets'], 1):
        print(f"\n{idx}. Type: {secret['secret_type']}")
        
        # Truncate long strings
        candidate = secret['candidate_string']
        if len(candidate) > 80:
            candidate = candidate[:80] + "..."
        print(f"   Candidate: {candidate}")
        
        print(f"   Position: {secret['position_start']}-{secret['position_end']}")
        print(f"   Source: {secret['source']} (Pattern ID: {secret['pattern_id']})")


def run_tests(client: SecretDetectionClient):
    """Run a series of tests on the API."""
    
    print_header("Testing Secret Detection API")
    
    # Test 1: Health Check
    print("\n1. Testing Health Check...")
    try:
        health = client.health_check()
        print("✓ Health check passed")
        print(f"   Status: {health['status']}")
        print(f"   Device: {health['device']}")
        print(f"   Patterns loaded: {health['patterns_loaded']}")
    except requests.exceptions.ConnectionError:
        print("✗ Cannot connect to server. Is it running?")
        print("  Start the server with: python main.py")
        return
    except Exception as e:
        print(f"✗ Health check failed: {e}")
        return
    
    # Test 2: API Info
    print("\n2. Testing API Info...")
    try:
        info = client.get_info()
        print("✓ API info retrieved")
        print(f"   Message: {info['message']}")
        print(f"   Version: {info.get('version', 'N/A')}")
    except Exception as e:
        print(f"✗ Failed to get API info: {e}")
    
    # Test 3: Secret Detection with sample text
    print("\n3. Testing Secret Detection...")
    
    sample_text = """
    Here's my configuration:
    API_KEY=sk-1234567890abcdef1234567890abcdef
    DATABASE_URL=postgresql://user:MyP@ssw0rd123@localhost:5432/mydb
    AWS_SECRET_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
    GITHUB_TOKEN=ghp_xxxxxxxxxxxx
    
    Contact: john.doe@example.com
    GitHub: github.com/johndoe
    """
    
    try:
        result = client.detect_secrets(
            text=sample_text,
            max_results=10
        )
        
        print("✓ Detection completed successfully")
        print(f"   Total candidates: {result['total_candidates']}")
        print(f"   Secrets detected: {result['secrets_detected']}")
        print(f"   Detection rate: {result['detection_rate']:.2f}%")
        
        print_secrets(result)
        
    except Exception as e:
        print(f"✗ Detection failed: {e}")
    
    # Test 4: Empty text handling
    print("\n4. Testing with minimal text...")
    
    try:
        result = client.detect_secrets(
            text="Hello world"
        )
        
        print(f"✓ Handled minimal text: {result['secrets_detected']} secrets")
        
    except Exception as e:
        print(f"✗ Failed: {e}")
    
    print_header("Testing completed!")


def test_with_file(client: SecretDetectionClient, file_path: str):
    """Test API with text from a file."""
    
    print_header(f"Testing with file: {file_path}")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()
        
        print(f"\nFile size: {len(text)} characters")
        
        result = client.detect_secrets(
            text=text
        )
        
        print(f"\n✓ Detection completed")
        print(f"   Total candidates: {result['total_candidates']}")
        print(f"   Secrets detected: {result['secrets_detected']}")
        print(f"   Detection rate: {result['detection_rate']:.2f}%")
        
        print_secrets(result)
        
    except FileNotFoundError:
        print(f"✗ File not found: {file_path}")
    except Exception as e:
        print(f"✗ Error: {e}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Test client for Secret Detection API",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--url",
        type=str,
        default="http://127.0.0.1:8000",
        help="Base URL of the API server (default: http://127.0.0.1:8000)"
    )
    parser.add_argument(
        "--file",
        type=str,
        help="Path to file containing text to analyze"
    )
    
    args = parser.parse_args()
    
    # Create client
    client = SecretDetectionClient(args.url)
    
    if args.file:
        # Test with file
        test_with_file(client, args.file)
    else:
        # Run standard tests
        run_tests(client)


if __name__ == "__main__":
    main()
