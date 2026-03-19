"""
Test Client for Secret Detection API
=====================================
Simple client to test the FastAPI server.

Usage:
    python test_client.py
"""

import requests
import json


def test_api(base_url="http://127.0.0.1:8000"):
    """Test the Secret Detection API."""
    
    print("="*70)
    print("Testing Secret Detection API")
    print("="*70)
    
    # Test 1: Health Check
    print("\n1. Testing Health Check...")
    try:
        response = requests.get(f"{base_url}/health")
        if response.status_code == 200:
            print("✓ Health check passed")
            print(json.dumps(response.json(), indent=2))
        else:
            print(f"✗ Health check failed: {response.status_code}")
            return
    except requests.exceptions.ConnectionError:
        print("✗ Cannot connect to server. Is it running?")
        print("  Start the server with: python fastapi_server.py")
        return
    
    # Test 2: Root Endpoint
    print("\n2. Testing Root Endpoint...")
    response = requests.get(f"{base_url}/")
    print("✓ Root endpoint response:")
    print(json.dumps(response.json(), indent=2))
    
    # Test 3: Secret Detection with sample text
    print("\n3. Testing Secret Detection...")
    
    sample_text = """
    Here's my configuration:
    API_KEY=sk-1234567890abcdef1234567890abcdef
    DATABASE_URL=postgresql://user:MyP@ssw0rd123@localhost:5432/mydb
    AWS_SECRET_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
    
    Also, you can contact me at john.doe@example.com
    My GitHub is github.com/johndoe
    """
    
    payload = {
        "text": sample_text,
        "confidence_threshold": 0.5,
        "max_results": 10
    }
    
    try:
        response = requests.post(
            f"{base_url}/detect",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            result = response.json()
            print("✓ Detection completed successfully")
            print(f"\nTotal candidates found: {result['total_candidates']}")
            print(f"Secrets detected: {result['secrets_detected']}")
            print(f"Detection rate: {result['detection_rate']:.2f}%")
            
            if result['secrets']:
                print(f"\n{'='*70}")
                print("Detected Secrets:")
                print('='*70)
                for idx, secret in enumerate(result['secrets'], 1):
                    print(f"\n{idx}. Type: {secret['secret_type']}")
                    print(f"   String: {secret['candidate_string'][:80]}{'...' if len(secret['candidate_string']) > 80 else ''}")
                    print(f"   Confidence: {secret['confidence_score']:.4f} ({secret['confidence_score']*100:.2f}%)")
                    print(f"   Position: {secret['position_start']}-{secret['position_end']}")
            else:
                print("\nNo secrets detected in the sample text.")
        else:
            print(f"✗ Detection failed: {response.status_code}")
            print(response.text)
    
    except Exception as e:
        print(f"✗ Error during detection: {e}")
    
    # Test 4: Test with different confidence threshold
    print("\n4. Testing with higher confidence threshold (0.8)...")
    
    payload['confidence_threshold'] = 0.8
    
    try:
        response = requests.post(
            f"{base_url}/detect",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✓ High-confidence secrets: {result['secrets_detected']}")
        else:
            print(f"✗ Request failed: {response.status_code}")
    
    except Exception as e:
        print(f"✗ Error: {e}")
    
    print("\n" + "="*70)
    print("Testing completed!")
    print("="*70)


def test_with_file(file_path, base_url="http://127.0.0.1:8000"):
    """Test API with text from a file."""
    
    print(f"\nTesting with file: {file_path}")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()
        
        payload = {
            "text": text,
            "confidence_threshold": 0.5
        }
        
        response = requests.post(
            f"{base_url}/detect",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✓ Secrets detected: {result['secrets_detected']}")
            
            if result['secrets']:
                for idx, secret in enumerate(result['secrets'], 1):
                    print(f"{idx}. {secret['secret_type']}: {secret['candidate_string'][:50]}...")
        else:
            print(f"✗ Request failed: {response.status_code}")
    
    except FileNotFoundError:
        print(f"✗ File not found: {file_path}")
    except Exception as e:
        print(f"✗ Error: {e}")


if __name__ == "__main__":
    import sys
    
    base_url = "http://127.0.0.1:8000"
    
    if len(sys.argv) > 1:
        # Test with file if provided
        test_with_file(sys.argv[1], base_url)
    else:
        # Run standard tests
        test_api(base_url)
