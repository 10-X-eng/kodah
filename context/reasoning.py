import httpx
import json
import logging
from core.config import settings

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class Reasoning:
    def __init__(self, model_name: str, context_str: str):
        self.model_name = model_name
        self.context_str = context_str  # Receive context directly here
        self.api_url = settings.OLLAMA_API_URL
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))

    async def perform_chain_of_thought_reasoning(self, query: str):
        logger.debug(f"Starting reasoning for query: {query}")

        # Step 1: Generate initial response from LLM using query and context
        initial_response = await self.generate_initial_response(query)

        # Step 2: Critic analyzes the initial response with the context
        critic_analysis = await self.analyze_with_critic(initial_response)

        # Step 3: Responder responds to Critic's feedback
        responder_response = await self.respond_to_critic(critic_analysis)

        # Step 4: Generate the final answer based on Critic's and Responder's responses
        final_answer = await self.generate_final_answer(critic_analysis, responder_response)

        # Stream back the chain of thought
        yield {
            "type": "chain",
            "role": "critic",
            "content": critic_analysis
        }

        yield {
            "type": "chain",
            "role": "responder",
            "content": responder_response
        }

        yield {
            "type": "final",
            "content": final_answer
        }

    async def generate_initial_response(self, query: str):
        # Generate the LLM's initial response based on the context + query
        combined_prompt = f"Context: {self.context_str}\nUser query: {query}"
        response = await self.client.post(
            f"{self.api_url}/api/chat",
            json={"model": self.model_name, "messages": [{"role": "user", "content": combined_prompt}], "stream": False}
        )
        return response.json().get("message", {}).get("content", "")

    async def analyze_with_critic(self, initial_response: str):
        # Critic analyzes the initial response, considering context
        critic_prompt = f"Critic, analyze this response:\n{initial_response}\nContext: {self.context_str}"
        response = await self.client.post(
            f"{self.api_url}/api/chat",
            json={"model": self.model_name, "messages": [{"role": "system", "content": critic_prompt}], "stream": False}
        )
        return response.json().get("message", {}).get("content", "")

    async def respond_to_critic(self, critic_analysis: str):
        # Responder responds to Critic's analysis, incorporating context
        responder_prompt = f"Responder, reply to the Critic's analysis:\n{critic_analysis}\nContext: {self.context_str}"
        response = await self.client.post(
            f"{self.api_url}/api/chat",
            json={"model": self.model_name, "messages": [{"role": "system", "content": responder_prompt}], "stream": False}
        )
        return response.json().get("message", {}).get("content", "")

    async def generate_final_answer(self, critic_analysis: str, responder_response: str):
        # Generate the final answer based on Critic's and Responder's dialogues
        final_answer_prompt = f"Final answer based on the following:\nCritic: {critic_analysis}\nResponder: {responder_response}\nContext: {self.context_str}"
        response = await self.client.post(
            f"{self.api_url}/api/chat",
            json={"model": self.model_name, "messages": [{"role": "system", "content": final_answer_prompt}], "stream": False}
        )
        return response.json().get("message", {}).get("content", "")

    async def close(self):
        await self.client.aclose()

