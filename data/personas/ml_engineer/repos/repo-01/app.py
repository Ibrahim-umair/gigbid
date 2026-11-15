import os
import sys
import psycopg
from pypdf import PdfReader
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_text_splitters import RecursiveCharacterTextSplitter

DB = os.environ["DATABASE_URL"]
emb = OpenAIEmbeddings(model=os.getenv("EMBED_MODEL", "text-embedding-3-small"))
llm = ChatOpenAI(model=os.getenv("LLM_MODEL", "gpt-4o-mini"), temperature=0)
splitter = RecursiveCharacterTextSplitter(chunk_size=900, chunk_overlap=120,
                                          separators=["\n## ", "\n\n", "\n", " "])

PROMPT = """Answer the question using ONLY the passages below.
If the passages do not contain the answer, reply exactly: I could not find this in the policies.
Cite as [title, p.N].

Passages:
{passages}

Question: {q}"""


def ingest(folder):
    with psycopg.connect(DB) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.execute("""CREATE TABLE IF NOT EXISTS chunks (
            id serial PRIMARY KEY, title text, page int, effective date, body text, v vector(1536))""")
        for name in os.listdir(folder):
            if not name.endswith(".pdf"):
                continue
            reader = PdfReader(os.path.join(folder, name))
            for pno, page in enumerate(reader.pages, 1):
                for piece in splitter.split_text(page.extract_text() or ""):
                    vec = emb.embed_query(piece)
                    conn.execute(
                        "INSERT INTO chunks (title, page, body, v) VALUES (%s,%s,%s,%s::vector)",
                        (name[:-4], pno, piece, str(vec)))
        conn.commit()


def ask(question, k=8):
    qv = str(emb.embed_query(question))
    with psycopg.connect(DB) as conn:
        rows = conn.execute(
            "SELECT title, page, body FROM chunks ORDER BY v <=> %s::vector LIMIT %s", (qv, k)).fetchall()
    passages = "\n\n".join(f"[{t}, p.{p}] {b}" for t, p, b in rows)
    return llm.invoke(PROMPT.format(passages=passages, q=question)).content


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "ingest":
        ingest(sys.argv[2])
    elif cmd == "ask":
        print(ask(sys.argv[2]))
