# context.py
from typing import List, Dict, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ContextManager:
    def __init__(self, model: str):
        """Initialize context manager with model-specific settings."""
        self.model = model
        self.max_context_length = self._get_model_context_length()
        
    def _get_model_context_length(self) -> int:
        """Get the maximum context length for the specified model."""
        context_lengths = {
            "llama3.2": 8192,
            "llama2": 4096,
            "mistral": 8192,
            "codellama": 16384,
            "neural-chat": 8192,
            "starling-lm": 8192,
            "mistral-openorca": 8192,
            "dolphin-phi": 4096
        }
        base_model = self.model.split(":")[0].lower()
        return context_lengths.get(base_model, 4096)

    def optimize_messages(self, messages: List[Dict[str, str]], system_prompt: Optional[str] = None) -> List[Dict[str, str]]:
        """Optimize message context for the chat completion API."""
        try:
            optimized_messages = []
            total_tokens = 0

            # Always include system prompt if provided
            if system_prompt:
                system_message = {"role": "system", "content": system_prompt}
                system_tokens = self._estimate_tokens([system_message])
                optimized_messages.append(system_message)
                total_tokens += system_tokens

            # Reserve tokens for the next response (approximately 1000 tokens)
            available_tokens = self.max_context_length - 1000

            # Process messages from newest to oldest
            for msg in reversed(messages):
                message = {
                    "role": msg["role"],
                    "content": msg["content"]
                }
                message_tokens = self._estimate_tokens([message])

                if total_tokens + message_tokens <= available_tokens:
                    optimized_messages.insert(1 if system_prompt else 0, message)
                    total_tokens += message_tokens
                else:
                    break

            # Log context window usage
            logger.info(f"Using {total_tokens} tokens out of {self.max_context_length} available for {self.model}")
            return optimized_messages

        except Exception as e:
            logger.error(f"Error optimizing message context: {str(e)}")
            # Fallback to recent messages only
            recent_messages = messages[-5:] if messages else []
            if system_prompt:
                recent_messages.insert(0, {"role": "system", "content": system_prompt})
            return recent_messages

    def _estimate_tokens(self, messages: List[Dict[str, str]]) -> int:
        """
        Estimate token count for messages using character-based heuristic.
        This is intentionally conservative to avoid context overflow.
        """
        total_chars = sum(len(msg["content"]) for msg in messages)
        # Assume average of 3 characters per token for conservative estimate
        char_per_token = 3
        # Add overhead for message formatting (role, quotes, etc)
        message_overhead = len(messages) * 4
        
        return (total_chars // char_per_token) + message_overhead