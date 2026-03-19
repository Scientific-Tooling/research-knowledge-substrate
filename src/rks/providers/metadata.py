from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

_DEFAULT_TIMEOUT = 30


class CrossrefMetadataProvider:
    def __init__(self, urlopen=urllib.request.urlopen):
        self.urlopen = urlopen

    def fetch(self, doi: str) -> dict:
        encoded = urllib.parse.quote(doi, safe="")
        with _urlopen_with_timeout(self.urlopen, f"https://api.crossref.org/works/{encoded}") as response:
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
    def __init__(self, urlopen=urllib.request.urlopen):
        self.urlopen = urlopen

    def fetch(self, arxiv_id: str) -> dict:
        with _urlopen_with_timeout(
            self.urlopen,
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


class PubmedMetadataProvider:
    def __init__(self, urlopen=urllib.request.urlopen):
        self.urlopen = urlopen

    def fetch(self, pmid: str) -> dict:
        encoded = urllib.parse.quote(pmid, safe="")
        with _urlopen_with_timeout(
            self.urlopen,
            f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id={encoded}&retmode=xml"
        ) as response:
            raw_xml = response.read().decode("utf-8")

        root = ET.fromstring(raw_xml)
        article = root.find("./PubmedArticle")
        if article is None:
            raise ValueError(f"No PubMed article found for PMID {pmid}")

        title = _collapse_xml_text(article.find("./MedlineCitation/Article/ArticleTitle"))
        abstract = _parse_pubmed_abstract(article)
        authors = _parse_pubmed_authors(article)
        year = _parse_pubmed_year(article)
        venue = _collapse_xml_text(article.find("./MedlineCitation/Article/Journal/Title")) or "PubMed"
        doi = _first_pubmed_article_id(article, "doi")

        return {
            "title": title or f"PMID {pmid}",
            "abstract": abstract or None,
            "authors": authors,
            "year": year,
            "venue": venue,
            "doi": doi,
            "arxiv_id": None,
            "references": _parse_pubmed_references(article),
            "pdf_candidates": [],
            "raw": raw_xml,
        }


def _strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value or "").replace("\n", " ").strip()


def _collapse_xml_text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return " ".join("".join(node.itertext()).split())


def _parse_pubmed_abstract(article: ET.Element) -> str:
    parts = []
    for section in article.findall("./MedlineCitation/Article/Abstract/AbstractText"):
        label = (section.attrib.get("Label") or "").strip()
        content = _collapse_xml_text(section)
        if not content:
            continue
        parts.append(f"{label}: {content}" if label else content)
    return "\n\n".join(parts)


def _parse_pubmed_authors(article: ET.Element) -> list[str]:
    authors = []
    for author in article.findall("./MedlineCitation/Article/AuthorList/Author"):
        collective_name = _collapse_xml_text(author.find("./CollectiveName"))
        if collective_name:
            authors.append(collective_name)
            continue

        last_name = _collapse_xml_text(author.find("./LastName"))
        fore_name = _collapse_xml_text(author.find("./ForeName"))
        initials = _collapse_xml_text(author.find("./Initials"))
        full_name = " ".join(part for part in (fore_name or initials, last_name) if part)
        if full_name:
            authors.append(full_name)
    return authors


def _parse_pubmed_year(article: ET.Element) -> int | None:
    year_text = _collapse_xml_text(article.find("./MedlineCitation/Article/Journal/JournalIssue/PubDate/Year"))
    if year_text.isdigit():
        return int(year_text)

    medline_date = _collapse_xml_text(article.find("./MedlineCitation/Article/Journal/JournalIssue/PubDate/MedlineDate"))
    match = re.search(r"\b(\d{4})\b", medline_date)
    if match:
        return int(match.group(1))
    return None


def _first_pubmed_article_id(article: ET.Element, id_type: str) -> str | None:
    path = f"./PubmedData/ArticleIdList/ArticleId[@IdType='{id_type}']"
    value = _collapse_xml_text(article.find(path))
    return value or None


def _parse_pubmed_references(article: ET.Element) -> list[dict]:
    references = []
    for reference in article.findall("./PubmedData/ReferenceList/Reference"):
        citation = _collapse_xml_text(reference.find("./Citation"))
        doi = None
        for identifier in reference.findall("./ArticleIdList/ArticleId"):
            if (identifier.attrib.get("IdType") or "").lower() == "doi":
                doi = _collapse_xml_text(identifier) or None
                if doi:
                    break
        year = None
        if citation:
            match = re.search(r"\b(\d{4})\b", citation)
            if match:
                year = int(match.group(1))
        references.append(
            {
                "doi": doi,
                "title": citation or None,
                "year": year,
            }
        )
    return references


def _urlopen_with_timeout(urlopen, url: str):
    try:
        return urlopen(url, timeout=_DEFAULT_TIMEOUT)
    except TypeError:
        return urlopen(url)
