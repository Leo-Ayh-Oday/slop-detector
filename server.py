"""Codebase Q&A — Ask questions about any GitHub repo"""
import json, os, re, shutil, tempfile, logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn, requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
BASE_URL = "https://api.deepseek.com/v1"

from slop_detector import SlopDetector, _extract_git_data
slop = SlopDetector()

# Load activation codes (SHA-256 hashes)
ACTIVATION_CODES: set[str] = set()
_codes_path = Path(__file__).parent / "activation_codes.json"
if _codes_path.exists():
    try:
        data = json.loads(_codes_path.read_text(encoding="utf-8"))
        ACTIVATION_CODES = set(data.get("codes", []))
    except Exception:
        logger.warning("Failed to load activation_codes.json")

# ── Pydantic models ──

class IndexRequest(BaseModel): repo_url: str; branch: str = "main"
class AskRequest(BaseModel): question: str; settings: dict = {}
class Settings(BaseModel): api_key: str = ""; model: str = "deepseek-v4-pro"
class SlopRequest(BaseModel): repo_url: str; branch: str = "main"
class ActivateRequest(BaseModel): activation_code: str

# ── Global state ──

class RepoState:
    def __init__(self):
        self.repo_path: Path | None = None
        self.chunks: list[dict] = []
        self.bm25 = None
        self.indexed = False
        self.repo_url = ""

state = RepoState()

# ── Code chunking with tree-sitter ──

def chunk_python(source: str, filepath: str) -> list[dict]:
    """Extract functions and classes from Python source using tree-sitter"""
    try:
        from tree_sitter import Language, Parser
        import tree_sitter_python as tspython
        lang = Language(tspython.language())
        parser = Parser(lang)
        tree = parser.parse(bytes(source, "utf8"))
    except ImportError:
        return _fallback_chunk(source, filepath)
    except Exception as e:
        logger.warning(f"Parse error {filepath}: {e}")
        return _fallback_chunk(source, filepath)

    chunks = []
    lines = source.split("\n")

    def extract_block(node):
        name_node = node.child_by_field_name("name")
        name = name_node.text.decode("utf8") if name_node else "<anonymous>"
        code = source[node.start_byte:node.end_byte]
        docstring = ""
        body = node.child_by_field_name("body")
        if body and body.named_child_count > 0:
            first = body.named_children[0]
            if first.type == "expression_statement":
                s = first.text.decode("utf8")
                if s.startswith('"""') or s.startswith("'''"):
                    docstring = s.strip('"').strip("'")[:200]

        chunks.append({
            "file": filepath,
            "type": node.type,
            "name": name,
            "start": node.start_point[0] + 1,
            "end": node.end_point[0] + 1,
            "code": code,
            "doc": docstring,
        })

    def walk(node):
        if node.type in ("function_definition", "class_definition", "method_definition"):
            extract_block(node)
        elif node.type == "decorated_definition":
            for child in node.children:
                if child.type in ("function_definition", "class_definition"):
                    extract_block(child)
        else:
            for child in node.children:
                walk(child)

    walk(tree.root_node)

    # Module-level code (imports, globals) as one chunk
    if chunks:
        first_start = min(c["start"] for c in chunks)
        if first_start > 3:
            header = "\n".join(lines[:first_start-1])
            if header.strip():
                chunks.insert(0, {"file": filepath, "type": "module_header", "name": "(imports & globals)",
                                  "start": 1, "end": first_start-1, "code": header, "doc": ""})
    return chunks


def chunk_javascript(source: str, filepath: str) -> list[dict]:
    """Extract functions and classes from JS/TS"""
    try:
        from tree_sitter import Language, Parser
        import tree_sitter_javascript as tsjs
        lang = Language(tsjs.language())
        parser = Parser(lang)
        tree = parser.parse(bytes(source, "utf8"))
    except (ImportError, Exception):
        return _fallback_chunk(source, filepath)

    chunks = []
    target_types = {"function_declaration", "method_definition", "class_declaration",
                    "arrow_function", "function_expression"}

    def walk(node):
        if node.type in target_types:
            name_node = node.child_by_field_name("name")
            name = name_node.text.decode("utf8") if name_node else "<anonymous>"
            code = source[node.start_byte:node.end_byte]
            chunks.append({"file": filepath, "type": node.type, "name": name,
                           "start": node.start_point[0]+1, "end": node.end_point[0]+1,
                           "code": code, "doc": ""})
        for child in node.children:
            walk(child)

    walk(tree.root_node)
    return chunks


def _fallback_chunk(source: str, filepath: str) -> list[dict]:
    """Line-based fallback for unsupported languages"""
    lines = source.split("\n")
    chunks = []
    current = []
    for i, line in enumerate(lines):
        current.append(line)
        if len(current) >= 30 or line.strip().startswith(("def ", "class ", "function ", "export ")):
            code = "\n".join(current)
            if code.strip():
                chunks.append({"file": filepath, "type": "code_block", "name": f"lines {i-len(current)+2}-{i+1}",
                               "start": i-len(current)+2, "end": i+1, "code": code, "doc": ""})
            current = []
    if current:
        code = "\n".join(current)
        if code.strip():
            chunks.append({"file": filepath, "type": "code_block", "name": f"lines {len(lines)-len(current)+1}-{len(lines)}",
                           "start": len(lines)-len(current)+1, "end": len(lines), "code": code, "doc": ""})
    return chunks


def chunk_file(filepath: Path, relative: str) -> list[dict]:
    ext = filepath.suffix.lower()
    try:
        source = filepath.read_text(encoding="utf-8", errors="ignore")
        if len(source) > 500000:
            return _fallback_chunk(source, relative)
    except:
        return []

    if ext == ".py":
        return chunk_python(source, relative)
    elif ext in (".js", ".ts", ".jsx", ".tsx"):
        return chunk_javascript(source, relative)
    elif ext in (".md", ".rst", ".txt"):
        return [{"file": relative, "type": "document", "name": filepath.name,
                 "start": 1, "end": source.count("\n")+1, "code": source, "doc": ""}]
    elif ext in (".go", ".rs", ".java", ".c", ".cpp", ".h", ".cs", ".rb", ".php"):
        return _fallback_chunk(source, relative)
    return []


SKIP_EXTS = {".png",".jpg",".gif",".svg",".ico",".woff",".ttf",".eot",".mp3",".mp4",
             ".zip",".tar",".gz",".pyc",".class",".o",".so",".dll",".exe",".bin",
             ".lock",".sum",".min.js",".min.css",".map"}
SKIP_DIRS = {"node_modules","__pycache__",".git",".venv","venv","dist","build",
             ".next",".turbo","target",".gradle"}


def index_repo(repo_path: Path):
    state.chunks = []
    state.repo_path = repo_path
    files = list(repo_path.rglob("*"))
    total = min(len(files), 5000)
    logger.info(f"Indexing {total} files from {repo_path}")

    for i, fp in enumerate(files[:5000]):
        if fp.suffix.lower() in SKIP_EXTS: continue
        if any(d in fp.parts for d in SKIP_DIRS): continue
        if not fp.is_file(): continue
        try:
            rel = str(fp.relative_to(repo_path)).replace("\\", "/")
            chunks = chunk_file(fp, rel)
            state.chunks.extend(chunks)
        except: pass

    logger.info(f"Indexed {len(state.chunks)} chunks")

    # Build BM25 index
    try:
        from rank_bm25 import BM25Okapi
        tokenized = [_tokenize(c["code"]) for c in state.chunks]
        state.bm25 = BM25Okapi(tokenized)
        state.indexed = True
    except ImportError:
        state.indexed = False
        logger.warning("rank_bm25 not installed")


def _tokenize(text: str) -> list[str]:
    """Code-aware tokenization"""
    text = text.replace("(", " ( ").replace(")", " ) ").replace("[", " [ ").replace("]", " ] ")
    text = text.replace("{", " { ").replace("}", " } ").replace(":", " : ").replace(".", " . ")
    text = text.replace("=", " = ").replace(",", " , ").replace("->", " -> ")
    return [t.lower() for t in text.split() if len(t) > 0]


# ── LLM call ──

def ask_llm(question: str, chunks: list[dict], settings: dict) -> str:
    model = settings.get("model") or "deepseek-v4-pro"
    api_key = settings.get("api_key") or API_KEY
    if not api_key:
        return "Error: No API key. Set DEEPSEEK_API_KEY or add key in Settings."

    context = ""
    for i, c in enumerate(chunks[:8]):
        context += f"\n[{i+1}] {c['file']}:{c['start']}-{c['end']} ({c['type']} {c['name']})\n```\n{c['code'][:2000]}\n```\n"

    system = """You answer questions about a codebase. Given relevant code snippets, explain the answer clearly.
For each claim, cite the file path and line numbers from the context.
If the answer cannot be found in the provided code, say so honestly.
Format code references as `file.py:10-25`."""

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Codebase context:\n{context[:12000]}\n\nQuestion: {question}"}
    ]

    try:
        r = requests.post(
            f"{BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": messages, "temperature": 0.3, "max_tokens": 2048},
            timeout=60
        )
        if r.status_code != 200: return f"API Error: {r.status_code}"
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Error: {e}"


# ── API endpoints ──

def _get_ui_path():
    base = Path(__file__).parent
    import sys
    if getattr(sys, 'frozen', False):
        base = Path(sys._MEIPASS)
    return base / "ui.html"


@app.get("/", response_class=HTMLResponse)
async def index():
    content = _get_ui_path().read_text(encoding="utf-8")
    return Response(content=content, media_type="text/html",
                    headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.post("/api/index")
async def index_endpoint(req: IndexRequest):
    if not req.repo_url:
        raise HTTPException(400, "repo_url required")

    tmp = tempfile.mkdtemp(prefix="qa_")
    try:
        import git
        git.Repo.clone_from(req.repo_url, tmp, branch=req.branch, depth=1)
    except Exception as e:
        shutil.rmtree(tmp, ignore_errors=True)
        raise HTTPException(400, f"Clone failed: {e}")

    index_repo(Path(tmp))
    state.repo_url = req.repo_url
    return {"status": "ok", "chunks": len(state.chunks), "repo": req.repo_url}


@app.post("/api/ask")
async def ask_endpoint(req: AskRequest):
    if not state.indexed:
        raise HTTPException(400, "No repo indexed. Index a repo first.")

    tokenized_query = _tokenize(req.question)
    scores = state.bm25.get_scores(tokenized_query)
    top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:10]
    top_chunks = [state.chunks[i] for i in top_indices if scores[i] > 0]

    if not top_chunks:
        return {"answer": "No relevant code found for this question.", "chunks": []}

    answer = ask_llm(req.question, top_chunks, req.settings or {})
    return {"answer": answer, "chunks": [
        {"file": c["file"], "start": c["start"], "end": c["end"],
         "type": c["type"], "name": c["name"], "snippet": c["code"][:500]}
        for c in top_chunks[:5]
    ], "repo": state.repo_url}


@app.get("/api/status")
async def status():
    return {"indexed": state.indexed, "chunks": len(state.chunks), "repo": state.repo_url}


@app.post("/api/slop")
async def slop_endpoint(req: SlopRequest):
    """Analyze a GitHub repo for AI-generated slop patterns."""
    if not req.repo_url:
        raise HTTPException(400, "repo_url required")

    tmp = tempfile.mkdtemp(prefix="slop_")
    try:
        import git
        git.Repo.clone_from(req.repo_url, tmp, branch=req.branch, depth=50)
    except Exception as e:
        shutil.rmtree(tmp, ignore_errors=True)
        raise HTTPException(400, f"Clone failed: {e}")

    repo_path = Path(tmp)
    git_data = _extract_git_data(repo_path)
    report = slop.analyze(repo_path, git_data=git_data)
    report["repo"] = req.repo_url

    # Cleanup temp dir
    shutil.rmtree(tmp, ignore_errors=True)
    return report


@app.post("/api/activate")
async def activate_endpoint(req: ActivateRequest):
    """Validate an activation code."""
    import hashlib
    code_hash = hashlib.sha256(req.activation_code.strip().encode()).hexdigest()
    if code_hash in ACTIVATION_CODES:
        return {"valid": True, "message": "Activated successfully. Unlimited analyses unlocked."}
    return {"valid": False, "message": "Invalid activation code. Please check and try again."}


if __name__ == "__main__":
    print("Codebase Q&A + AI Slop Detector → http://localhost:8766")
    uvicorn.run(app, host="0.0.0.0", port=8766)
