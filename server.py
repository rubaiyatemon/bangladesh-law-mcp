"""
Bangladesh Legal Acts MCP Server

Exposes the Bangladesh Legal Acts Dataset (1,484+ acts scraped from
http://bdlaws.minlaw.gov.bd) over the Model Context Protocol, so any
MCP-compatible client (Claude Desktop, Gemini, GPT, etc.) can query
acts, search across legislation, and pull historical / legal-system
context.

Data layout: one JSON file per act inside the directory pointed to by
the BLA_DATA_DIR env var (default: ../Data/acts relative to this file).

Transport:
  * stdio (default) - local MCP clients such as Claude Desktop, Gemini
    CLI, Cursor, etc.
  * Streamable HTTP - selected via TRANSPORT=http, mounts the MCP
    endpoint at /mcp and a /healthz liveness check alongside it. Used
    when the server is hosted (Fly.io, Docker, etc.).
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP
from starlette.responses import JSONResponse

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# All logs go to stderr so they never corrupt the stdio JSON-RPC stream.
logging.basicConfig(
    level=os.getenv("BLA_LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("bangladesh-law-mcp")

def _resolve_data_dir() -> Path:
    """Find the acts directory.

    Resolution order:
      1. ``BLA_DATA_DIR`` env var (points at ``acts/`` or its parent ``Data/``).
      2. ``<repo>/Data/acts``  - the data submodule layout.
      3. ``<repo>/../Data/acts`` - sibling-clone layout.
      4. ``<repo>/../Bangladesh-Legal-Acts-Dataset/Data/acts`` - default dev layout.
    """
    env = os.getenv("BLA_DATA_DIR")
    if env:
        p = Path(env).resolve()
        if p.is_dir() and p.name == "acts":
            return p
        if p.is_dir() and (p / "acts").is_dir():
            return (p / "acts").resolve()
        # Even if the path doesn't exist yet, honour the env var verbatim
        # so the error message tells the user exactly what was tried.
        return p

    here = Path(__file__).resolve().parent
    candidates = [
        here / "Data" / "acts",  # submodule / vendored
        here.parent / "Data" / "acts",  # sibling clone
        here.parent
        / "Bangladesh-Legal-Acts-Dataset"
        / "Data"
        / "acts",  # default dev layout
    ]
    for c in candidates:
        if c.is_dir():
            return c.resolve()
    # Fall back to the most-likely default so the error message is useful.
    return candidates[0].resolve()


DATA_DIR = _resolve_data_dir()

if not DATA_DIR.is_dir():
    log.error("Acts directory not found: %s", DATA_DIR)
    raise SystemExit(
        f"Acts directory not found: {DATA_DIR}\n"
        "Set the BLA_DATA_DIR environment variable to the path of the "
        "acts/ folder (or its parent Data/ folder), or clone "
        "https://github.com/sakhadib/Bangladesh-Legal-Acts-Dataset as a "
        "sibling of this repository."
    )

log.info("Loading acts from %s", DATA_DIR)

# ---------------------------------------------------------------------------
# In-memory index
# ---------------------------------------------------------------------------
# We keep a lightweight index in memory (id, title, year, language, repealed)
# plus a lazy cache of the full JSON for each act. The full texts are loaded
# on demand to keep startup fast and memory usage reasonable.

_index: list[dict[str, Any]] = []
_id_to_file: dict[str, Path] = {}
_full_cache: dict[str, dict[str, Any]] = {}


def _act_id_from_filename(name: str) -> str:
    """`act-print-123.json` -> `act-print-123` (the public-facing id)."""
    stem = Path(name).stem
    return stem


def _build_index() -> None:
    """Walk the data directory and build the search/listing index."""
    files = sorted(DATA_DIR.glob("act-print-*.json"))
    log.info("Indexing %d act files", len(files))
    for fp in files:
        try:
            with fp.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:  # noqa: BLE001
            log.warning("Skipping %s: %s", fp.name, exc)
            continue

        act_id = _act_id_from_filename(fp.name)
        _id_to_file[act_id] = fp

        csv_meta = data.get("csv_metadata") or {}
        _index.append(
            {
                "id": act_id,
                "act_title": (data.get("act_title") or "").strip(),
                "act_no": (data.get("act_no") or "").strip(),
                "act_year": str(data.get("act_year") or "").strip(),
                "language": data.get("language") or "",
                "is_repealed": bool(csv_meta.get("is_repealed", False)),
                "token_count": data.get("token_count") or 0,
                "num_sections": len(data.get("sections") or []),
                "num_footnotes": len(data.get("footnotes") or []),
                "source_url": data.get("source_url") or "",
            }
        )
    log.info("Index built: %d acts", len(_index))


_build_index()


def _load_full(act_id: str) -> dict[str, Any]:
    if act_id in _full_cache:
        return _full_cache[act_id]
    fp = _id_to_file.get(act_id)
    if fp is None:
        raise KeyError(act_id)
    with fp.open("r", encoding="utf-8") as f:
        data = json.load(f)
    _full_cache[act_id] = data
    return data


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "bangladesh-law-mcp",
    instructions=(
        "MCP server for the Bangladesh Legal Acts Dataset. Use the tools to "
        "list acts, fetch full act text, search across acts, or get a single "
        "section. Each act has metadata (year, number, language, repealed "
        "flag), the full section/footnote text, and historical government "
        "and legal-system context for the period when the act was passed."
    ),
)


# ---------------------------------------------------------------------------
# Health check (used by Fly.io / load balancers)
# ---------------------------------------------------------------------------


@mcp.custom_route("/healthz", methods=["GET"])
def healthz(_request):  # type: ignore[no-untyped-def]
    """Return a tiny liveness/readiness JSON payload.

    Exposed as a plain Starlette route by FastMCP, so it works regardless
    of the MCP transport in use (stdio is unaffected). On Fly.io the
    platform hits this every few seconds to decide if the VM is healthy.
    """
    return JSONResponse(
        {
            "status": "ok",
            "server": "bangladesh-law-mcp",
            "acts_loaded": len(_index),
            "sections_loaded": sum(
                (m.get("num_sections") or 0) for m in _index
            ),
            "data_dir": str(DATA_DIR),
        }
    )


# ----- helpers --------------------------------------------------------------


def _summarise(meta: dict[str, Any]) -> dict[str, Any]:
    """Return the lightweight summary used by list/search tools."""
    return {
        "id": meta["id"],
        "act_title": meta["act_title"],
        "act_no": meta["act_no"],
        "act_year": meta["act_year"],
        "language": meta["language"],
        "is_repealed": meta["is_repealed"],
        "num_sections": meta["num_sections"],
        "num_footnotes": meta["num_footnotes"],
        "token_count": meta["token_count"],
        "source_url": meta["source_url"],
    }


def _strip_footnotes(act: dict[str, Any]) -> dict[str, Any]:
    """Drop inline footnote markers like `1` `2` from section content."""
    out: dict[str, Any] = {}
    for k, v in act.items():
        if k == "sections" and isinstance(v, list):
            out[k] = [
                {
                    **s,
                    "section_content": re.sub(
                        r"\d+\[?", "", s.get("section_content", "")
                    ),
                }
                if isinstance(s, dict)
                else s
                for s in v
            ]
        else:
            out[k] = v
    return out


# ----- tools ----------------------------------------------------------------


@mcp.tool()
def list_acts(
    query: str = "",
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    language: Optional[str] = None,
    only_repealed: bool = False,
    only_active: bool = False,
    limit: int = 50,
) -> dict[str, Any]:
    """
    List acts in the dataset with optional filtering.

    Args:
        query: Free-text substring matched against the act title (case-insensitive).
        year_from: Earliest act year (inclusive).
        year_to: Latest act year (inclusive).
        language: Filter by language code: "english", "bengali", or "mixed".
        only_repealed: If true, return only repealed acts.
        only_active: If true, return only acts currently in force.
        limit: Maximum number of results to return (1-500, default 50).

    Returns:
        A dict with `total` (matched), `returned`, and `acts` (list of summaries).
    """
    limit = max(1, min(int(limit), 500))
    q = (query or "").lower().strip()

    results: list[dict[str, Any]] = []
    for meta in _index:
        if q and q not in meta["act_title"].lower():
            continue
        if year_from is not None:
            try:
                if int(meta["act_year"]) < year_from:
                    continue
            except ValueError:
                pass
        if year_to is not None:
            try:
                if int(meta["act_year"]) > year_to:
                    continue
            except ValueError:
                pass
        if language and meta["language"].lower() != language.lower():
            continue
        if only_repealed and not meta["is_repealed"]:
            continue
        if only_active and meta["is_repealed"]:
            continue
        results.append(_summarise(meta))

    return {
        "total": len(results),
        "returned": min(limit, len(results)),
        "acts": results[:limit],
    }


@mcp.tool()
def get_act(act_id: str, include_context: bool = True) -> dict[str, Any]:
    """
    Fetch the full record of a single act by its id (e.g. "act-print-11").

    Args:
        act_id: The act id, exactly as returned by list_acts / search_acts.
        include_context: Whether to include the historical government and
            legal-system context blocks (default true).

    Returns:
        The full act record: title, number, year, language, sections,
        footnotes, source URL, and (optionally) government / legal context.
    """
    try:
        act = _load_full(act_id)
    except KeyError:
        return {"error": f"Act not found: {act_id}"}

    out = _strip_footnotes(act)
    if not include_context:
        out.pop("government_context", None)
        out.pop("legal_system_context", None)
    return out


@mcp.tool()
def get_section(act_id: str, section_index: int) -> dict[str, Any]:
    """
    Fetch a single section of an act by its 0-based index in the sections array.

    Args:
        act_id: The act id, exactly as returned by list_acts / search_acts.
        section_index: 0-based position of the section in the act.

    Returns:
        Dict with `act_id`, `act_title`, `section_index`, `section_title`,
        and `section_content`. Returns an error dict if not found.
    """
    try:
        act = _load_full(act_id)
    except KeyError:
        return {"error": f"Act not found: {act_id}"}

    sections = act.get("sections") or []
    if section_index < 0 or section_index >= len(sections):
        return {
            "error": f"section_index {section_index} out of range "
            f"(0..{len(sections) - 1})"
        }

    sec = sections[section_index]
    content = re.sub(r"\d+\[?", "", sec.get("section_content", ""))
    return {
        "act_id": act_id,
        "act_title": act.get("act_title", ""),
        "act_year": act.get("act_year", ""),
        "section_index": section_index,
        "section_title": sec.get("section_title", ""),
        "section_content": content,
    }


@mcp.tool()
def search_acts(
    query: str,
    search_in: str = "sections",
    limit: int = 10,
) -> dict[str, Any]:
    """
    Free-text search across acts.

    Args:
        query: Substring to search for (case-insensitive).
        search_in: Where to search - "title", "sections", or "all".
        limit: Maximum number of matching acts to return (1-50, default 10).

    Returns:
        A dict with `total_matches` and `matches` (list of {act_summary,
        snippet, matched_section_index}). The snippet shows ~200 chars of
        surrounding context.
    """
    limit = max(1, min(int(limit), 50))
    q = (query or "").lower().strip()
    if not q:
        return {"error": "query must not be empty"}

    matches: list[dict[str, Any]] = []
    for meta in _index:
        title_hit = False
        section_hit_index: Optional[int] = None
        snippet: str = ""

        if search_in in ("title", "all") and q in meta["act_title"].lower():
            title_hit = True

        if search_in in ("sections", "all") and not title_hit:
            try:
                act = _load_full(meta["id"])
            except Exception:  # noqa: BLE001
                continue
            for i, sec in enumerate(act.get("sections") or []):
                content = (sec.get("section_content") or "").lower()
                if q in content:
                    section_hit_index = i
                    raw = sec.get("section_content") or ""
                    idx = raw.lower().find(q)
                    start = max(0, idx - 80)
                    end = min(len(raw), idx + len(q) + 120)
                    snippet = (
                        raw[start:end].replace("\n", " ")
                        + ("..." if end < len(raw) else "")
                    )
                    break

        if title_hit or section_hit_index is not None:
            matches.append(
                {
                    **_summarise(meta),
                    "matched_in": "title" if title_hit else "section",
                    "matched_section_index": section_hit_index,
                    "snippet": snippet,
                }
            )
        if len(matches) >= limit:
            break

    return {"total_matches": len(matches), "matches": matches}


@mcp.tool()
def get_statistics() -> dict[str, Any]:
    """
    Return aggregate statistics about the dataset.

    Returns:
        Totals, year range, language distribution, repealed count, and the
        most common government systems and legal frameworks represented.
    """
    if not _index:
        return {"total_acts": 0}

    years: list[int] = []
    languages: dict[str, int] = {}
    repealed = 0
    gov_systems: dict[str, int] = {}
    legal_frameworks: dict[str, int] = {}

    for meta in _index:
        try:
            years.append(int(meta["act_year"]))
        except ValueError:
            pass
        lang = meta["language"] or "unknown"
        languages[lang] = languages.get(lang, 0) + 1
        if meta["is_repealed"]:
            repealed += 1

        # Pull context lazily - it lives in the full JSON, not the index.
        try:
            act = _load_full(meta["id"])
        except Exception:  # noqa: BLE001
            continue

        gctx = act.get("government_context") or {}
        gs = gctx.get("govt_system")
        if gs:
            gov_systems[gs] = gov_systems.get(gs, 0) + 1

        lctx = act.get("legal_system_context") or {}
        lf = (lctx.get("legal_framework") or {}).get("primary_laws")
        if isinstance(lf, list):
            for law in lf:
                legal_frameworks[law] = legal_frameworks.get(law, 0) + 1

    return {
        "total_acts": len(_index),
        "total_sections": sum(m["num_sections"] for m in _index),
        "total_footnotes": sum(m["num_footnotes"] for m in _index),
        "year_range": {
            "earliest": min(years) if years else None,
            "latest": max(years) if years else None,
        },
        "repealed_acts": repealed,
        "active_acts": len(_index) - repealed,
        "languages": dict(sorted(languages.items(), key=lambda x: -x[1])),
        "top_government_systems": dict(
            sorted(gov_systems.items(), key=lambda x: -x[1])[:10]
        ),
        "top_legal_sources": dict(
            sorted(legal_frameworks.items(), key=lambda x: -x[1])[:10]
        ),
    }


# ----- resources ------------------------------------------------------------


@mcp.resource("act://{act_id}")
def act_resource(act_id: str) -> str:
    """Expose each act as a read-only MCP resource."""
    try:
        act = _load_full(act_id)
    except KeyError:
        return json.dumps({"error": f"Act not found: {act_id}"})
    return json.dumps(act, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Console-script entry point: `bangladesh-law-mcp`.

    Transport is selected via the ``TRANSPORT`` env var:

    * ``stdio`` (default) - JSON-RPC over stdin/stdout, used by Claude
      Desktop, Gemini CLI, Cursor, etc. via ``mcp run server.py``.
    * ``http`` - Streamable HTTP at ``http://<host>:8000/mcp``, used when
      the server is hosted (Fly.io, Docker, etc.) and consumed by clients
      that support remote MCP servers. The ``/healthz`` route is also
      served from the same port for liveness checks.
    """
    transport = os.getenv("TRANSPORT", "stdio").lower().strip()
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))

    if transport == "http":
        log.info("Starting Streamable HTTP transport on %s:%s/mcp", host, port)
        # ``streamable_http`` is the modern MCP-over-HTTP transport
        # (supersedes the old SSE transport). FastMCP mounts the MCP
        # endpoint at /mcp and serves our /healthz alongside it.
        mcp.settings.host = host
        mcp.settings.port = port
        mcp.run(transport="streamable-http")
    elif transport == "stdio":
        mcp.run()  # noqa: E702 - default stdio for local clients
    else:
        raise SystemExit(
            f"Unknown TRANSPORT={transport!r} (expected 'stdio' or 'http')"
        )


if __name__ == "__main__":
    main()
