#!/usr/bin/env python3
"""Generate a print-optimized PDF CV from _data/data.yml using WeasyPrint.

Single source of truth: _data/data.yml. Run locally or from CI:

    pip install PyYAML weasyprint      # (weasyprint also needs system pango libs)
    python scripts/generate_cv_pdf.py

Output: Emilien_Schaffner_CV.pdf at the repository root.
"""
import html
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = REPO_ROOT / "_data" / "data.yml"
OUT_PDF = REPO_ROOT / "Emilien_Schaffner_CV.pdf"

BRAND = "#4CAC9D"
BRAND_DARK = "#3A8579"
INK = "#2b2b2b"
MUTED = "#6b6b6b"
LIGHT = "#f4f8f7"

# Location isn't a field in the theme's data.yml, so it's set here.
LOCATION = "Switzerland"


def esc(text):
    return html.escape(str(text), quote=False)


def clean_inline(text):
    """Strip theme HTML (<br/>) and collapse whitespace for plain-text fields."""
    for tag in ("<br />", "<br/>", "<br>"):
        text = text.replace(tag, " ")
    return " ".join(text.split())


def label_after_nbsp(text):
    """'🇫🇷&nbsp;&nbsp;French' -> 'French' (drop leading emoji/entities)."""
    return text.split("&nbsp;")[-1].strip()


def parse_details(block):
    """Parse a YAML block-scalar of markdown-ish bullets.

    Returns (intro, bullets, outro) where bullets is a list of
    [text, [sub, sub, ...]]. Handles nested bullets (deeper indent),
    intro/outro paragraphs, and wrapped continuation lines.
    """
    lines = [ln for ln in (l.rstrip() for l in block.splitlines()) if ln.strip()]
    intro = outro = None
    bullets = []
    base_indent = None
    for raw in lines:
        stripped = raw.lstrip()
        indent = len(raw) - len(stripped)
        if stripped.startswith("- "):
            text = stripped[2:].strip()
            if base_indent is None:
                base_indent = indent
            if indent > base_indent and bullets:
                bullets[-1][1].append(text)
            else:
                bullets.append([text, []])
        elif not bullets:
            intro = f"{intro} {stripped}".strip() if intro else stripped
        elif stripped[:1].islower():
            # wrapped continuation of the previous bullet / sub-bullet
            if bullets[-1][1]:
                bullets[-1][1][-1] += " " + stripped
            else:
                bullets[-1][0] += " " + stripped
        else:
            outro = f"{outro} {stripped}".strip() if outro else stripped
    return intro, bullets, outro


def bullets_html(bullets):
    out = ["<ul>"]
    for text, subs in bullets:
        if subs:
            sub = "".join(f"<li>{esc(s)}</li>" for s in subs)
            out.append(f"<li>{esc(text)}<ul class='sub'>{sub}</ul></li>")
        else:
            out.append(f"<li>{esc(text)}</li>")
    out.append("</ul>")
    return "".join(out)


def build_html(data):
    sidebar = data["sidebar"]

    # Tagline field is "Title <br /> tagline <br /> subtag"
    parts = [p.strip() for p in sidebar["tagline"].replace("<br/>", "<br />").split("<br />")]
    title_line = parts[0] if parts else ""
    tagline = parts[1] if len(parts) > 1 else ""
    subtag = parts[2] if len(parts) > 2 else ""

    contacts = []
    loc = sidebar.get("location") or LOCATION
    if loc:
        contacts.append(("Location", loc))
    if sidebar.get("email"):
        contacts.append(("Email", sidebar["email"]))
    if sidebar.get("phone"):
        contacts.append(("Phone", str(sidebar["phone"])))
    if sidebar.get("linkedin"):
        contacts.append(("LinkedIn", f"linkedin.com/in/{sidebar['linkedin']}"))
    if sidebar.get("github"):
        contacts.append(("GitHub", f"github.com/{sidebar['github']}"))
    if sidebar.get("website"):
        contacts.append(("Web", sidebar["website"]))
    contact_html = "  &nbsp;|&nbsp;  ".join(
        f"<span class='c-label'>{esc(k)}:</span> {esc(v)}" for k, v in contacts
    )

    profile = [p.strip() for p in data["career-profile"]["summary"].split("\n\n") if p.strip()]
    profile_html = "".join(f"<p>{esc(p)}</p>" for p in profile)

    exp_html = ""
    for e in data["experiences"]:
        role = clean_inline(e["role"])
        intro, bullets, outro = parse_details(e["details"])
        body = ""
        if intro:
            body += f"<p class='intro'>{esc(intro)}</p>"
        if bullets:
            body += bullets_html(bullets)
        if outro:
            body += f"<p class='outro'>{esc(outro)}</p>"
        exp_html += f"""
        <div class="entry">
          <div class="entry-head">
            <div><span class="role">{esc(role)}</span> <span class="company">&middot; {esc(e['company'])}</span></div>
            <div class="time">{esc(e['time'])}</div>
          </div>
          {body}
        </div>"""

    skills_html = ""
    for s in data["skills"]["toolset"]:
        pct = str(s["level"]).replace("%", "").strip()
        skills_html += f"""
        <div class="skill">
          <div class="skill-label">{esc(s['name'])}</div>
          <div class="bar"><div class="fill" style="width:{esc(pct)}%"></div></div>
        </div>"""

    edu_html = ""
    for ed in data["education"]:
        edu_html += f"""
        <div class="entry edu">
          <div class="entry-head">
            <div><span class="role">{esc(ed['degree'])}</span> <span class="company">&middot; {esc(ed['university'])}</span></div>
            <div class="time">{esc(ed['time'])}</div>
          </div>
        </div>"""

    certs_html = "".join(
        f"<li><span class='cert-title'>{esc(clean_inline(c['title']))}</span>"
        f"<span class='cert-date'>{esc(c['tagline'])}</span></li>"
        for c in data["projects"]["assignments"]
    )

    lang_html = "".join(
        f"<li><b>{esc(label_after_nbsp(l['idiom']))}</b> &mdash; {esc(l['level'])}</li>"
        for l in sidebar.get("languages", [])
    )
    interest_html = "".join(
        f"<span class='pill'>{esc(label_after_nbsp(i['item']))}</span>"
        for i in sidebar.get("interests", [])
    )

    avatar = sidebar.get("avatar", "profile.png")

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><style>
@page {{
  size: A4;
  margin: 11mm 14mm 9mm 14mm;
  @bottom-center {{
    content: "{esc(sidebar['name'])} \\2014 Curriculum Vitae \\2014 Page " counter(page) " / " counter(pages);
    font-family: Helvetica, Arial, sans-serif; font-size: 7.5pt; color: {MUTED};
  }}
}}
* {{ box-sizing: border-box; }}
body {{ font-family: "Helvetica Neue", Helvetica, Arial, "Liberation Sans", sans-serif; color: {INK};
       font-size: 9.1pt; line-height: 1.38; margin: 0; }}
.header {{ display: flex; align-items: center; gap: 16px;
  background: {BRAND}; color: #fff; padding: 12px 18px; border-radius: 8px; }}
.header img {{ width: 78px; height: 78px; border-radius: 50%; border: 3px solid rgba(255,255,255,.85);
  object-fit: cover; flex: 0 0 auto; }}
.h-name {{ font-size: 22pt; font-weight: 700; letter-spacing: .3px; margin: 0 0 1px; }}
.h-title {{ font-size: 11pt; font-weight: 600; opacity: .97; }}
.h-tag {{ font-size: 9pt; opacity: .95; margin-top: 3px; }}
.h-sub {{ font-size: 8.4pt; opacity: .9; margin-top: 1px; font-style: italic; }}
.contact {{ margin-top: 9px; font-size: 8.5pt; color: {MUTED}; text-align: center;
  padding-bottom: 9px; border-bottom: 1px solid #e3e9e8; }}
.contact .c-label {{ color: {BRAND_DARK}; font-weight: 600; }}
h2.sec {{ font-size: 10.3pt; text-transform: uppercase; letter-spacing: 1.2px;
  color: {BRAND_DARK}; margin: 9px 0 4px; padding-bottom: 2px; border-bottom: 2px solid {BRAND}; }}
.profile p {{ margin: 0 0 3px; text-align: justify; }}
.entry {{ margin-bottom: 6px; break-inside: avoid; }}
.entry-head {{ display: flex; justify-content: space-between; align-items: baseline; gap: 10px; }}
.role {{ font-weight: 700; font-size: 10pt; }}
.company {{ color: {MUTED}; font-weight: 500; }}
.time {{ color: {BRAND_DARK}; font-weight: 600; font-size: 8.6pt; white-space: nowrap; }}
.entry ul {{ margin: 3px 0 0; padding-left: 16px; }}
.entry li {{ margin: 1px 0; }}
.entry p.intro {{ margin: 0 0 2px; }}
.entry p.outro {{ margin: 2px 0 0; color: {MUTED}; }}
ul.sub {{ margin: 1px 0 2px; padding-left: 15px; list-style: circle; color: {MUTED}; }}
.edu {{ margin-bottom: 5px; }}
.skill {{ margin-bottom: 4px; break-inside: avoid; }}
.skill-label {{ font-size: 8.6pt; margin-bottom: 2px; }}
.bar {{ height: 6px; background: {LIGHT}; border-radius: 4px; overflow: hidden; }}
.fill {{ height: 100%; background: {BRAND}; border-radius: 4px; }}
.two-col {{ column-count: 2; column-gap: 22px; }}
ul.certs {{ list-style: none; margin: 0; padding: 0; }}
ul.certs li {{ display: flex; justify-content: space-between; gap: 8px; font-size: 8.7pt;
  margin-bottom: 2px; break-inside: avoid; border-bottom: 1px dotted #dfe6e5; padding-bottom: 1px; }}
.cert-date {{ color: {BRAND_DARK}; font-weight: 600; white-space: nowrap; }}
.bottom {{ display: flex; gap: 26px; margin-top: 4px; }}
.bottom .col {{ flex: 1; }}
ul.langs {{ list-style: none; margin: 0; padding: 0; }}
ul.langs li {{ margin-bottom: 3px; }}
.pill {{ display: inline-block; background: {LIGHT}; color: {BRAND_DARK}; border: 1px solid #d9e6e3;
  border-radius: 12px; padding: 2px 9px; font-size: 8.3pt; margin: 0 4px 4px 0; }}
</style></head>
<body>
  <div class="header">
    <img src="assets/images/{esc(avatar)}" alt="">
    <div>
      <div class="h-name">{esc(sidebar['name'])}</div>
      <div class="h-title">{esc(title_line)}</div>
      <div class="h-tag">{esc(tagline)}</div>
      <div class="h-sub">{esc(subtag)}</div>
    </div>
  </div>
  <div class="contact">{contact_html}</div>

  <h2 class="sec">Career Profile</h2>
  <div class="profile">{profile_html}</div>

  <h2 class="sec">Professional Experience</h2>
  {exp_html}

  <h2 class="sec">Skills &amp; Proficiency</h2>
  <div class="two-col">{skills_html}</div>

  <h2 class="sec">Education</h2>
  {edu_html}

  <h2 class="sec">Certifications &amp; Courses</h2>
  <ul class="certs two-col">{certs_html}</ul>

  <div class="bottom">
    <div class="col">
      <h2 class="sec">Languages</h2>
      <ul class="langs">{lang_html}</ul>
    </div>
    <div class="col">
      <h2 class="sec">Interests</h2>
      <div>{interest_html}</div>
    </div>
  </div>
</body></html>"""


def render_pdf(html_str):
    weasyprint = shutil.which("weasyprint")
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as tmp:
        tmp.write(html_str)
        tmp_path = tmp.name
    try:
        base_url = REPO_ROOT.as_uri() + "/"
        if weasyprint:  # CLI (matches local Homebrew install)
            subprocess.run(
                [weasyprint, "--base-url", base_url, tmp_path, str(OUT_PDF)],
                check=True,
            )
        else:  # Python module fallback (matches CI pip install)
            from weasyprint import HTML  # noqa: PLC0415
            HTML(string=html_str, base_url=base_url).write_pdf(str(OUT_PDF))
    finally:
        os.unlink(tmp_path)


def main():
    with open(DATA_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    render_pdf(build_html(data))
    print(f"Generated {OUT_PDF.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    sys.exit(main())
