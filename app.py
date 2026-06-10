from flask import Flask, render_template, request, redirect, flash, url_for
import os
from whoosh.index import create_in, open_dir
from whoosh.fields import Schema, TEXT, ID, KEYWORD, STORED
from whoosh.qparser import MultifieldParser, QueryParser
from whoosh.highlight import HtmlFormatter
from werkzeug.utils import secure_filename
import PyPDF2
import docx as python_docx

app = Flask(__name__)
app.secret_key = "secret123"

UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"txt", "pdf", "docx", "doc", "md"}

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

schema = Schema(
    title=TEXT(stored=True),
    content=TEXT(stored=True),
    type=KEYWORD(stored=True),
    path=ID(stored=True)
)

if not os.path.exists("indexdir"):
    os.mkdir("indexdir")
    ix = create_in("indexdir", schema)
else:
    ix = open_dir("indexdir")


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def extract_text(path, ext):
    try:
        if ext in ("txt", "md"):
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        elif ext == "pdf":
            text = ""
            with open(path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text += page.extract_text() or ""
            return text
        elif ext in ("docx", "doc"):
            doc = python_docx.Document(path)
            return "\n".join([p.text for p in doc.paragraphs])
    except Exception as e:
        print(f"Erreur extraction {path}: {e}")
    return ""


def index_file(path, filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "txt"
    content = extract_text(path, ext)
    if not content.strip():
        return False
    writer = ix.writer()
    writer.update_document(title=filename, content=content, type=ext, path=path)
    writer.commit()
    return True


@app.route("/")
def home():
    return render_template("search.html")


@app.route("/search")
def search():
    q = request.args.get("q", "").strip()
    field = request.args.get("field", "all")
    doc_type = request.args.get("type", "all")
    results_list = []
    error = None

    if not q:
        return render_template("results.html", results=[], q=q, error="Entrez un mot-clé.")

    try:
        with ix.searcher() as searcher:
            if field == "title":
                parser = QueryParser("title", schema=ix.schema)
            elif field == "content":
                parser = QueryParser("content", schema=ix.schema)
            else:
                parser = MultifieldParser(["title", "content"], schema=ix.schema)

            query = parser.parse(q)
            results = searcher.search(query, limit=30)
            results.fragmenter.charlimit = None
            results.formatter = HtmlFormatter(tagname="mark")

            for r in results:
                file_type = r["type"].lower()
                if doc_type != "all" and file_type != doc_type.lower():
                    continue
                results_list.append({
                    "title": r.highlights("title") or r["title"],
                    "content": r.highlights("content") or r["content"][:300],
                    "type": file_type
                })
    except Exception as e:
        error = f"Erreur : {e}"

    return render_template("results.html", results=results_list, q=q,
                           field=field, doc_type=doc_type, error=error)


@app.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        files = request.files.getlist("file")
        success = 0
        errors = []
        for file in files:
            if file and file.filename:
                if allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    path = os.path.join(UPLOAD_FOLDER, filename)
                    file.save(path)
                    if index_file(path, filename):
                        success += 1
                    else:
                        errors.append(filename + " (vide)")
                else:
                    errors.append(file.filename + " (type non supporté)")
        if success:
            flash(f"✅ {success} fichier(s) indexé(s) !", "success")
        if errors:
            flash("⚠️ Problème avec : " + ", ".join(errors), "error")
        return redirect(url_for("upload"))
    return render_template("upload.html")


if __name__ == "__main__":
    app.run(debug=True)
