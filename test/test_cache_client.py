"""
Cache Test Client for Secret Detection API
===========================================
Tests the LRU caching functionality by sending duplicate requests
with the same context windows to demonstrate cache efficiency.

Usage:
    python test_cache_client.py
"""

import asyncio
import aiohttp
import time
import json
from typing import List, Dict
from collections import defaultdict


class CacheTestClient:
    """Client for testing the caching functionality of the Secret Detection API."""
    
    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        """
        Initialize the cache test client.
        
        Args:
            base_url: Base URL of the API server
        """
        self.base_url = base_url.rstrip('/')
    
    async def detect_secrets(
        self,
        session: aiohttp.ClientSession,
        text: str,
        request_id: int = None
    ) -> Dict:
        """
        Detect secrets in text.
        
        Args:
            session: aiohttp client session
            text: Text to analyze
            request_id: Optional request identifier for logging
        
        Returns:
            Detection results with timing info
        """
        payload = {
            "text": text,
            "batch_size": 32
        }
        
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
            'request_id': request_id,
            'result': result,
            'elapsed_time': elapsed
        }
    
    async def run_cache_test(self):
        """Run comprehensive cache test with duplicate requests."""
        print("="*80)
        print("SECRET DETECTION API - LRU CACHE TEST")
        print("="*80)
        
        # Test samples - some with duplicate context windows
        test_samples = [
            {
                'text': 'My API key is sk_test_4eC39HqLyjWDarjtT1zdp7dc for production use',
                'label': 'Sample 1 - First occurrence'
            },
            {
                'text': 'The password is MySecretP@ss123 and token is ghp_1234567890abcdefghijklmnopqrstuv',
                'label': 'Sample 2 - First occurrence'
            },
            {
                'text': 'My API key is sk_test_4eC39HqLyjWDarjtT1zdp7dc for production use',
                'label': 'Sample 1 - DUPLICATE (should use cache)'
            },
            {
                'text': 'Database connection: postgres://user:pass@localhost:5432/db',
                'label': 'Sample 3 - First occurrence'
            },
            {
                'text': 'The password is MySecretP@ss123 and token is ghp_1234567890abcdefghijklmnopqrstuv',
                'label': 'Sample 2 - DUPLICATE (should use cache)'
            },
            {
                'text': 'My API key is sk_test_4eC39HqLyjWDarjtT1zdp7dc for production use',
                'label': 'Sample 1 - DUPLICATE AGAIN (should use cache)'
            },
            {
                'text': 'JWT token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U',
                'label': 'Sample 4 - First occurrence'
            },
            {
                'text': 'Database connection: postgres://user:pass@localhost:5432/db',
                'label': 'Sample 3 - DUPLICATE (should use cache)'
            },
        ]
        
        async with aiohttp.ClientSession() as session:
            # Health check
            print("\n[1] Checking API health...")
            try:
                async with session.get(f"{self.base_url}/health") as response:
                    if response.status == 200:
                        health = await response.json()
                        print(f"✓ API is healthy")
                        print(f"  - Model loaded: {health.get('model_loaded')}")
                        print(f"  - Device: {health.get('device')}")
                        print(f"  - Patterns loaded: {health.get('patterns_loaded')}")
            except Exception as e:
                print(f"✗ API health check failed: {e}")
                print("\nMake sure the API server is running:")
                print("  python main.py")
                return
            
            # Run test requests
            print("\n[2] Running cache test with duplicate requests...")
            print("="*80)
            
            results = []
            cache_stats_history = []
            
            for idx, sample in enumerate(test_samples, 1):
                print(f"\nRequest #{idx}: {sample['label']}")
                print(f"Text: {sample['text'][:60]}...")
                
                try:
                    result = await self.detect_secrets(
                        session,
                        sample['text'],
                        request_id=idx
                    )
                    results.append(result)
                    
                    response_data = result['result']
                    cache_stats = response_data.get('cache_stats', {})
                    cache_stats_history.append(cache_stats)
                    
                    print(f"  Time: {result['elapsed_time']*1000:.2f}ms")
                    print(f"  Candidates: {response_data['total_candidates']}")
                    print(f"  Secrets: {response_data['secrets_detected']}")
                    print(f"  Cache hits: {cache_stats.get('hits', 0)}")
                    print(f"  Cache misses: {cache_stats.get('misses', 0)}")
                    print(f"  Hit rate: {cache_stats.get('hit_rate', 0):.2f}%")
                    
                    # Show which candidates were from cache
                    all_candidates = response_data.get('all_candidates', [])
                    cached_count = sum(1 for c in all_candidates if c.get('from_cache', False))
                    new_count = len(all_candidates) - cached_count
                    print(f"  From cache: {cached_count}/{len(all_candidates)} candidates")
                    print(f"  New inference: {new_count}/{len(all_candidates)} candidates")
                    
                except Exception as e:
                    print(f"✗ Request failed: {e}")
            
            # Summary
            print("\n" + "="*80)
            print("TEST SUMMARY")
            print("="*80)
            
            if results:
                times = [r['elapsed_time'] for r in results]
                print(f"\nTotal requests: {len(results)}")
                print(f"Average time: {sum(times)/len(times)*1000:.2f}ms")
                print(f"Min time: {min(times)*1000:.2f}ms")
                print(f"Max time: {max(times)*1000:.2f}ms")
                
                # Show cache effectiveness
                if cache_stats_history:
                    final_stats = cache_stats_history[-1]
                    print(f"\nFinal Cache Statistics:")
                    print(f"  Total cache hits: {final_stats.get('hits', 0)}")
                    print(f"  Total cache misses: {final_stats.get('misses', 0)}")
                    print(f"  Overall hit rate: {final_stats.get('hit_rate', 0):.2f}%")
                
                # Show duplicate detection benefit
                print("\n" + "-"*80)
                print("CACHE BENEFIT ANALYSIS")
                print("-"*80)
                
                # Group by text to identify duplicates
                text_groups = defaultdict(list)
                for idx, sample in enumerate(test_samples):
                    text_groups[sample['text']].append((idx, results[idx] if idx < len(results) else None))
                
                for text, requests in text_groups.items():
                    if len(requests) > 1:
                        print(f"\nDuplicate text: {text[:50]}...")
                        print(f"  Sent {len(requests)} times:")
                        for idx, result in requests:
                            if result:
                                print(f"    Request #{idx+1}: {result['elapsed_time']*1000:.2f}ms")
                        
                        if all(r[1] for r in requests):
                            times = [r[1]['elapsed_time'] for r in requests]
                            first_time = times[0]
                            avg_cached_time = sum(times[1:]) / len(times[1:]) if len(times) > 1 else 0
                            speedup = (first_time / avg_cached_time) if avg_cached_time > 0 else 0
                            print(f"    First request: {first_time*1000:.2f}ms")
                            print(f"    Cached requests avg: {avg_cached_time*1000:.2f}ms")
                            print(f"    Speedup: {speedup:.2f}x faster")
                
                # Show detailed results for one request
                print("\n" + "="*80)
                print("SAMPLE DETAILED RESPONSE (Request #1)")
                print("="*80)
                if results:
                    sample_result = results[0]['result']
                    print(f"\nTotal candidates found: {sample_result['total_candidates']}")
                    print(f"Secrets detected: {sample_result['secrets_detected']}")
                    print(f"\nAll candidates with labels:")
                    for i, candidate in enumerate(sample_result.get('all_candidates', [])[:5], 1):
                        print(f"  {i}. Candidate: {candidate['candidate_string']}")
                        print(f"     Type: {candidate['secret_type']}")
                        print(f"     Is Secret: {candidate['is_secret']}")
                        print(f"     Position: {candidate['position_start']}-{candidate['position_end']}")
                        print(f"     From Cache: {candidate.get('from_cache', False)}")
                    
                    if len(sample_result.get('all_candidates', [])) > 5:
                        print(f"  ... and {len(sample_result['all_candidates']) - 5} more")
            
            print("\n" + "="*80)
            print("TEST COMPLETE")
            print("="*80)


async def main():
    """Main entry point."""
    client = CacheTestClient()
    await client.run_cache_test()


if __name__ == "__main__":
    asyncio.run(main())
