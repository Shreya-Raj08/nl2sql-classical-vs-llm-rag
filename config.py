"""Central configuration for the NL-to-SQL project (paths, model names, settings)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# ---- Spider dataset -------------------------------------------------------
SPIDER_DIR = ROOT / "data" / "spider_data"
SPIDER_DB_DIR = SPIDER_DIR / "database"            # one folder per database, each with <db_id>.sqlite
SPIDER_TABLES = SPIDER_DIR / "tables.json"         # schema of every database
SPIDER_TRAIN = SPIDER_DIR / "train_spider.json"    # 7,000 training questions (RAG example pool)
SPIDER_DEV = SPIDER_DIR / "dev.json"               # 1,034 dev questions on 20 unseen databases (test set)

# Official Spider evaluation scripts (used only for the Easy/Medium/Hard/Extra difficulty label)
SPIDER_EVAL_DIR = ROOT / "test-suite-sql-eval"

# ---- Demo database ----------------------------------------------------------
DEMO_DB = "college_2"

# ---- LLM (local, via Ollama) ------------------------------------------------
LLM_MODEL = "qwen2.5-coder:7b"
LLM_OPTIONS = {"temperature": 0, "num_ctx": 8192, "seed": 42}
LLM_MAX_FIX_ATTEMPTS = 1           # self-correction: retry once if SQLite reports an error

# ---- RAG (dynamic few-shot examples) ----------------------------------------
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
RAG_TOP_K = 3
RAG_INDEX_DIR = ROOT / "data" / "rag_index"

# ---- Execution safety --------------------------------------------------------
QUERY_TIMEOUT_SEC = 10
MAX_RESULT_ROWS = 500

# ---- Outputs -----------------------------------------------------------------
RESULTS_DIR = ROOT / "results"
CACHE_DIR = ROOT / "data" / "cache"

# The four systems compared in this project
SYSTEMS = {
    "classical": "S1: Classical NLP",
    "nlp_llm": "S2: NLP + LLM",
    "nlp_llm_rag": "S3: NLP + LLM + RAG",
    "llm_rag": "Baseline: LLM + RAG",
}
