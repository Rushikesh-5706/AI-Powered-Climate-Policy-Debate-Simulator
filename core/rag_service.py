import json
import logging
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

logger = logging.getLogger(__name__)

COUNTRY_COLLECTION_MAP = {
    "USA": "usa_policy.json",
    "EU": "eu_policy.json",
    "China": "china_policy.json",
}

TOP_K = 4


class RAGService:
    def __init__(self, policies_dir: Path) -> None:
        self.policies_dir = policies_dir
        self.client = chromadb.Client()
        self.embedding_fn = embedding_functions.DefaultEmbeddingFunction()
        self.collections: dict[str, chromadb.Collection] = {}

    async def initialize(self) -> None:
        for agent_name, filename in COUNTRY_COLLECTION_MAP.items():
            file_path = self.policies_dir / filename
            if not file_path.exists():
                raise FileNotFoundError(
                    f"Required policy file not found: {file_path}"
                )
            with open(file_path, "r", encoding="utf-8") as f:
                policy = json.load(f)

            chunks = self._chunk_policy(policy)
            collection_name = agent_name.lower() + "_policy"

            collection = self.client.create_collection(
                name=collection_name,
                embedding_function=self.embedding_fn,
            )
            ids = [f"{agent_name}_chunk_{i}" for i in range(len(chunks))]
            collection.add(documents=chunks, ids=ids)
            self.collections[agent_name] = collection
            logger.info(
                "Indexed %d chunks for agent %s", len(chunks), agent_name
            )

    @staticmethod
    def _chunk_policy(policy: dict) -> list[str]:
        chunks: list[str] = []
        for position in policy.get("key_positions", []):
            chunks.append(f"Key position: {position}")
        for red_line in policy.get("red_lines", []):
            chunks.append(f"Red line: {red_line}")
        return chunks

    async def retrieve(
        self,
        agent_name: str,
        query: str,
        history: list[dict],
    ) -> str:
        if agent_name not in self.collections:
            return "No policy context available."

        recent_messages = " ".join(
            entry["message"] for entry in history[-3:]
        )
        composite_query = f"{query} {recent_messages}".strip()

        collection = self.collections[agent_name]
        n = min(TOP_K, collection.count())
        if n == 0:
            return "No policy context available."

        results = collection.query(
            query_texts=[composite_query],
            n_results=n,
        )
        documents: list[str] = results.get("documents", [[]])[0]
        return "\n".join(documents) if documents else "No relevant policy points found."
