# context/manager.py
import os
import json
from typing import List, Dict, Optional
import logging
import httpx
import numpy as np
import hnswlib
from sentence_transformers import SentenceTransformer
from core.config import settings

logger = logging.getLogger(__name__)

def get_index_path(chat_id: int) -> str:
    return getattr(settings, "CONTEXT_INDEX_PATH_TEMPLATE", "context_index_{chat_id}.bin").format(chat_id=chat_id)

def get_memory_texts_path(chat_id: int) -> str:
    return getattr(settings, "CONTEXT_TEXTS_PATH_TEMPLATE", "context_texts_{chat_id}.json").format(chat_id=chat_id)

def get_summary_path(chat_id: int) -> str:
    return getattr(settings, "CONTEXT_SUMMARY_PATH_TEMPLATE", "global_summary_{chat_id}.txt").format(chat_id=chat_id)

class ContextManager:
    def __init__(self, model: str, chat_id: int, max_elements: int = 10000):
        """
        Initialize the advanced context manager for a specific chat.
          - Sets up the embedding model.
          - Loads (or creates) an hnswlib index for this chat.
          - Loads any previously stored memory texts and global summary for this chat.
        """
        self.chat_id = chat_id
        self.model = model
        self.max_context_length = settings.get_model_context_length(model)
        logger.info(f"Advanced context manager for chat_id {chat_id} with model {model} and context length {self.max_context_length}")

        # Unique file paths per chat.
        self.index_path = get_index_path(chat_id)
        self.memory_texts_path = get_memory_texts_path(chat_id)
        self.summary_path = get_summary_path(chat_id)

        # Ensure the model is only downloaded once
        model_dir = os.path.expanduser("~/.cache/huggingface/transformers")
        model_path = os.path.join(model_dir, 'sentence-transformers', 'all-mpnet-base-v2')
        
        if not os.path.exists(model_path):
            logger.info(f"Model not found locally at {model_path}. It will be downloaded.")
        
        self.embedder = SentenceTransformer('all-mpnet-base-v2', cache_folder=model_dir)
        self.embedding_dim = self.embedder.get_sentence_embedding_dimension()

        self.index = hnswlib.Index(space='cosine', dim=self.embedding_dim)
        if os.path.exists(self.index_path) and os.path.exists(self.memory_texts_path):
            try:
                self.index.load_index(self.index_path)
                with open(self.memory_texts_path, "r", encoding="utf-8") as f:
                    self.memory_texts = json.load(f)
                logger.info(f"Loaded persisted context for chat_id {chat_id} from disk.")
            except Exception as e:
                logger.error(f"Error loading persisted context for chat_id {chat_id}: {e}")
                self._init_new_index(max_elements)
        else:
            self._init_new_index(max_elements)

        if os.path.exists(self.summary_path):
            with open(self.summary_path, "r", encoding="utf-8") as f:
                self.global_summary = f.read().strip()
        else:
            self.global_summary = ""

    def _init_new_index(self, max_elements: int):
        """Initialize a new index and empty memory."""
        self.index.init_index(max_elements=max_elements, ef_construction=200, M=16)
        self.index.set_ef(50)
        self.memory_texts = []
        logger.info("Initialized new advanced hnswlib index.")

    def save_context(self) -> None:
        """Persist the index and memory texts to disk."""
        try:
            self.index.save_index(self.index_path)
            with open(self.memory_texts_path, "w", encoding="utf-8") as f:
                json.dump(self.memory_texts, f)
            logger.info("Saved context to disk.")
        except Exception as e:
            logger.error(f"Error saving context: {e}")

    def save_global_summary(self) -> None:
        """Persist the global summary to disk."""
        try:
            with open(self.summary_path, "w", encoding="utf-8") as f:
                f.write(self.global_summary)
            logger.info("Saved global summary to disk.")
        except Exception as e:
            logger.error(f"Error saving global summary: {e}")

    def delete_context(self) -> None:
        """Delete all persisted context files for this chat_id."""
        for path in [self.index_path, self.memory_texts_path, self.summary_path]:
            try:
                if os.path.exists(path):
                    os.remove(path)
                    logger.info(f"Deleted file: {path}")
            except Exception as e:
                logger.error(f"Error deleting file {path}: {e}")

    def add_to_memory(self, message: Dict[str, str]) -> None:
        """Compute and add the message embedding to the index and memory_texts; then persist."""
        text = message["content"]
        if text.strip():
            embedding = self.embedder.encode(text, convert_to_numpy=True)
            norm = np.linalg.norm(embedding)
            if norm > 0:
                embedding = embedding / norm
            embedding = np.expand_dims(embedding, axis=0)
            self.index.add_items(embedding)
            self.memory_texts.append(message)
            logger.debug(f"Added message to advanced memory: {text[:50]}...")
            self.save_context()

    def update_global_summary(self, messages: List[Dict[str, str]]) -> None:
        """
        Update the global rolling summary using a summarization API.
        Summarizes all messages older than the last 10 turns.
        """
        if len(messages) > 10:
            to_summarize = messages[:-10]
            conversation_text = "\n".join([f"{m['role']}: {m['content']}" for m in to_summarize])
            prompt = (
                "Summarize the following conversation, keeping all key details:\n\n"
                f"{conversation_text}\n\nSummary:"
            )
            try:
                response = httpx.post(
                    f"{settings.OLLAMA_API_URL}/api/generate",
                    json={"model": self.model, "prompt": prompt, "stream": False},
                    timeout=60.0,
                )
                if response.status_code == 200:
                    data = response.json()
                    summary = data.get("response", "").strip()
                    self.global_summary = summary
                    self.save_global_summary()
                    logger.info("Updated global summary.")
                else:
                    logger.error(f"Global summarization API error: {response.status_code}")
            except Exception as e:
                logger.error(f"Error in global summarization: {e}")

    def retrieve_relevant_context(self, query: str, limit: int = 5) -> List[Dict[str, str]]:
        """Retrieve up to 'limit' messages from the index that are most similar to the query."""
        if not self.memory_texts or self.index.element_count == 0:
            return []
        k = min(limit, self.index.element_count)
        self.index.set_ef(1000)
        embedding = self.embedder.encode(query, convert_to_numpy=True)
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm
        embedding = np.expand_dims(embedding, axis=0)
        labels, _ = self.index.knn_query(embedding, k=k)
        candidates = []
        query_emb = embedding[0]
        for idx in labels[0]:
            if idx < len(self.memory_texts):
                candidate = self.memory_texts[idx]
                candidate_emb = self.embedder.encode(candidate["content"], convert_to_numpy=True)
                cand_norm = np.linalg.norm(candidate_emb)
                if cand_norm > 0:
                    candidate_emb = candidate_emb / cand_norm
                sim = np.dot(query_emb, candidate_emb)
                candidates.append((sim, candidate))
        candidates.sort(key=lambda x: x[0], reverse=True)
        retrieved = [c[1] for c in candidates[:limit]]
        logger.debug(f"Advanced retrieval returned {len(retrieved)} messages for query: {query[:50]}...")
        return retrieved

    def optimize_messages(self, messages: List[Dict[str, str]], system_prompt: Optional[str] = None) -> List[Dict[str, str]]:
        """
        Build the final prompt by combining:
          1. A system prompt.
          2. A global summary of older conversation.
          3. The recent conversation (last 10 messages).
          4. Relevant retrieved context.
        New messages are added to memory.
        """
        if system_prompt and system_prompt.strip():
            base = [{"role": "system", "content": system_prompt}]
        else:
            base = [{"role": "system", "content": "You are a helpful assistant."}]
        
        for msg in messages:
            self.add_to_memory(msg)
        
        self.update_global_summary(messages)
        
        recent = messages[-10:] if len(messages) > 10 else messages
        candidate = base
        if self.global_summary:
            candidate.append({"role": "assistant", "content": f"Summary of earlier conversation: {self.global_summary}"})
        candidate += recent
        
        retrieved = self.retrieve_relevant_context(messages[-1]["content"]) if messages else []
        candidate_with_retrieval = candidate + retrieved
        while self._estimate_tokens(candidate_with_retrieval) > self.max_context_length and retrieved:
            retrieved.pop(0)
            candidate_with_retrieval = candidate + retrieved
        
        return candidate_with_retrieval

    def summarize_context(self, messages: List[Dict[str, str]]) -> str:
        """Summarize the provided messages using the generate endpoint."""
        conversation_text = "\n".join([f"{m['role']}: {m['content']}" for m in messages])
        prompt = (
            "Summarize the following conversation concisely while retaining all important details:\n\n"
            f"{conversation_text}\n\nSummary:"
        )
        try:
            response = httpx.post(
                f"{settings.OLLAMA_API_URL}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False},
                timeout=60.0,
            )
            if response.status_code == 200:
                data = response.json()
                summary = data.get("response", "").strip()
                return summary if summary else "Summary not available."
            else:
                logger.error(f"Summarization API error: {response.status_code}")
                return "Summary not available."
        except Exception as e:
            logger.error(f"Error summarizing conversation: {e}")
            return "Summary not available."

    def _estimate_tokens(self, messages: List[Dict[str, str]]) -> int:
        total_chars = sum(len(m["content"]) for m in messages)
        char_per_token = 3
        message_overhead = len(messages) * 4
        return (total_chars // char_per_token) + message_overhead

    def chunk_text(self, text: str, max_tokens: int, overlap_tokens: int) -> List[str]:
        tokens = text.split()
        if len(tokens) <= max_tokens:
            return [text]
        chunks = []
        start = 0
        while start < len(tokens):
            end = start + max_tokens
            chunk = " ".join(tokens[start:end])
            chunks.append(chunk)
            if end >= len(tokens):
                break
            start += max_tokens - overlap_tokens
        return chunks
