"""
Retrieval Method Implementations
================================
Four retrieval methods for comparison experiment:

R0: Ours Full - Hybrid Neuro-Symbolic (exact match registry + vector search + fallback)
R1: Naive RAG - Pure vector search, no exact match, no symbolic rules
R2: Critique-RAG - Pre-analysis → Vector search → LLM critique → re-retrieve (inspired by Self-RAG, Asai et al. 2024)
R3: CRAG - Vector search → rule-based quality assessment → corrective retrieval
"""

import os
import sys
import json
import re
from typing import Dict, Any, Optional, List
from pathlib import Path

eda_dir = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(eda_dir))

import retriever_final_merged as retriever_module

# ================= API Config =================
API_KEY = os.environ.get("EDA_API_KEY", "")
BASE_URL = os.environ.get("EDA_BASE_URL", "")
MODEL_NAME = os.environ.get("EDA_MODEL_NAME", "deepseek-ai/DeepSeek-V3.2")


class BaseRetrievalWrapper:
    """Base class for all retrieval methods."""

    def get_name(self) -> str:
        raise NotImplementedError

    def search_component(self, query_text: str) -> Dict[str, Any]:
        """Search for a component. Returns {"status": ..., "data": ...}"""
        raise NotImplementedError

    def _call_llm(self, system_prompt: str, user_message: str, temperature: float = 0.1) -> Optional[str]:
        """Direct LLM call."""
        try:
            from openai import OpenAI
            client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=temperature,
                max_tokens=512,
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"   [LLM Error]: {e}")
            return None


# ================= R0: Ours Full =================

class OursRetrieval(BaseRetrievalWrapper):
    """Hybrid Neuro-Symbolic: exact match registry + vector search + fallback."""

    def __init__(self):
        self.retriever = retriever_module.IntelligentRetriever(enable_exact_match=True)

    def get_name(self) -> str:
        return "Ours (Hybrid Neuro-Symbolic)"

    def search_component(self, query_text: str) -> Dict[str, Any]:
        return self.retriever.search_component(query_text)


# ================= R1: Naive RAG =================

class NaiveRAGRetrieval(BaseRetrievalWrapper):
    """Pure vector search. No exact match, no symbolic rules, no query optimization."""

    def __init__(self):
        self.retriever = retriever_module.IntelligentRetriever(enable_exact_match=False)

    def get_name(self) -> str:
        return "Naive RAG (Vector Only)"

    def search_component(self, query_text: str) -> Dict[str, Any]:
        # Bypass exact match and _optimize_query, go straight to vector search
        return self._pure_vector_search(query_text)

    def _pure_vector_search(self, query_text: str) -> Dict[str, Any]:
        """Pure vector search without any symbolic enhancement."""
        try:
            embed = self.retriever.model.encode([query_text]).tolist()
            results = self.retriever.collection.query(
                query_embeddings=embed,
                n_results=15,
                include=["metadatas", "distances"]
            )

            if not results['ids'] or len(results['ids'][0]) == 0:
                return {"status": "not_found", "data": None}

            # Take top result by distance (closest match)
            best_meta = results['metadatas'][0][0]
            best_dist = results['distances'][0][0]
            best_score = max(0.0, 1.0 - best_dist)

            # Parse pins
            pins_data = []
            if "pins_json" in best_meta:
                try:
                    pins_data = json.loads(best_meta["pins_json"])
                except:
                    pass

            data = {
                "lib_id": best_meta.get("lib_id", "Unknown"),
                "source_library": best_meta.get("source_library", ""),
                "description": best_meta.get("description", ""),
                "raw_symbol_definition": best_meta.get("raw_symbol_definition", ""),
                "pins": pins_data,
                "match_score": round(best_score, 4),
            }
            return {"status": "success", "data": data}

        except Exception as e:
            print(f"   [Naive RAG Error]: {e}")
            return {"status": "error", "data": None, "reason": str(e)}


# ================= R2: Critique-RAG =================
# Inspired by Self-RAG (Asai et al., ICLR 2024) — adapted for EDA component retrieval.
# Key adaptation: adds pre-retrieval query analysis (domain-specific) before the
# retrieve → critique → rewrite loop, since EDA queries have distinct precision tiers
# (exact part numbers vs. generic component types).

CRITIQUE_PRE_ANALYSIS_PROMPT = """Analyze this electronic component search query and classify its precision tier.

Query: {query}

Tiers:
- "exact": Precise part number (e.g., LM2904, 2N3904, 1N4733A) — requires strict match
- "specific": Functional description (e.g., "NPN transistor", "zener diode 5.1V") — moderate match ok
- "generic": Common component type (e.g., Resistor, Capacitor, VCC, GND, LED) — loose match acceptable

Output ONLY a JSON: {{"tier": "<exact|specific|generic>", "threshold": <1-5>, "reasoning": "<brief>"}}
Threshold guide: exact=4, specific=3, generic=2"""

CRITIQUE_EVAL_PROMPT = """Evaluate whether the retrieved electronic component matches the search query.

Search query: {query}
Retrieved component: {lib_id}
Description: {description}
Precision tier: {tier} (minimum acceptable score: {threshold})

Score the match on a scale of 1-5:
1 = completely wrong (different component category)
3 = somewhat related (same category but different specific type)
5 = excellent match

Output ONLY a JSON: {{"score": <1-5>, "relevant": <true/false>, "explanation": "<brief>"}}"""

CRITIQUE_REWRITE_PROMPT = """The search query "{query}" did not find a good match (score: {score}/{threshold}).
Rewrite the query to use more general or alternative electronic component terminology.

Examples:
- "LED" -> "Light emitting diode"
- "LM2904" -> "dual operational amplifier"
- "1N4733A" -> "zener diode 5.1V"
- "2N3904" -> "NPN transistor general purpose"

Output ONLY the rewritten query text, nothing else."""


class CritiqueRAGRetrieval(BaseRetrievalWrapper):
    """
    Critique-RAG retrieval (inspired by Self-RAG, Asai et al., ICLR 2024).
    Pre-analysis → Vector search → LLM critique relevance → re-retrieve with refined query.

    Key adaptation for EDA: adds a pre-retrieval query tier analysis so that
    critique thresholds adapt to query specificity (exact part numbers need
    stricter matching than generic component types).
    """

    def __init__(self, max_retries: int = 1):
        self.max_retries = max_retries
        self.retriever = retriever_module.IntelligentRetriever(enable_exact_match=False)

    def get_name(self) -> str:
        return "Critique-RAG"

    def _analyze_query_tier(self, query_text: str) -> tuple:
        """Pre-retrieval analysis: classify query precision tier and set threshold."""
        # Fast path: common generic components
        q_lower = query_text.lower().strip()
        generics = {"resistor", "capacitor", "inductor", "vcc", "gnd", "power supply",
                    "connector", "switch", "diode", "led"}
        if q_lower in generics:
            return "generic", 2

        # LLM analysis for ambiguous queries
        analysis_raw = self._call_llm(
            "You are an EDA query classifier. Output ONLY valid JSON.",
            CRITIQUE_PRE_ANALYSIS_PROMPT.format(query=query_text),
            temperature=0.1
        )
        if not analysis_raw:
            return "specific", 3  # Default: moderate threshold

        try:
            analysis = json.loads(analysis_raw)
        except json.JSONDecodeError:
            m = re.search(r'\{[^}]*\}', analysis_raw, re.DOTALL)
            if m:
                try:
                    analysis = json.loads(m.group(0))
                except:
                    return "specific", 3
            else:
                return "specific", 3

        tier = analysis.get("tier", "specific")
        threshold = analysis.get("threshold", 3)
        return tier, threshold

    def search_component(self, query_text: str) -> Dict[str, Any]:
        # Step 0: Pre-retrieval query analysis
        tier, threshold = self._analyze_query_tier(query_text)
        print(f"   [Critique-RAG] Query tier: {tier} (threshold={threshold})")

        # Step 1: Initial vector search
        result = self._vector_search(query_text)

        if result.get("status") != "success":
            return result

        # Step 2: LLM critique with tier-aware threshold
        data = result["data"]
        lib_id = data.get("lib_id", "")
        desc = data.get("description", "")

        eval_prompt = CRITIQUE_EVAL_PROMPT.format(
            query=query_text, lib_id=lib_id, description=desc,
            tier=tier, threshold=threshold
        )

        eval_raw = self._call_llm(
            "You are a component retrieval evaluator. Output ONLY valid JSON.",
            eval_prompt
        )

        if not eval_raw:
            return result

        # Parse evaluation
        try:
            eval_data = json.loads(eval_raw)
        except json.JSONDecodeError:
            match = re.search(r'\{[^}]*\}', eval_raw, re.DOTALL)
            if match:
                try:
                    eval_data = json.loads(match.group(0))
                except:
                    return result
            else:
                return result

        score = eval_data.get("score", 3)
        relevant = eval_data.get("relevant", score >= threshold)

        if relevant and score >= threshold:
            return result

        # Step 3: Rewrite query and re-retrieve
        if self.max_retries > 0:
            rewrite_prompt = CRITIQUE_REWRITE_PROMPT.format(
                query=query_text, score=score, threshold=threshold
            )
            new_query = self._call_llm(
                "You are a query reformulation assistant.",
                rewrite_prompt,
                temperature=0.3
            )

            if new_query and new_query.strip() != query_text:
                new_query = new_query.strip().strip('"').strip("'")
                print(f"   [Critique-RAG] Re-retrieving with: '{new_query}'")
                retry_result = self._vector_search(new_query)
                if retry_result.get("status") == "success":
                    return retry_result

        return result

    def _vector_search(self, query_text: str) -> Dict[str, Any]:
        """Pure vector search without symbolic enhancement."""
        try:
            embed = self.retriever.model.encode([query_text]).tolist()
            results = self.retriever.collection.query(
                query_embeddings=embed,
                n_results=15,
                include=["metadatas", "distances"]
            )

            if not results['ids'] or len(results['ids'][0]) == 0:
                return {"status": "not_found", "data": None}

            best_meta = results['metadatas'][0][0]
            best_dist = results['distances'][0][0]
            best_score = max(0.0, 1.0 - best_dist)

            pins_data = []
            if "pins_json" in best_meta:
                try:
                    pins_data = json.loads(best_meta["pins_json"])
                except:
                    pass

            data = {
                "lib_id": best_meta.get("lib_id", "Unknown"),
                "source_library": best_meta.get("source_library", ""),
                "description": best_meta.get("description", ""),
                "raw_symbol_definition": best_meta.get("raw_symbol_definition", ""),
                "pins": pins_data,
                "match_score": round(best_score, 4),
            }
            return {"status": "success", "data": data}

        except Exception as e:
            print(f"   [Critique-RAG Vector Error]: {e}")
            return {"status": "error", "data": None, "reason": str(e)}


# ================= R3: CRAG =================

class CRAGRetrieval(BaseRetrievalWrapper):
    """Corrective RAG (Yan et al., ICLR 2024) adapted with hybrid EDA quality rules."""

    def __init__(self):
        self.retriever = retriever_module.IntelligentRetriever(enable_exact_match=False)

    def get_name(self) -> str:
        return "CRAG (Corrective RAG)"

    def search_component(self, query_text: str) -> Dict[str, Any]:
        # Step 1: Initial vector search
        result = self._pure_vector_search(query_text)

        if result.get("status") != "success":
            return self._corrective_search(query_text)

        # Step 2: Rule-based quality assessment
        data = result["data"]
        lib_id = data.get("lib_id", "")
        score = data.get("match_score", 0)
        quality = self._assess_quality(query_text, lib_id, score)

        if quality == "high":
            return result  # Accept
        elif quality == "medium":
            # Try to improve with larger candidate pool
            return self._corrective_search(query_text, n_results=30)
        else:
            # Low quality: aggressive corrective search
            expanded_queries = self._expand_queries(query_text)
            for exp_query in expanded_queries:
                improved = self._corrective_search(exp_query, n_results=30)
                if improved.get("status") == "success":
                    improved_data = improved.get("data", {})
                    improved_score = improved_data.get("match_score", 0)
                    if improved_score > score:
                        return improved
            return result

    def _assess_quality(self, query: str, lib_id: str, score: float) -> str:
        """
        Hybrid quality assessment: embedding similarity + domain rules.

        Uses both vector-space proximity (score) and symbolic rules (keyword &
        substring matching) to classify match quality. This bridges the gap
        between pure rule-based assessment and learned evaluators.
        """
        q_lower = query.lower().strip()
        lib_lower = lib_id.lower().strip()

        # ===== Tier 1: Symbolic exact/substring matching =====
        if q_lower == lib_lower:
            return "high"
        if q_lower in lib_lower or lib_lower in q_lower:
            return "high"

        # ===== Tier 2: Compute embedding similarity between query and lib_id =====
        # This captures semantic proximity that substring matching misses.
        # Example: "operational amplifier" vs "LM2904" — no substring overlap
        # but they are semantically close in the embedding space.
        semantic_bonus = 0.0
        try:
            q_embed = self.retriever.model.encode([query])[0]
            lib_embed = self.retriever.model.encode([lib_id])[0]
            # Cosine similarity via dot product (both are normalized)
            semantic_sim = float(sum(a * b for a, b in zip(q_embed, lib_embed)))
            # Map from [-1, 1] to [0, 0.3] bonus
            semantic_bonus = max(0.0, (semantic_sim - 0.5) * 0.6)
        except Exception:
            pass  # Fallback to rule-only if embedding fails

        # Combined score = vector similarity + semantic bonus
        combined = score + semantic_bonus

        # ===== Tier 3: Domain-category thresholds =====
        generic_types = ["r", "c", "l", "d", "resistor", "capacitor", "inductor",
                        "diode", "led", "vcc", "gnd", "connector"]
        is_generic = any(t in q_lower for t in generic_types)

        if is_generic:
            if combined > 0.55:
                return "high"
            elif combined > 0.25:
                return "medium"
            return "low"
        else:
            # Specific components (chips, transistors, regulators, etc.)
            if combined > 0.65:
                return "high"
            elif combined > 0.35:
                return "medium"
            return "low"

    def _expand_queries(self, query: str) -> List[str]:
        """Generate expanded query variants for corrective search."""
        q = query.strip()
        variants = []

        # Add common electronics vocabulary expansions
        expansions = {
            "led": "Light emitting diode",
            "resistor": "R",
            "capacitor": "C",
            "inductor": "L",
            "diode": "D",
            "opamp": "operational amplifier",
            "op-amp": "operational amplifier",
            "regulator": "voltage regulator",
            "zener": "zener diode",
            "npn": "NPN transistor",
            "pnp": "PNP transistor",
        }

        q_lower = q.lower()
        for key, expansion in expansions.items():
            if key in q_lower:
                variants.append(expansion)

        # Also try the original query (in case abbreviation expansion helps)
        if variants:
            variants.insert(0, q)

        return variants

    def _corrective_search(self, query_text: str, n_results: int = 30) -> Dict[str, Any]:
        """Corrective search with expanded candidate pool."""
        try:
            embed = self.retriever.model.encode([query_text]).tolist()
            results = self.retriever.collection.query(
                query_embeddings=embed,
                n_results=n_results,
                include=["metadatas", "distances"]
            )

            if not results['ids'] or len(results['ids'][0]) == 0:
                return {"status": "not_found", "data": None}

            # Rerank: pick best based on similarity + keyword heuristics
            best_idx = 0
            best_score = 0
            for i in range(len(results['ids'][0])):
                dist = results['distances'][0][i]
                score = 1.0 - dist

                # Keyword bonus
                meta = results['metadatas'][0][i]
                lib_id = meta.get("lib_id", "").lower()
                keywords = meta.get("keywords", "")
                if isinstance(keywords, str):
                    try:
                        keywords = [k.strip().lower() for k in keywords.split(',')]
                    except:
                        keywords = []
                elif not isinstance(keywords, list):
                    keywords = []

                q_words = set(query_text.lower().split())
                kw_set = set(keywords)
                if q_words.intersection(kw_set):
                    score += 3.0

                if score > best_score:
                    best_score = score
                    best_idx = i

            best_meta = results['metadatas'][0][best_idx]
            pins_data = []
            if "pins_json" in best_meta:
                try:
                    pins_data = json.loads(best_meta["pins_json"])
                except:
                    pass

            data = {
                "lib_id": best_meta.get("lib_id", "Unknown"),
                "source_library": best_meta.get("source_library", ""),
                "description": best_meta.get("description", ""),
                "raw_symbol_definition": best_meta.get("raw_symbol_definition", ""),
                "pins": pins_data,
                "match_score": round(best_score, 4),
            }
            return {"status": "success", "data": data}

        except Exception as e:
            print(f"   [CRAG Error]: {e}")
            return {"status": "error", "data": None, "reason": str(e)}

    def _pure_vector_search(self, query_text: str) -> Dict[str, Any]:
        """Same as NaiveRAG's pure vector search (no symbolic enhancement)."""
        try:
            embed = self.retriever.model.encode([query_text]).tolist()
            results = self.retriever.collection.query(
                query_embeddings=embed,
                n_results=15,
                include=["metadatas", "distances"]
            )

            if not results['ids'] or len(results['ids'][0]) == 0:
                return {"status": "not_found", "data": None}

            best_meta = results['metadatas'][0][0]
            best_dist = results['distances'][0][0]
            best_score = max(0.0, 1.0 - best_dist)

            pins_data = []
            if "pins_json" in best_meta:
                try:
                    pins_data = json.loads(best_meta["pins_json"])
                except:
                    pass

            data = {
                "lib_id": best_meta.get("lib_id", "Unknown"),
                "source_library": best_meta.get("source_library", ""),
                "description": best_meta.get("description", ""),
                "raw_symbol_definition": best_meta.get("raw_symbol_definition", ""),
                "pins": pins_data,
                "match_score": round(best_score, 4),
            }
            return {"status": "success", "data": data}

        except Exception as e:
            print(f"   [CRAG Vector Error]: {e}")
            return {"status": "error", "data": None, "reason": str(e)}


# ================= Factory =================

def create_retrieval_method(method_type: str) -> BaseRetrievalWrapper:
    """Factory function for retrieval methods."""
    methods = {
        "Ours": OursRetrieval,
        "NaiveRAG": NaiveRAGRetrieval,
        "CritiqueRAG": CritiqueRAGRetrieval,
        "CRAG": CRAGRetrieval,
    }

    if method_type not in methods:
        raise ValueError(f"Unknown retrieval method: {method_type}. Available: {list(methods.keys())}")

    return methods[method_type]()
