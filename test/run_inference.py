"""
Quick script to run inference with different optimization modes
"""

import subprocess
import sys
import os
from pathlib import Path

def run_inference(model_path, test_file="test.csv", mode="default"):
    """
    Run inference with different optimization modes.
    
    Args:
        model_path: Path to the saved model
        test_file: Path to test CSV file
        mode: One of ["default", "fp16", "quantized", "all"]
    """
    
    # Check if model exists
    if not os.path.exists(model_path):
        print(f"Error: Model path does not exist: {model_path}")
        print("\nAvailable models:")
        models_dir = Path("models/balanced")
        if models_dir.exists():
            for item in models_dir.iterdir():
                if item.is_dir() and "complete" in item.name:
                    print(f"  - {item}")
        else:
            print("  No models found in models/balanced/")
        return
    
    # Check if test file exists
    if not os.path.exists(test_file):
        print(f"Error: Test file does not exist: {test_file}")
        return
    
    print("="*60)
    print(f"Running Inference - Mode: {mode.upper()}")
    print("="*60)
    print(f"Model: {model_path}")
    print(f"Test File: {test_file}")
    print()
    
    base_cmd = [
        sys.executable, 
        "inference.py",
        "--model_path", model_path,
        "--test_file", test_file,
        "--batch_size", "16"
    ]
    
    if mode == "default":
        # Run with default settings
        output_file = "inference_results_default.txt"
        cmd = base_cmd + ["--output_file", output_file]
        print("Running with default settings (no optimizations)...")
        
    elif mode == "fp16":
        # Run with FP16 mixed precision
        output_file = "inference_results_fp16.txt"
        cmd = base_cmd + ["--use_fp16", "--output_file", output_file]
        print("Running with FP16 mixed precision (GPU only)...")
        
    elif mode == "quantized":
        # Run with quantization
        output_file = "inference_results_quantized.txt"
        cmd = base_cmd + ["--use_quantization", "--output_file", output_file]
        print("Running with dynamic quantization (CPU only)...")
        
    elif mode == "all":
        # Run all modes sequentially
        print("Running all optimization modes...\n")
        run_inference(model_path, test_file, "default")
        print("\n" + "="*60 + "\n")
        run_inference(model_path, test_file, "fp16")
        print("\n" + "="*60 + "\n")
        run_inference(model_path, test_file, "quantized")
        return
    
    else:
        print(f"Error: Unknown mode '{mode}'")
        print("Available modes: default, fp16, quantized, all")
        return
    
    # Run the inference
    try:
        subprocess.run(cmd, check=True)
        print(f"\n✓ Results saved to: {output_file}")
    except subprocess.CalledProcessError as e:
        print(f"\n✗ Error running inference: {e}")
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Run inference with optimization modes")
    parser.add_argument(
        "--model_path",
        type=str,
        default="models/balanced/microsoft_codebert-base_complete",
        help="Path to saved model directory"
    )
    parser.add_argument(
        "--test_file",
        type=str,
        default="test.csv",
        help="Path to test CSV file"
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="default",
        choices=["default", "fp16", "quantized", "all"],
        help="Optimization mode to use"
    )
    
    args = parser.parse_args()
    
    run_inference(args.model_path, args.test_file, args.mode)
