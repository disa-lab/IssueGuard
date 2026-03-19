"""
Manager for the ML model and inference operations.
"""

import os
from typing import List, Dict, Optional

import torch
from torch.utils.data import DataLoader, Dataset
from transformers import AutoTokenizer, AutoModelForSequenceClassification

from .utils import clean_text, create_context_window


class PairDataset(Dataset):
    """Dataset for text pair classification."""
    
    def __init__(self, encodings):
        self.encodings = encodings
    
    def __getitem__(self, idx):
        return {key: val[idx].clone().detach() for key, val in self.encodings.items()}
    
    def __len__(self):
        return len(self.encodings['input_ids'])


class ModelManager:
    """Manages the ML model for secret detection."""
    
    def __init__(
        self,
        model_path: str,
        device: Optional[str] = None,
        use_quantization: bool = False,
        max_length: int = 256,
        window_size: int = 200
    ):
        """
        Initialize the model manager.
        
        Args:
            model_path: Path to the trained model
            device: Device to use (cuda/cpu), None for auto-detect
            use_quantization: Whether to use quantization for CPU
            max_length: Maximum sequence length for tokenization
            window_size: Context window size around candidates
        """
        self.model_path = model_path
        self.max_length = max_length
        self.window_size = window_size
        
        # Determine device
        if device:
            self.device = torch.device(device)
        else:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
        print(f"Initializing model on device: {self.device}")
        
        # Load model and tokenizer
        self.model, self.tokenizer = self._load_model(use_quantization)
        print("✓ Model loaded successfully")
    
    def _load_model(self, use_quantization: bool):
        """
        Load the trained model and tokenizer.
        
        Args:
            use_quantization: Whether to apply quantization
        
        Returns:
            Tuple of (model, tokenizer)
        """
        print(f"Loading model from: {self.model_path}")
        
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"Model not found: {self.model_path}")
        
        tokenizer = AutoTokenizer.from_pretrained(self.model_path)
        model = AutoModelForSequenceClassification.from_pretrained(self.model_path)
        
        # Apply quantization if requested (only on CPU)
        if use_quantization and self.device.type == 'cpu':
            print("Applying dynamic quantization for CPU optimization...")
            model = torch.quantization.quantize_dynamic(
                model, 
                {torch.nn.Linear}, 
                dtype=torch.qint8
            )
            print("✓ Quantization applied")
        elif use_quantization and self.device.type == 'cuda':
            print("Warning: Quantization is only supported on CPU. Skipping.")
        
        model.to(self.device)
        model.eval()
        
        return model, tokenizer
    
    def run_inference(
        self,
        text: str,
        candidates: List[Dict],
        batch_size: int = 32
    ) -> List[Dict]:
        """
        Run inference on candidate strings.
        
        Args:
            text: Original text containing the candidates
            candidates: List of candidate dictionaries
            batch_size: Batch size for inference
        
        Returns:
            List of results with predictions and confidence scores
        """
        if not candidates:
            return []
        
        # Clean the text
        cleaned_text = clean_text(text)
        
        # Prepare data
        contexts = []
        candidate_strings = []
        
        for candidate in candidates:
            context = create_context_window(
                cleaned_text, 
                candidate['candidate_string'],
                window_size=self.window_size
            )
            contexts.append(context)
            candidate_strings.append(candidate['candidate_string'])
        
        # Tokenize
        encodings = self.tokenizer(
            contexts,
            candidate_strings,
            padding=True,
            truncation=True,
            return_tensors='pt',
            max_length=self.max_length
        )
        
        # Create dataset and dataloader
        dataset = PairDataset(encodings)
        dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=False)
        
        # Run inference
        all_predictions = []
        
        with torch.no_grad():
            for batch in dataloader:
                input_ids = batch['input_ids'].to(self.device)
                attention_mask = batch['attention_mask'].to(self.device)
                
                kwargs = {
                    "input_ids": input_ids,
                    "attention_mask": attention_mask
                }
                
                if 'token_type_ids' in batch:
                    kwargs['token_type_ids'] = batch['token_type_ids'].to(self.device)
                
                outputs = self.model(**kwargs)
                
                logits = outputs.logits
                predictions = torch.argmax(logits, dim=-1)
                
                all_predictions.extend(predictions.cpu().numpy())
        
        # Combine results with candidate information
        results = []
        for candidate, pred in zip(candidates, all_predictions):
            results.append({
                'candidate_string': candidate['candidate_string'],
                'secret_type': candidate['secret_type'],
                'pattern_id': candidate['pattern_id'],
                'source': candidate['source'],
                'position': candidate['position'],
                'prediction': int(pred),
                'is_secret': bool(pred == 1)
            })
        
        return results
    
    def get_device(self) -> str:
        """Get the device being used."""
        return str(self.device)
