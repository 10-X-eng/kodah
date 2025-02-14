import tiktoken
import torch

class TikTokenWrapper:
    """
    A simple wrapper for tiktoken to mimic a Hugging Face tokenizer interface.
    
    This class provides an __call__ method for encoding text into token IDs
    and a decode method for converting token IDs back into text.
    """
    def __init__(self, model_name: str = "gpt-3.5-turbo"):
        # Load the tiktoken encoder for the specified model.
        self.encoder = tiktoken.encoding_for_model(model_name)

    def __call__(self, text: str, return_tensors: str = None):
        # Encode the text into token IDs.
        tokens = self.encoder.encode(text)
        if return_tensors == "pt":
            # Return as a dictionary with a tensor (as expected by many models).
            return {"input_ids": torch.tensor([tokens], dtype=torch.long)}
        return tokens

    def decode(self, token_ids, skip_special_tokens: bool = True):
        # Decode token IDs back into a string.
        return self.encoder.decode(token_ids)
