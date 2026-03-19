"""
Multiple Client Test for Secret Detection API
==============================================
Tests the API with multiple concurrent clients to verify async handling.

Usage:
    python client_multiple.py
    python client_multiple.py --clients 10
    python client_multiple.py --url http://localhost:8000
"""

import asyncio
import aiohttp
import time
import argparse
from typing import List, Dict
import statistics


class AsyncSecretDetectionClient:
    """Async client for interacting with the Secret Detection API."""
    
    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        """
        Initialize the async client.
        
        Args:
            base_url: Base URL of the API server
        """
        self.base_url = base_url.rstrip('/')
    
    async def health_check(self, session: aiohttp.ClientSession) -> dict:
        """
        Check if the API is healthy.
        
        Args:
            session: aiohttp client session
        
        Returns:
            Health check response
        """
        async with session.get(f"{self.base_url}/health") as response:
            response.raise_for_status()
            return await response.json()
    
    async def detect_secrets(
        self,
        session: aiohttp.ClientSession,
        text: str,
        max_results: int = None,
        batch_size: int = 32,
        client_id: int = None
    ) -> Dict:
        """
        Detect secrets in text.
        
        Args:
            session: aiohttp client session
            text: Text to analyze
            max_results: Maximum number of results
            batch_size: Batch size for inference
            client_id: Optional client identifier for logging
        
        Returns:
            Detection results with timing info
        """
        payload = {
            "text": text,
            "batch_size": batch_size
        }
        
        if max_results is not None:
            payload["max_results"] = max_results
        
        start_time = time.time()
        
        async with session.post(
            f"{self.base_url}/detect",
            json=payload,
            headers={"Content-Type": "application/json"}
        ) as response:
            response.raise_for_status()
            result = await response.json()
        
        end_time = time.time()
        elapsed = end_time - start_time
        
        return {
            'client_id': client_id,
            'result': result,
            'elapsed_time': elapsed,
            'start_time': start_time,
            'end_time': end_time
        }


def print_header(title: str):
    """Print a formatted header."""
    print("\n" + "="*70)
    print(title)
    print("="*70)


async def test_concurrent_requests(
    client: AsyncSecretDetectionClient,
    num_clients: int = 5,
    sample_texts: List[str] = None
):
    """
    Test the API with multiple concurrent requests.
    
    Args:
        client: AsyncSecretDetectionClient instance
        num_clients: Number of concurrent clients to simulate
        sample_texts: List of sample texts (will be cycled)
    """
    
    # Default sample texts if none provided
    if sample_texts is None:
        sample_texts = [
            """
            API_KEY=sk-1234567890abcdef1234567890abcdef
            DATABASE_URL=postgresql://user:MyP@ssw0rd123@localhost:5432/mydb
            """,
            """
            AWS_SECRET_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
            GITHUB_TOKEN=ghp_1234567890abcdefghijklmnopqrstuvwxyz
            """,
            """
            STRIPE_KEY=sk_live_51H1234567890abcdefghijklmnop
            MONGODB_URI=mongodb://admin:SecretP@ss123@localhost:27017/db
            """,
            """
            SLACK_WEBHOOK=https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXX
            JWT_SECRET=my-super-secret-jwt-key-123456789
            """,
            """
            PRIVATE_KEY=-----BEGIN RSA PRIVATE KEY-----
            MIIEpAIBAAKCAQEA1234567890abcdefghijk
            -----END RSA PRIVATE KEY-----
            """
        ]
    
    print_header(f"Testing {num_clients} Concurrent Clients")
    
    # Create aiohttp session
    timeout = aiohttp.ClientTimeout(total=300)  # 5 minutes timeout
    connector = aiohttp.TCPConnector(limit=100)  # Allow many connections
    
    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        
        # First, check if server is healthy
        print("\n1. Checking server health...")
        try:
            health = await client.health_check(session)
            print(f"✓ Server is healthy")
            print(f"   Device: {health['device']}")
            print(f"   Patterns loaded: {health['patterns_loaded']}")
        except Exception as e:
            print(f"✗ Cannot connect to server: {e}")
            print("  Make sure the server is running: python main.py")
            return
        
        # Create tasks for concurrent requests
        print(f"\n2. Launching {num_clients} concurrent requests...")
        
        tasks = []
        overall_start = time.time()
        
        for i in range(num_clients):
            # Cycle through sample texts
            text = sample_texts[i % len(sample_texts)]
            
            task = client.detect_secrets(
                session=session,
                text=text,
                client_id=i + 1
            )
            tasks.append(task)
        
        # Wait for all requests to complete
        print(f"   Waiting for all requests to complete...")
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        overall_end = time.time()
        overall_elapsed = overall_end - overall_start
        
        # Process results
        successful = []
        failed = []
        
        for result in results:
            if isinstance(result, Exception):
                failed.append(result)
            else:
                successful.append(result)
        
        print(f"\n✓ All requests completed!")
        
        # Print statistics
        print_header("Results Summary")
        
        print(f"\nTotal clients: {num_clients}")
        print(f"Successful: {len(successful)}")
        print(f"Failed: {len(failed)}")
        
        if failed:
            print("\nFailed requests:")
            for idx, error in enumerate(failed, 1):
                print(f"  {idx}. {error}")
        
        if successful:
            # Timing statistics
            elapsed_times = [r['elapsed_time'] for r in successful]
            secrets_detected = [r['result']['secrets_detected'] for r in successful]
            
            print(f"\nTiming Statistics:")
            print(f"  Total time: {overall_elapsed:.2f}s")
            print(f"  Average per request: {statistics.mean(elapsed_times):.2f}s")
            print(f"  Min time: {min(elapsed_times):.2f}s")
            print(f"  Max time: {max(elapsed_times):.2f}s")
            print(f"  Median time: {statistics.median(elapsed_times):.2f}s")
            
            if len(elapsed_times) > 1:
                print(f"  Std deviation: {statistics.stdev(elapsed_times):.2f}s")
            
            # Throughput
            requests_per_second = num_clients / overall_elapsed
            print(f"\nThroughput:")
            print(f"  Requests/second: {requests_per_second:.2f}")
            
            # Detection statistics
            print(f"\nDetection Statistics:")
            print(f"  Total secrets detected: {sum(secrets_detected)}")
            print(f"  Average per request: {statistics.mean(secrets_detected):.1f}")
            
            # Show sample results
            print(f"\nSample Results (first 3):")
            for i, r in enumerate(successful[:3], 1):
                result = r['result']
                print(f"\n  Client {r['client_id']}:")
                print(f"    Time: {r['elapsed_time']:.2f}s")
                print(f"    Candidates: {result['total_candidates']}")
                print(f"    Secrets detected: {result['secrets_detected']}")
                print(f"    Detection rate: {result['detection_rate']:.1f}%")
        
        print_header("Test Completed")


async def test_stress(
    client: AsyncSecretDetectionClient,
    num_clients: int = 20,
    waves: int = 3
):
    """
    Stress test with multiple waves of concurrent requests.
    
    Args:
        client: AsyncSecretDetectionClient instance
        num_clients: Number of concurrent clients per wave
        waves: Number of waves to send
    """
    
    print_header(f"Stress Test: {waves} waves × {num_clients} clients")
    
    sample_text = """
    API_KEY=sk-1234567890abcdef1234567890abcdef
    DATABASE_URL=postgresql://user:MyP@ssw0rd123@localhost:5432/mydb
    AWS_SECRET_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
    GITHUB_TOKEN=ghp_1234567890abcdefghijklmnopqrstuvwxyz
    """
    
    timeout = aiohttp.ClientTimeout(total=300)
    connector = aiohttp.TCPConnector(limit=100)
    
    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        
        all_wave_times = []
        
        for wave_num in range(1, waves + 1):
            print(f"\nWave {wave_num}/{waves}:")
            print(f"  Launching {num_clients} requests...")
            
            wave_start = time.time()
            
            tasks = []
            for i in range(num_clients):
                task = client.detect_secrets(
                    session=session,
                    text=sample_text,
                    client_id=f"{wave_num}-{i+1}"
                )
                tasks.append(task)
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            wave_end = time.time()
            wave_elapsed = wave_end - wave_start
            all_wave_times.append(wave_elapsed)
            
            successful = [r for r in results if not isinstance(r, Exception)]
            failed = [r for r in results if isinstance(r, Exception)]
            
            print(f"  ✓ Wave completed in {wave_elapsed:.2f}s")
            print(f"    Successful: {len(successful)}/{num_clients}")
            if failed:
                print(f"    Failed: {len(failed)}")
        
        print_header("Stress Test Summary")
        print(f"\nTotal waves: {waves}")
        print(f"Clients per wave: {num_clients}")
        print(f"Total requests: {waves * num_clients}")
        print(f"\nWave times:")
        for i, t in enumerate(all_wave_times, 1):
            print(f"  Wave {i}: {t:.2f}s")
        print(f"\nAverage wave time: {statistics.mean(all_wave_times):.2f}s")
        print(f"Total time: {sum(all_wave_times):.2f}s")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Multiple client test for Secret Detection API",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--url",
        type=str,
        default="http://127.0.0.1:8000",
        help="Base URL of the API server (default: http://127.0.0.1:8000)"
    )
    parser.add_argument(
        "--clients",
        type=int,
        default=5,
        help="Number of concurrent clients (default: 5)"
    )
    parser.add_argument(
        "--stress",
        action="store_true",
        help="Run stress test with multiple waves"
    )
    parser.add_argument(
        "--waves",
        type=int,
        default=3,
        help="Number of waves for stress test (default: 3)"
    )
    
    args = parser.parse_args()
    
    # Create client
    client = AsyncSecretDetectionClient(args.url)
    
    if args.stress:
        # Run stress test
        await test_stress(client, num_clients=args.clients, waves=args.waves)
    else:
        # Run standard concurrent test
        await test_concurrent_requests(client, num_clients=args.clients)


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())
