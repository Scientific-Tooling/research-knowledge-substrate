from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


class CrossrefMetadataProvider:
    def fetch(self, doi: str) -> dict:
        encoded = urllib.parse.quote(doi, safe="")
        with urllib.request.urlopen(f"https://api.crossref.org/works/{encoded}") as response:
            payload = json.loads(response.read().decode("utf-8"))

        message = payload["message"]
        issued = (message.get("issued", {}).get("date-parts") or [[None]])[0]
        authors = []
        for author in message.get("author", []):
            given = author.get("given", "").strip()
            family = author.get("family", "").strip()
            full_name = " ".join(part for part in (given, family) if part)
            if full_name:
                authors.append(full_name)

        abstract = _strip_tags(message.get("abstract", ""))
        titles = message.get("title") or []
        venues = message.get("container-title") or []
        pdf_candidates = []
        for link in message.get("link", []):
            if link.get("content-type") != "application/pdf":
                continue
            url = link.get("URL")
            if not url:
                continue
            pdf_candidates.append({"url": url, "source": "crossref_link"})

        return {
            "title": titles[0] if titles else doi,
            "abstract": abstract or None,
            "authors": authors,
            "year": issued[0],
            "venue": venues[0] if venues else None,
            "doi": doi,
            "arxiv_id": None,
            "references": [
                {
                    "doi": reference.get("DOI"),
                    "title": reference.get("article-title") or reference.get("unstructured"),
                    "year": reference.get("year"),
                }
                for reference in message.get("reference", [])
            ],
            "pdf_candidates": pdf_candidates,
            "raw": payload,
        }


class ArxivMetadataProvider:
    def fetch(self, arxiv_id: str) -> dict:
        with urllib.request.urlopen(
            f"http://export.arxiv.org/api/query?id_list={urllib.parse.quote(arxiv_id, safe='')}"
        ) as response:
            raw_xml = response.read().decode("utf-8")

        root = ET.fromstring(raw_xml)
        namespace = {"atom": "http://www.w3.org/2005/Atom"}
        entry = root.find("atom:entry", namespace)
        if entry is None:
            raise ValueError(f"No arXiv entry found for {arxiv_id}")

        authors = [
            author.findtext("atom:name", default="", namespaces=namespace).strip()
            for author in entry.findall("atom:author", namespace)
        ]
        title = " ".join(entry.findtext("atom:title", default="", namespaces=namespace).split())
        abstract = " ".join(entry.findtext("atom:summary", default="", namespaces=namespace).split())
        published = entry.findtext("atom:published", default="", namespaces=namespace)
        year = int(published[:4]) if len(published) >= 4 and published[:4].isdigit() else None

        return {
            "title": title or arxiv_id,
            "abstract": abstract or None,
            "authors": [name for name in authors if name],
            "year": year,
            "venue": "arXiv",
            "doi": None,
            "arxiv_id": arxiv_id,
            "references": [],
            "pdf_candidates": [
                {
                    "url": f"https://arxiv.org/pdf/{arxiv_id}.pdf",
                    "source": "arxiv_pdf",
                }
            ],
            "raw": raw_xml,
        }


def _strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value or "").replace("\n", " ").strip()
