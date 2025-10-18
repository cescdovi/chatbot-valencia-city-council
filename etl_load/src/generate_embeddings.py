from config.common_settings import settings
from config.setup_logging import setup_logging
from typing import Dict
import openai
class OpenAIEmbeddingsGenerator:
    def __init__(self,
                 model = settings.EMBEDDINGS_MODEL):

        self.client = openai.OpenAI(api_key = settings.OPENAI_API_KEY)
        self.embeddings_model = model
       
    def embed_query(self, text: list[str]) -> list[list[float]]:
        resp = self.client.embeddings.create(
            model=self.embeddings_model, 
            input=text)
        return resp.data[0].embedding




        