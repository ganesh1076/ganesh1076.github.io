#!/usr/bin/env python3
"""
Fetch the latest publications from NASA ADS for a given ORCID and
regenerate the publications.html page, keeping the existing site structure.

Usage:
    python generate_publications.py

Requires:
    pip install ads          # NASA ADS Python client
  OR
    An ADS API token set in ADS_TOKEN env variable (uses requests as fallback).

Get your ADS API token from: https://ui.adsabs.harvard.edu/user/settings/token
Set it:  export ADS_TOKEN="your_token_here"
"""

import os
import re
import sys
import json
import html as html_module
from pathlib import Path
from datetime import datetime

# --- Configuration -----------------------------------------------------------
ORCID        = "0000-0003-3639-9052"
AUTHOR_NAME  = "Pawar, G"          # substring used to identify author in list
MAX_PAPERS   = 10
OUTPUT_FILE  = Path(__file__).parent / "publications.html"
TEMPLATE_FILE = Path(__file__).parent / "publications.html"
# -----------------------------------------------------------------------------

JOURNAL_LINKS = {
    "A&A":   "https://www.aanda.org/",
    "A&AS":  "https://www.aanda.org/",
    "AJ":    "https://iopscience.iop.org/journal/1538-3881",
    "ApJ":   "https://iopscience.iop.org/journal/0004-637X",
    "ApJL":  "https://journals.aas.org/astrophysical-journal-letters/",
    "ApJS":  "https://iopscience.iop.org/journal/0067-0049",
    "MNRAS": "https://academic.oup.com/mnras",
    "PASP":  "https://iopscience.iop.org/journal/1538-3873",
    "PASA":  "https://www.cambridge.org/core/journals/publications-of-the-astronomical-society-of-australia",
    "Proc.": "https://www.astro.sk/caosp/",
    "JDSO":  "http://www.jdso.org/",
}


def get_ads_token():
    token = os.environ.get("ADS_TOKEN", "").strip()
    if not token:
        sys.exit(
            "ERROR: NASA ADS API token not found.\n"
            "Get your token at https://ui.adsabs.harvard.edu/user/settings/token\n"
            "Then run:  export ADS_TOKEN='your_token_here'"
        )
    return token


def fetch_papers(token, max_papers=MAX_PAPERS):
    """Query ADS API and return list of paper dicts, newest first."""
    import urllib.request
    import urllib.parse

    fields = "title,author,year,bibcode,pub,volume,page,doi,arxiv_class,identifier,pubdate"
    query = urllib.parse.quote(f"orcid:{ORCID}")
    sort  = urllib.parse.quote("date desc, bibcode desc")
    url   = (
        f"https://api.adsabs.harvard.edu/v1/search/query"
        f"?q={query}&sort={sort}&fl={fields}&rows={max_papers}"
    )

    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())

    return data["response"]["docs"]


def journal_abbrev(pub):
    """Map full journal name to a short badge label."""
    if not pub:
        return "arXiv"
    p = pub.strip()
    mapping = [
        ("Astronomy and Astrophysics",          "A&A"),
        ("Astronomy & Astrophysics",             "A&A"),
        ("A&A",                                  "A&A"),
        ("The Astrophysical Journal Letters",    "ApJL"),
        ("Astrophysical Journal Letters",        "ApJL"),
        ("ApJL",                                 "ApJL"),
        ("The Astrophysical Journal Supplement", "ApJS"),
        ("The Astrophysical Journal",            "ApJ"),
        ("Astrophysical Journal",                "ApJ"),
        ("The Astronomical Journal",             "AJ"),
        ("Monthly Notices",                      "MNRAS"),
        ("MNRAS",                                "MNRAS"),
        ("Publications of the Astronomical Society of the Pacific", "PASP"),
        ("Contributions of the Astronomical Observatory", "Proc."),
        ("Journal of Double Star",               "JDSO"),
        ("Nature Astronomy",                     "NatAs"),
        ("Nature",                               "Nature"),
    ]
    for full, abbr in mapping:
        if full.lower() in p.lower():
            return abbr
    # Fall back to first 6 chars
    return p[:6].rstrip()


def arxiv_id_from_identifiers(identifiers):
    """Extract arXiv ID (e.g. '2412.12867') from ADS identifier list."""
    if not identifiers:
        return None
    for ident in identifiers:
        m = re.match(r"arXiv:(\d{4}\.\d{4,5})", ident, re.IGNORECASE)
        if m:
            return m.group(1)
        m = re.match(r"(\d{4}\.\d{4,5})", ident)
        if m:
            return m.group(1)
    return None


def doi_from_paper(paper):
    dois = paper.get("doi", [])
    return dois[0] if dois else None


def make_abstract_url(paper, arxiv_id, doi):
    """Best available URL for the abstract / landing page."""
    bibcode = paper.get("bibcode", "")
    if bibcode:
        return f"https://ui.adsabs.harvard.edu/abs/{bibcode}/abstract"
    if doi:
        return f"https://doi.org/{doi}"
    if arxiv_id:
        return f"https://arxiv.org/abs/{arxiv_id}"
    return "#"


def make_pdf_url(arxiv_id, doi, pub_abbrev):
    if arxiv_id:
        return f"https://arxiv.org/pdf/{arxiv_id}"
    if doi:
        return f"https://doi.org/{doi}"
    return "#"


def make_ads_url(paper, arxiv_id):
    bibcode = paper.get("bibcode", "")
    if bibcode:
        return f"https://ui.adsabs.harvard.edu/abs/{bibcode}/abstract"
    if arxiv_id:
        return f"https://ui.adsabs.harvard.edu/abs/arXiv:{arxiv_id}"
    return f"https://ui.adsabs.harvard.edu/search/q=orcid%3A{ORCID}&sort=date+desc"


def journal_ref_string(paper, pub_abbrev):
    """Human-readable journal reference line."""
    pub   = paper.get("pub", "") or ""
    vol   = paper.get("volume", "") or ""
    pages = paper.get("page", [])
    page  = pages[0] if pages else ""
    year  = paper.get("year", "") or ""
    doi   = doi_from_paper(paper)
    arxiv_id = arxiv_id_from_identifiers(paper.get("identifier", []))

    parts = []
    if pub:
        parts.append(html_module.escape(pub))
    if vol:
        parts.append(vol)
    if page:
        parts.append(page)
    if year:
        parts.append(f"({year})")
    ref = ", ".join(parts) if parts else f"{pub_abbrev} {year}"

    if doi:
        ref += f". doi:{doi}"
    elif arxiv_id:
        ref += f". arXiv:{arxiv_id}"
    return ref


def highlight_author(name):
    """Return True if this author name matches the site owner."""
    if not name:
        return False
    n = name.lower().replace(" ", "").replace(",", "").replace(".", "")
    targets = ["pawarg", "ganeshpawar", "gpawar"]
    return any(t in n for t in targets)


def render_author_list(authors):
    """Return HTML for the author list with the site owner bolded."""
    if not authors:
        return ""
    parts = []
    for i, author in enumerate(authors):
        escaped = html_module.escape(author)
        is_last = (i == len(authors) - 1)
        if highlight_author(author):
            tag = f"<nobr><strong>{escaped}</strong>{'.' if is_last else ';'}</nobr>"
        else:
            prefix = "and " if is_last else ""
            tag = f"<nobr>{prefix}{escaped}{'.' if is_last else ';'}</nobr>"
        parts.append(tag)
    return "\n              ".join(parts)


def render_paper_entry(paper):
    title    = html_module.escape((paper.get("title") or [""])[0])
    authors  = paper.get("author") or []
    pub      = paper.get("pub") or ""
    abbrev   = journal_abbrev(pub)
    jlink    = JOURNAL_LINKS.get(abbrev, "https://ui.adsabs.harvard.edu/")
    arxiv_id = arxiv_id_from_identifiers(paper.get("identifier", []))
    doi      = doi_from_paper(paper)
    abs_url  = make_abstract_url(paper, arxiv_id, doi)
    pdf_url  = make_pdf_url(arxiv_id, doi, abbrev)
    ads_url  = make_ads_url(paper, arxiv_id)
    jref     = journal_ref_string(paper, abbrev)
    authors_html = render_author_list(authors)

    return f"""\
      <li><div class="row m-0 mt-3 p-0">
        <div class="col-sm-1 p-0 abbr">
          <a class="badge font-weight-bold danger-color-dark darken-1 align-middle" style="width: 65px;" href="{jlink}" target="_blank">{abbrev}</a>
        </div>
        <div class="col-sm-11 mt-2 mt-sm-0 p-0 pl-xs-0 pl-sm-4 pr-xs-0 pr-sm-2">
          <div class="col p-0">
            <h5 class="title mb-0">{title}</h5>
            <div class="author">
              {authors_html}
            </div>
            <div><p class="periodical font-italic">{jref}</p></div>
            <div class="col p-0">
              <a class="badge grey waves-effect font-weight-light mr-1" href="{abs_url}" target="_blank">Abstract</a>
              <a class="badge grey waves-effect font-weight-light mr-1" href="{pdf_url}" target="_blank">PDF</a>
              <a class="badge grey waves-effect font-weight-light mr-1" href="{ads_url}" target="_blank">ADS</a>
            </div>
          </div>
        </div>
      </div></li>"""


def group_by_year(papers):
    groups = {}
    for paper in papers:
        year = paper.get("year", "Unknown")
        groups.setdefault(year, []).append(paper)
    return sorted(groups.items(), key=lambda x: x[0], reverse=True)


def render_publications_section(papers):
    sections = []
    for year, year_papers in group_by_year(papers):
        entries = "\n".join(render_paper_entry(p) for p in year_papers)
        sections.append(f"""\
<div class="row m-0 p-0" style="border-top: 1px solid #ddd; flex-direction: row-reverse;">
  <div class="col-sm-1 mt-2 p-0 pr-1">
    <h3 class="bibliography-year" style="color:black;">{year}</h3>
  </div>
  <div class="col-sm-11 p-0">
    <ol class="bibliography">
{entries}
    </ol>
  </div>
</div>""")
    return "\n\n".join(sections)


def build_publications_block(papers):
    pub_section = render_publications_section(papers)
    return f"""\
  <h1>Publications</h1>
  <div class="row" style="margin-top: -3.5em;">
    <a class="ml-auto mr-2" href="https://ui.adsabs.harvard.edu/search/q=orcid%3A{ORCID}&sort=date%20desc%2C%20bibcode%20desc&p_=0" target="_blank">
      <img height="55px" src="./assets/img/ads_logo.svg" />
    </a>
  </div>

{pub_section}

  </div>"""


# ---- HTML skeleton (everything outside the publications content) ------------

HEAD = """\
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">

  <title>Ganesh Pawar | Publications</title>
  <meta name="description" content="Personal website of Ganesh Pawar.">

  <!-- Fonts and Icons -->
  <link rel="stylesheet" type="text/css" href="https://fonts.googleapis.com/css?family=Roboto:300,400,500,700|Roboto+Slab:100,300,400,500,700|Material+Icons" />

  <!-- CSS Files -->
  <link rel="stylesheet" href="./assets/css/all.min.css">
  <link rel="stylesheet" href="./assets/css/academicons.min.css">
  <link rel="stylesheet" href="./assets/css/main.css">
  <link rel="canonical" href="./publications/">
  <style>
    /* Professional theme overrides */
    body {
      background-image: none !important;
      background-color: #f4f6f9 !important;
    }
    a { color: #1565c0; text-decoration: none; }
    a:hover { color: #0d47a1; text-decoration: none; }
    .navbar-active a { color: #1565c0 !important; }
    .news a { color: #1565c0; }
    .cv h3 { color: #1565c0; }
    .badge-notify { background: #1565c0 !important; }
    .bibliography li .author nobr > em { color: #1565c0 !important; }
    .bibliography .abbr a:hover { background: #1565c0 !important; }
    .project-card .github-icon .stars { background-color: #1565c0 !important; }
    progress { color: #1565c0; }
    progress::-webkit-progress-value { background-color: #1565c0; }
    progress::-moz-progress-bar { background-color: #1565c0; }
    .progress-bar { background-color: #1565c0; }
    footer { background-color: #1a237e !important; color: #eceff1 !important; }
    footer a { color: #c5cae9 !important; }
    footer a:hover { color: #90caf9 !important; }
  </style>
</head>
<body>
  <!-- Header -->
  <nav id="navbar" class="navbar fixed-top navbar-expand-md grey lighten-5 z-depth-1 navbar-light">
    <div class="container-fluid p-0">
        <a class="navbar-brand title font-weight-lighter" href="./"><span class="font-weight-bold">Ganesh</span> Pawar</a>
      <button class="navbar-toggler ml-auto" type="button" data-toggle="collapse" data-target="#navbarNav" aria-controls="navbarNav" aria-expanded="false" aria-label="Toggle navigation">
        <span class="navbar-toggler-icon"></span>
      </button>
      <div class="collapse navbar-collapse text-right" id="navbarNav">
        <ul class="navbar-nav ml-auto flex-nowrap">
          <li class="nav-item"><a class="nav-link" href="./">Home</a></li>
          <li class="nav-item"><a class="nav-link" href="./cv.html">CV</a></li>
          <li class="nav-item"><a class="nav-link" href="./projects.html">Projects</a></li>
          <li class="nav-item navbar-active font-weight-bold">
            <a class="nav-link" href="./publications.html">Publications<span class="sr-only">(current)</span></a>
          </li>
          <li class="nav-item"><a class="nav-link" href="./outreach.html">Outreach</a></li>
        </ul>
      </div>
    </div>
  </nav>

  <!-- Scrolling Progress Bar -->
  <progress id="progress" value="0">
    <div class="progress-container">
      <span class="progress-bar"></span>
    </div>
  </progress>

  <!-- Content -->
  <div class="content">
"""

FOOT = """\

  <!-- Footer -->
  <footer>
    &copy; Copyright 2021 Ganesh Pawar.
  </footer>

  <!-- Core JavaScript Files -->
  <script src="./assets/js/jquery.min.js" type="text/javascript"></script>
  <script src="./assets/js/popper.min.js" type="text/javascript"></script>
  <script src="./assets/js/bootstrap.min.js" type="text/javascript"></script>
  <script src="./assets/js/mdb.min.js" type="text/javascript"></script>
  <script async="" src="https://cdnjs.cloudflare.com/ajax/libs/masonry/4.2.2/masonry.pkgd.min.js" integrity="sha384-GNFwBvfVxBkLMJpYMOABq3c+d3KnQxudP/mGPkzpZSTYykLBNsZEnG2D9G/X/+7D" crossorigin="anonymous"></script>
  <script src="https://unpkg.com/imagesloaded@4/imagesloaded.pkgd.min.js"></script>
  <script type="text/javascript" async src="https://cdnjs.cloudflare.com/ajax/libs/mathjax/2.7.5/latest.js?config=TeX-MML-AM_CHTML"></script>
  <script src="./assets/js/common.js"></script>

  <!-- Scrolling Progress Bar -->
  <script type="text/javascript">
    $(document).ready(function() {
      var navbarHeight = $('#navbar').outerHeight(true);
      $('body').css({ 'padding-top': navbarHeight });
      $('progress-container').css({ 'padding-top': navbarHeight });
      var progressBar = $('#progress');
      progressBar.css({ 'top': navbarHeight });
      var getMax = function() { return $(document).height() - $(window).height(); }
      var getValue = function() { return $(window).scrollTop(); }
      if ('max' in document.createElement('progress')) {
        progressBar.attr({ max: getMax() });
        progressBar.attr({ value: getValue() });
        $(document).on('scroll', function() { progressBar.attr({ value: getValue() }); });
        $(window).resize(function() {
          var navbarHeight = $('#navbar').outerHeight(true);
          $('body').css({ 'padding-top': navbarHeight });
          $('progress-container').css({ 'padding-top': navbarHeight });
          progressBar.css({ 'top': navbarHeight });
          progressBar.attr({ max: getMax(), value: getValue() });
        });
      } else {
        var max = getMax(), value, width;
        var getWidth = function() { value = getValue(); width = (value/max)*100+'%'; return width; }
        var setWidth = function() { progressBar.css({ width: getWidth() }); };
        setWidth();
        $(document).on('scroll', setWidth);
        $(window).on('resize', function() { max = getMax(); setWidth(); });
      }
    });
  </script>

  <!-- Code Syntax Highlighting -->
  <link href="https://fonts.googleapis.com/css?family=Source+Code+Pro" rel="stylesheet">
  <script src="./assets/js/highlight.pack.js"></script>
  <script>hljs.initHighlightingOnLoad();</script>

  <!-- Enable Tooltips -->
  <script type="text/javascript">
    $(function () { $('[data-toggle="tooltip"]').tooltip() })
  </script>

  <!-- Google Analytics -->
  <script>
    (function(i,s,o,g,r,a,m){i['GoogleAnalyticsObject']=r;i[r]=i[r]||function(){
    (i[r].q=i[r].q||[]).push(arguments)},i[r].l=1*new Date();a=s.createElement(o),
    m=s.getElementsByTagName(o)[0];a.async=1;a.src=g;m.parentNode.insertBefore(a,m)
    })(window,document,'script','//www.google-analytics.com/analytics.js','ga');
    ga('create', 'UA-105573982-1', 'auto');
    ga('send', 'pageview');
  </script>
</body>
</html>
"""


def main():
    token = get_ads_token()
    print(f"Fetching up to {MAX_PAPERS} papers for ORCID {ORCID} from NASA ADS…")
    papers = fetch_papers(token, MAX_PAPERS)
    print(f"  Found {len(papers)} paper(s).")

    pub_block = build_publications_block(papers)
    html = HEAD + pub_block + FOOT

    OUTPUT_FILE.write_text(html, encoding="utf-8")
    print(f"  Written → {OUTPUT_FILE}")
    print("Done. Open publications.html in a browser to review.")


if __name__ == "__main__":
    main()
